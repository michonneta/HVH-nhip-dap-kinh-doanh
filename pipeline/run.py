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
from .analysis import alerts_for
from .bulletin import build_bulletin, test_card
from .config import ROOT

log = logging.getLogger("nhip-dap")
DATA_DIR = ROOT / "docs" / "data"
STATE_DIR = ROOT / "state"
SEND_LOG = STATE_DIR / "send_log.json"
BUILD_STATE = STATE_DIR / "build.json"
CHATS_STATE = STATE_DIR / "lark_chats.sha256"   # chỉ lưu dấu vân tay, tên nhóm nằm trong file đã mã hóa
TREND_WEEKS = 12          # số tuần trên biểu đồ xu hướng
REPORT_WEEKS = 4          # số tuần gần nhất được tính lại phân tích mỗi lần build (đơn còn đổi trạng thái)
KEEP_WEEKS = 26           # giữ file báo cáo tuần trong docs/data tối đa
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

    def write(self, name, obj):
        _write_json(DATA_DIR / name, self.enc.seal(obj) if self.enc else obj)


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
    sealer = sealer or _Sealer()
    latest = metrics.last_sunday(_now(cfg).date())
    sundays = [latest - timedelta(days=7 * i) for i in range(TREND_WEEKS)]
    summary = metrics.fetch_summary(sundays, cfg)
    dash_url = _dashboard_url(cfg)

    reports = {}
    for d in sundays[:REPORT_WEEKS]:
        report = reports[d] = metrics.build_report(d, cfg, summary=summary)
        public = {**report, "markets": [{k: v for k, v in m.items() if k != "breakdown"} for m in report["markets"]]}
        public["alerts"] = {t: alerts_for(report, t) for t in ("survival", "monthly")}
        # bản xem trước theo loại KPI (mọi thị trường)
        public["cards"] = {t: build_bulletin(report, {"name": "", "kpi_type": t, "markets": []}, dash_url)["card"]
                           for t in ("survival", "monthly")}
        sealer.write(f"report-{d}.json", public)

    cutoff = latest - timedelta(days=7 * KEEP_WEEKS)
    dates = []
    for f in sorted(DATA_DIR.glob("report-*.json")):
        d = date.fromisoformat(f.stem[len("report-"):])
        if d < cutoff:
            f.unlink()
        else:
            dates.append(str(d))

    sealer.write("trend.json", metrics.build_trend(sundays, cfg, summary))
    built_at = _now(cfg).isoformat(timespec="seconds")
    sealer.write("index.json", {
        "generated_at": built_at, "latest": str(latest), "dates": sorted(dates, reverse=True),
        "config": {k: v for k, v in cfg.items() if k != "groups"}, "dashboard_url": dash_url,
    })
    write_history(sealer)
    _write_json(BUILD_STATE, {"built_at": built_at})
    log.info("Đã build dashboard: %s tuần, mới nhất %s", len(dates), latest)
    return reports


def write_history(sealer):
    sealer.write("history.json", _read_json(SEND_LOG, [])[-200:][::-1])


# ---------------------------------------------------------------- gửi bản tin
def send(cfg, run_date: date, group_ids: list, trigger: str, schedule_id=None, occurrence=None, report=None,
         live=None) -> list:
    """live: {chat_id: tên} các nhóm Bot đang ở (None = không biết, cứ gửi)."""
    report = report or metrics.build_report(run_date, cfg)
    bot = None
    dash_url = _dashboard_url(cfg)
    entries = []
    for g in cfg["groups"]:
        if g["id"] not in group_ids:
            continue
        entry = {"at": _now(cfg).isoformat(timespec="seconds"), "trigger": trigger, "run_date": str(run_date),
                 "schedule_id": schedule_id, "occurrence": occurrence,
                 "group_id": g["id"], "group": g["name"], "kpi_type": g["kpi_type"]}
        try:
            b = build_bulletin(report, g, dash_url)
            entry.update(failing=b["failing"], alerts=len(b["alerts"]))
            if not g.get("enabled", True):
                entry["status"] = "bỏ qua (nhóm tắt)"
            elif not b["has_alert"] and not g.get("send_when_ok"):
                entry["status"] = "bỏ qua (đạt KPI)"
            elif live is not None and g["chat_id"] not in live:
                entry["status"] = "bỏ qua (Bot không còn trong nhóm)"  # không thử lại mỗi 30 phút
            else:
                bot = bot or _bot()
                entry["message_id"] = bot.send_card(g["chat_id"], b["card"])
                entry["status"] = "đã gửi"
        except Exception as e:  # lỗi một nhóm không chặn các nhóm khác
            log.exception("Gửi nhóm %s lỗi", g["name"])
            entry["status"] = "lỗi"
            entry["error"] = str(e)[:500]
        log.info("%s → %s", g["name"], entry["status"])
        entries.append(entry)
    _write_json(SEND_LOG, (_read_json(SEND_LOG, []) + entries)[-1000:])
    return entries


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
             occurrence=occ.isoformat(), report=reports.get(run_date), live=live)
    if jobs:
        write_history(sealer)
    if not jobs and not stale:
        log.info("Không có việc: chưa đến lịch, dữ liệu dashboard còn mới (build lúc %s)", built)


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="pipeline.run")
    p.add_argument("cmd", choices=["tick", "build", "send", "test", "chats"])
    p.add_argument("--date", help="Ngày T (YYYY-MM-DD), mặc định Chủ nhật gần nhất")
    p.add_argument("--groups", default="", help="chat_id nhóm (oc_...), cách nhau bởi dấu phẩy; trống = mọi nhóm đã đăng ký")
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
        entries = send(cfg, run_date, group_ids, trigger="gửi thủ công", live=live)
        write_history(sealer)
        if not entries:
            log.warning("Không có nhóm nào đăng ký nhận bản tin trong số đã chọn")
        if any(e["status"] == "lỗi" for e in entries):
            sys.exit(1)
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
