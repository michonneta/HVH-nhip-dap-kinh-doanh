"""Điểm vào cho GitHub Actions.

  python -m pipeline.run tick                     # chạy định kỳ: đồng bộ nhóm Lark, gửi bản tin đến hạn, làm mới dashboard
  python -m pipeline.run build                    # làm mới dữ liệu dashboard (docs/data)
  python -m pipeline.run send [--date D] [--groups oc_x,oc_y]   # gửi ngay (trống = mọi nhóm đã đăng ký)
  python -m pipeline.run test --groups oc_x       # gửi tin kiểm tra kết nối
  python -m pipeline.run chats                    # đồng bộ danh sách nhóm Bot đang tham gia
"""
import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import config as config_mod
from . import metrics
from .bulletin import build_card, draft_card, test_card
from .config import ROOT

log = logging.getLogger("nhip-dap")
DATA_DIR = ROOT / "docs" / "data"
STATE_DIR = ROOT / "state"
SEND_LOG = STATE_DIR / "send_log.json"
BUILD_STATE = STATE_DIR / "build.json"
CHATS_STATE = STATE_DIR / "lark_chats.sha256"   # chỉ lưu dấu vân tay, tên nhóm nằm trong file đã mã hóa
SNAPSHOTS = STATE_DIR / "giao_snapshots.json"   # số đơn cửa sổ giao lúc gửi bản tin, để tuần sau xem đơn quá hạn đi về đâu
DRAFTS_WITH_HTML = 12                           # chỉ giữ bản tin HTML cho các bản nháp gần nhất (file dữ liệu gọn)
CATCHUP_HOURS = 6         # lịch bị trễ (GitHub cron chậm) vẫn gửi bù trong khoảng này
BUILD_EVERY_HOURS = float(os.getenv("BUILD_EVERY_HOURS", "20"))
DOW_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# ---------------------------------------------------------------- tiện ích
def _read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def _now(cfg) -> datetime:
    return datetime.now(ZoneInfo(cfg["timezone"]))


def _dashboard_url(cfg) -> str:
    if cfg.get("dashboard_url"):
        return cfg["dashboard_url"]
    repo = os.getenv("GITHUB_REPOSITORY", "")  # owner/repo, có sẵn trong GitHub Actions
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner.lower()}.github.io/{name}/"
    return ""


class _Sealer:
    """Ghi file dữ liệu dashboard, mã hóa nếu có DASHBOARD_PASSWORD."""

    def __init__(self):
        pwd = os.getenv("DASHBOARD_PASSWORD", "")
        if pwd:
            from .crypto import Encryptor
            self.enc = Encryptor(pwd)
        else:
            self.enc = None
            log.warning("Chưa đặt DASHBOARD_PASSWORD: dữ liệu dashboard sẽ ở dạng KHÔNG mã hóa (công khai trên Pages)")

    def write(self, name, obj, gz=False):
        if self.enc:
            _write_json(DATA_DIR / name, self.enc.seal(obj, gz=gz))
        else:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            (DATA_DIR / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str),
                                         encoding="utf-8")


def _bot():
    from .lark import LarkBot
    return LarkBot()


# ---------------------------------------------------------------- nhóm Lark
def sync_chats(cfg, sealer=None):
    """Lấy các nhóm Bot đang tham gia; ghi docs/data/lark_chats.json khi danh sách thay đổi.

    Trả về {chat_id: tên} hoặc None nếu không gọi được Lark (khi đó không chặn việc gửi).
    """
    try:
        chats = sorted(_bot().list_chats(), key=lambda c: c["name"])
    except Exception as e:
        log.warning("Không lấy được danh sách nhóm Lark: %s", e)
        return None
    digest = hashlib.sha256(json.dumps(chats, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    old = CHATS_STATE.read_text().strip() if CHATS_STATE.exists() else ""
    if digest != old or not (DATA_DIR / "lark_chats.json").exists():
        (sealer or _Sealer()).write("lark_chats.json", {"updated_at": _now(cfg).isoformat(timespec="seconds"), "chats": chats})
        CHATS_STATE.parent.mkdir(parents=True, exist_ok=True)
        CHATS_STATE.write_text(digest)
        log.info("Danh sách nhóm Lark thay đổi: %s nhóm", len(chats))
    live = {c["chat_id"]: c["name"] for c in chats}
    for g in cfg["groups"]:  # dùng tên nhóm mới nhất nếu nhóm đổi tên
        g["name"] = live.get(g["chat_id"], g["name"])
    return live


# ---------------------------------------------------------------- build dashboard
def build(cfg, sealer=None) -> dict:
    """Làm mới dữ liệu Dashboard (khối cube, trình duyệt tự lọc/tính) + báo cáo kỳ gần nhất cho bản tin."""
    from .cube import build_cube
    sealer = sealer or _Sealer()
    today = _now(cfg).date()
    latest = metrics.last_sunday(today)
    sealer.write("cube.json", build_cube(today), gz=True)
    reports = {latest: metrics.build_report(latest, cfg)}
    record_snapshot(cfg, reports[latest])
    built_at = _now(cfg).isoformat(timespec="seconds")
    sealer.write("index.json", {
        "generated_at": built_at, "latest": str(latest), "today": str(today),
        "config": {k: v for k, v in cfg.items() if k != "groups"}, "dashboard_url": _dashboard_url(cfg),
    })
    for old in list(DATA_DIR.glob("report-*.json")) + [DATA_DIR / "trend.json"]:  # định dạng cũ
        old.unlink(missing_ok=True)
    write_history(sealer)
    _write_json(BUILD_STATE, {"built_at": built_at})
    log.info("Đã build dashboard, kỳ bản tin gần nhất T = %s", latest)
    return reports


def write_history(sealer):
    sealer.write("history.json", _read_json(SEND_LOG, [])[-200:][::-1])


def record_snapshot(cfg, report):
    """Lưu số đơn cửa sổ giao của kỳ T lần đầu thấy (lúc gửi bản tin), giữ 8 kỳ gần nhất."""
    from .report import snapshot_of
    snaps = _read_json(SNAPSHOTS, {})
    if report["run_date"] in snaps:
        return
    snaps[report["run_date"]] = snapshot_of(report, _now(cfg).isoformat(timespec="seconds"))
    _write_json(SNAPSHOTS, dict(sorted(snaps.items())[-8:]))


# ---------------------------------------------------------------- soạn bản tin (AI Analyst)
def _ai_enabled(cfg) -> bool:
    from .ai_writer import backend
    return cfg["ai"]["enabled"] and bool(backend())


def compose(cfg, report, kpi_type, markets, dash_url, cache) -> dict:
    """Bản tin cho một phạm vi (loại KPI + thị trường): mô hình số liệu → lời văn (AI, lỗi thì mẫu) → HTML + card Lark."""
    from . import report as report_mod, report_html, report_writer
    key = (report["run_date"], kpi_type, tuple(sorted(markets)))
    if key in cache:
        return cache[key]
    prev_snap = _read_json(SNAPSHOTS, {}).get(str(date.fromisoformat(report["run_date"]) - timedelta(days=7)))
    model = report_mod.build_model(report, kpi_type, markets, cfg["near_pp"], prev_snap)
    narr, author, err = report_writer.template(model), "mẫu", None
    if model["failing"] or cfg["send_when_ok"]:
        if _ai_enabled(cfg):
            try:
                narr, author = report_writer.write(model), "AI"
            except Exception as e:  # không để lỡ lịch vì AI: quay về mẫu, ghi lại lý do
                log.exception("AI Analyst lỗi, dùng bản tin theo mẫu")
                err = str(e)[:300]
        elif cfg["ai"]["enabled"]:
            err = "Chưa kết nối AI (thiếu secret CLAUDE_CODE_OAUTH_TOKEN hoặc ANTHROPIC_API_KEY)"
    b = {"has_alert": bool(model["failing"]), "failing": sorted({c["market"] for c in model["failing"]}),
         "alerts": len(model["failing"]), "author": author, "ai_error": err,
         "html": report_html.render(model, narr, author), "card": build_card(model, narr, dash_url, author),
         "image_key": None, "image_error": None}
    cache[key] = b
    return b


def _ensure_image(b, bot_box):
    """Chụp bản tin HTML thành ảnh và tải lên Lark một lần (image_key dùng lại khi duyệt gửi). Lỗi thì vẫn gửi card."""
    if b.get("image_key") or b.get("image_error"):
        return b.get("image_key")
    try:
        from .report_image import render_jpeg
        bot_box[0] = bot_box[0] or _bot()
        b["image_key"] = bot_box[0].upload_image(render_jpeg(b["html"]))
    except Exception as e:
        log.exception("Không tạo / tải được ảnh bản tin (kiểm tra quyền im:resource của Bot)")
        b["image_error"] = str(e)[:300]
    return b.get("image_key")


# ---------------------------------------------------------------- bản nháp chờ duyệt
def load_drafts() -> list:
    path = DATA_DIR / "drafts.json"
    if not path.exists():
        return []
    obj = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(obj, dict) and obj.get("enc"):
        from .crypto import open_sealed
        obj = open_sealed(obj, os.getenv("DASHBOARD_PASSWORD", ""))
    return obj


def save_drafts(drafts: list, sealer):
    drafts = drafts[-60:]
    for d in drafts[:-DRAFTS_WITH_HTML]:
        d.pop("html", None)
    sealer.write("drafts.json", drafts)


def _log(entries):
    _write_json(SEND_LOG, (_read_json(SEND_LOG, []) + entries)[-1000:])


def _entry(cfg, g, run_date, trigger, schedule_id=None, occurrence=None):
    return {"at": _now(cfg).isoformat(timespec="seconds"), "trigger": trigger, "run_date": str(run_date),
            "schedule_id": schedule_id, "occurrence": occurrence,
            "group_id": g["id"], "group": g["name"], "kpi_type": g["kpi_type"]}


def _post(bot_box, chat_id, card, image_key=None):
    """Gửi card, rồi ảnh bản tin đầy đủ (nếu có) ngay sau đó. Trả về message_id của card."""
    bot_box[0] = bot_box[0] or _bot()
    message_id = bot_box[0].send_card(chat_id, card)
    if image_key:
        bot_box[0].send_image(chat_id, image_key)
    return message_id


def send(cfg, run_date: date, group_ids: list, trigger: str, schedule_id=None, occurrence=None, report=None,
         live=None, sealer=None) -> list:
    """Soạn bản tin cho các nhóm; có duyệt thì tạo bản nháp, không thì gửi thẳng.

    live: {chat_id: tên} các nhóm Bot đang ở (None = không biết, cứ gửi).
    """
    report = report or metrics.build_report(run_date, cfg)
    record_snapshot(cfg, report)
    dash_url = _dashboard_url(cfg)
    review = cfg["review"]["enabled"]
    bot, cache, entries, pending = [None], {}, [], {}
    for g in cfg["groups"]:
        if g["id"] not in group_ids:
            continue
        entry = _entry(cfg, g, run_date, trigger, schedule_id, occurrence)
        try:
            if live is not None and g["chat_id"] not in live:
                entry["status"] = "bỏ qua (Bot không còn trong nhóm)"  # không thử lại mỗi 30 phút
            else:
                b = compose(cfg, report, g["kpi_type"], g["markets"], dash_url, cache)
                entry.update(failing=b["failing"], alerts=b["alerts"], author=b["author"])
                if not b["has_alert"] and not g.get("send_when_ok"):
                    entry["status"] = "bỏ qua (đạt KPI)"
                elif review:
                    pending.setdefault((g["kpi_type"], tuple(sorted(g["markets"]))), []).append((g, entry))
                    entry["status"] = "chờ duyệt"
                else:
                    entry["message_id"] = _post(bot, g["chat_id"], b["card"], _ensure_image(b, bot))
                    entry["status"] = "đã gửi"
                    if b.get("image_error"):
                        entry["image_error"] = b["image_error"]
        except Exception as e:  # lỗi một nhóm không chặn các nhóm khác
            log.exception("Gửi nhóm %s lỗi", g["name"])
            entry["status"] = "lỗi"
            entry["error"] = str(e)[:500]
        entries.append(entry)

    if pending:
        drafts = load_drafts()
        for (kpi_type, markets), members in pending.items():
            b = compose(cfg, report, kpi_type, list(markets), dash_url, cache)
            _ensure_image(b, bot)
            draft_id = f"{run_date:%Y%m%d}-{kpi_type}-{_now(cfg):%H%M%S}" + (f"-{'-'.join(markets)}" if markets else "")
            draft = {"id": draft_id, "run_date": str(run_date), "kpi_type": kpi_type, "markets": list(markets),
                     "created_at": _now(cfg).isoformat(timespec="seconds"), "trigger": trigger,
                     "author": b["author"], "ai_error": b["ai_error"], "failing": b["failing"],
                     "group_ids": [g["id"] for g, _ in members], "targets": [g["name"] for g, _ in members],
                     "status": "chờ duyệt", "card": b["card"], "html": b["html"],
                     "image_key": b["image_key"], "image_error": b["image_error"]}
            drafts.append(draft)
            for _, entry in members:
                entry["draft_id"] = draft_id
            _notify_reviewer(cfg, draft, bot, dash_url)
        save_drafts(drafts, sealer or _Sealer())

    for e in entries:
        log.info("%s → %s", e["group"], e["status"])
    _log(entries)
    return entries


def _notify_reviewer(cfg, draft, bot, dash_url):
    chat_id = cfg["review"]["chat_id"]
    if not chat_id:
        log.info("Bản nháp %s chờ duyệt trên Dashboard (chưa chọn nhóm duyệt)", draft["id"])
        return
    try:
        draft["review_message_id"] = _post(bot, chat_id, draft_card(draft["card"], draft["targets"], draft["id"], dash_url),
                                           draft.get("image_key"))
    except Exception as e:
        log.exception("Không gửi được bản nháp vào nhóm duyệt")
        draft["review_error"] = str(e)[:300]


def _find_draft(drafts, draft_id):
    d = next((x for x in drafts if x["id"] == draft_id), None)
    if not d:
        raise SystemExit(f"Không tìm thấy bản nháp {draft_id}")
    return d


def approve(cfg, draft_id, sealer, by="") -> list:
    """Gửi bản nháp đã duyệt tới các nhóm (theo danh sách nhóm hiện tại). by: tên Admin bấm duyệt."""
    drafts = load_drafts()
    d = _find_draft(drafts, draft_id)
    if d["status"] != "chờ duyệt":
        raise SystemExit(f"Bản nháp {draft_id} đang ở trạng thái '{d['status']}', không gửi lại")
    d["approved_by"] = by or None
    live = sync_chats(cfg, sealer)
    bot, entries = [None], []
    targets = [g for g in cfg["groups"] if g["kpi_type"] == d["kpi_type"] and sorted(g["markets"]) == sorted(d["markets"])]
    for g in targets:
        entry = _entry(cfg, g, d["run_date"], "duyệt bản nháp")
        entry.update(draft_id=draft_id, failing=d["failing"], author=d["author"])
        try:
            if live is not None and g["chat_id"] not in live:
                entry["status"] = "bỏ qua (Bot không còn trong nhóm)"
            else:
                entry["message_id"] = _post(bot, g["chat_id"], d["card"], d.get("image_key"))
                entry["status"] = "đã gửi"
        except Exception as e:
            log.exception("Gửi nhóm %s lỗi", g["name"])
            entry["status"], entry["error"] = "lỗi", str(e)[:500]
        log.info("%s → %s", g["name"], entry["status"])
        entries.append(entry)
    d["status"] = "đã gửi" if any(e["status"] == "đã gửi" for e in entries) else "lỗi gửi"
    d["sent_at"] = _now(cfg).isoformat(timespec="seconds")
    d["sent_to"] = [e["group"] for e in entries if e["status"] == "đã gửi"]
    save_drafts(drafts, sealer)
    _log(entries)
    return entries


def redraft(cfg, draft_id, sealer, by=""):
    """Viết lại bản nháp với dữ liệu mới nhất (vd. sau khi chỉnh KPI hoặc muốn AI viết lại)."""
    drafts = load_drafts()
    d = _find_draft(drafts, draft_id)
    report = metrics.build_report(date.fromisoformat(d["run_date"]), cfg)
    dash_url = _dashboard_url(cfg)
    b = compose(cfg, report, d["kpi_type"], d["markets"], dash_url, {})
    bot = [None]
    _ensure_image(b, bot)
    d.update(card=b["card"], html=b["html"], image_key=b["image_key"], image_error=b["image_error"],
             author=b["author"], ai_error=b["ai_error"], failing=b["failing"],
             status="chờ duyệt", rewritten_at=_now(cfg).isoformat(timespec="seconds"), rewritten_by=by or None)
    _notify_reviewer(cfg, d, bot, dash_url)
    save_drafts(drafts, sealer)


def reject(cfg, draft_id, sealer, by=""):
    drafts = load_drafts()
    d = _find_draft(drafts, draft_id)
    d["status"], d["rejected_at"] = "đã hủy", _now(cfg).isoformat(timespec="seconds")
    d["rejected_by"] = by or None
    save_drafts(drafts, sealer)


def _dow_match(spec: str, d: date) -> bool:
    if spec == "*":
        return True
    if spec == "mon-fri":
        return d.weekday() < 5
    return DOW_NAMES[d.weekday()] == spec


def last_occurrence(s: dict, now: datetime):
    for k in range(8):
        d = now.date() - timedelta(days=k)
        if _dow_match(s["day_of_week"], d):
            occ = datetime(d.year, d.month, d.day, s["hour"], s["minute"], tzinfo=now.tzinfo)
            if occ <= now:
                return occ
    return None


def due_jobs(cfg, now: datetime) -> list:
    """[(schedule, occurrence, group_ids còn phải gửi)] — nhóm đã gửi/bỏ qua ở lần này thì không gửi lại."""
    done = {(e.get("schedule_id"), e.get("occurrence"), e["group_id"])
            for e in _read_json(SEND_LOG, []) if e.get("status") != "lỗi"}
    jobs = []
    for s in cfg["schedules"]:
        if not s.get("enabled", True):
            continue
        occ = last_occurrence(s, now)
        if occ is None or now - occ > timedelta(hours=CATCHUP_HOURS):
            continue
        key = occ.isoformat()
        todo = [g["id"] for g in cfg["groups"] if (s["id"], key, g["id"]) not in done]
        if todo:
            jobs.append((s, occ, todo))
    return jobs


def tick(cfg):
    now = _now(cfg)
    sealer = _Sealer()
    live = sync_chats(cfg, sealer)  # rẻ: chỉ gọi Lark, không truy vấn BigQuery
    jobs = due_jobs(cfg, now)
    built = _read_json(BUILD_STATE, {}).get("built_at")
    age = now - datetime.fromisoformat(built) if built else None
    stale = age is None or age > timedelta(hours=BUILD_EVERY_HOURS)
    reports = {}
    # Đến lịch gửi thì làm mới dashboard luôn (trừ khi vừa build < 1 giờ, vd. lượt gửi lại nhóm bị lỗi)
    if stale or (jobs and age > timedelta(hours=1)):
        reports = build(cfg, sealer)
    for s, occ, todo in jobs:
        run_date = metrics.last_sunday(occ.date())
        send(cfg, run_date, todo, trigger=f"lịch: {s['name']}", schedule_id=s["id"],
             occurrence=occ.isoformat(), report=reports.get(run_date), live=live, sealer=sealer)
    if jobs:
        write_history(sealer)
    if not jobs and not stale:
        log.info("Không có việc: chưa đến lịch, dữ liệu dashboard còn mới (build lúc %s)", built)


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="pipeline.run")
    p.add_argument("cmd", choices=["tick", "build", "send", "test", "chats", "approve", "redraft", "reject"])
    p.add_argument("--date", help="Ngày T (YYYY-MM-DD), mặc định Chủ nhật gần nhất")
    p.add_argument("--groups", default="", help="chat_id nhóm (oc_...), cách nhau bởi dấu phẩy; trống = mọi nhóm đã đăng ký")
    p.add_argument("--draft", default="", help="mã bản nháp (approve / redraft / reject)")
    p.add_argument("--by", default="", help="tên Admin thực hiện (approve / redraft / reject), ghi vào bản nháp")
    a = p.parse_args(argv)
    cfg = config_mod.load()
    chat_ids = {x.strip() for x in a.groups.split(",") if x.strip()}
    group_ids = [g["id"] for g in cfg["groups"] if not chat_ids or g["chat_id"] in chat_ids]

    if a.cmd == "tick":
        tick(cfg)
    elif a.cmd == "build":
        sealer = _Sealer()
        sync_chats(cfg, sealer)
        build(cfg, sealer)
    elif a.cmd == "send":
        sealer = _Sealer()
        live = sync_chats(cfg, sealer)
        run_date = date.fromisoformat(a.date) if a.date else metrics.last_sunday(_now(cfg).date())
        entries = send(cfg, run_date, group_ids, trigger="gửi thủ công", live=live, sealer=sealer)
        write_history(sealer)
        if not entries:
            log.warning("Không có nhóm nào đăng ký nhận bản tin trong số đã chọn")
        if any(e["status"] == "lỗi" for e in entries):
            sys.exit(1)
    elif a.cmd in ("approve", "redraft", "reject"):
        if not a.draft:
            raise SystemExit("Thiếu --draft")
        sealer = _Sealer()
        if a.cmd == "approve":
            entries = approve(cfg, a.draft, sealer, a.by)
            write_history(sealer)
            if any(e["status"] == "lỗi" for e in entries):
                sys.exit(1)
        elif a.cmd == "redraft":
            redraft(cfg, a.draft, sealer, a.by)
        else:
            reject(cfg, a.draft, sealer, a.by)
    elif a.cmd == "test":
        live = sync_chats(cfg) or {}
        bot = _bot()
        for chat_id in sorted(chat_ids or {r["chat_id"] for r in cfg["recipients"]}):
            r = next((r for r in cfg["recipients"] if r["chat_id"] == chat_id), {})
            name = live.get(chat_id) or r.get("name") or chat_id
            bot.send_card(chat_id, test_card(name, [t for t in ("survival", "monthly") if r.get(t)]))
            log.info("Đã gửi tin kiểm tra tới %s", name)
    elif a.cmd == "chats":
        live = sync_chats(cfg)
        if live is None:
            sys.exit(1)
        for chat_id, name in live.items():
            print(f"{chat_id}\t{name}")


if __name__ == "__main__":
    main()
