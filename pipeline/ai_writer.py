"""AI Analyst: đọc dữ liệu đứng sau Dashboard và viết bản tin phân tích (Claude API).

Nguyên tắc:
- Code tính mọi con số (chỉ số, KPI, phân khúc gây thiếu hụt); AI chỉ diễn giải, liên kết và đề xuất.
- Mọi con số AI viết ra phải có trong dữ liệu đầu vào (kiểm tra tự động); sai thì cho viết lại 1 lần,
  vẫn sai thì báo lỗi để bản tin quay về mẫu theo quy tắc.
"""
import json
import logging
import os
import re
import shutil
import subprocess

from pydantic import BaseModel

from .analysis import KPI_TYPE_LABEL, METRICS, PROJECT_WEEKS, fmt_date, money

log = logging.getLogger("nhip-dap")
MODEL = os.getenv("AI_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("AI_EFFORT", "high")


def backend() -> str:
    """'api' (ANTHROPIC_API_KEY, tính phí theo API) | 'claude-code' (CLAUDE_CODE_OAUTH_TOKEN, dùng gói Claude Pro/Max) | ''"""
    if os.getenv("ANTHROPIC_API_KEY"):
        return "api"
    if os.getenv("CLAUDE_CODE_OAUTH_TOKEN"):
        return "claude-code"
    return ""


class Section(BaseModel):
    """Một dòng của bảng bản tin (một chỉ số không đạt của một thị trường)."""
    market: str
    metric: str
    causes: list[str]   # cột Nguyên nhân
    actions: list[str]  # cột Gợi ý hành động


class AIBulletin(BaseModel):
    hot: str     # NÓNG
    watch: str   # LƯU Ý
    good: str    # TIN VUI
    sections: list[Section]


SYSTEM_PROMPT = """Bạn là Data Analyst của Phòng Dịch vụ khách hàng (P.DVKH) – HV HOLDINGS. Mỗi kỳ bạn đọc dữ liệu \
Dashboard "Nhịp đập kinh doanh" (tỷ lệ chốt, tỷ lệ giao của các thị trường ML, PH, CAM, TH, VN, ID) và viết bản tin \
gửi vào nhóm Lark của phòng.

Đối tượng đọc: trưởng nhóm và nhân viên vận hành, đọc trên điện thoại, cần biết ngay việc gì phải làm.

Cách viết:
- Phần tóm tắt đầu bản tin theo Nguyên tắc Kim tự tháp (Barbara Minto), mỗi mục 1–3 câu ngắn, điều quan trọng nhất \
nói trước. Với mỗi chỉ số được nhắc tới phải đủ 3 ý: điều gì xảy ra (số liệu then chốt) → nguyên nhân chính (kèm \
`ty_trong_pct`) → tác động, ghi rõ "hụt doanh thu `doanh_thu_thieu_hut_moi_tuan`/tuần" (có thể thêm \
`doanh_thu_thieu_hut_4_tuan` nếu kéo dài):
  `hot` – NÓNG: các chỉ số có `muc_do` = "Không đạt KPI" (thiếu nhiều), thị trường nặng nhất trước;
  `watch` – LƯU Ý: chỉ số `muc_do` = "Gần đạt", chỉ số đạt nhưng sát ngưỡng (vượt KPI rất ít) hoặc giảm mạnh so với \
tuần trước;
  `good` – TIN VUI: thị trường đạt toàn bộ chỉ số, chỉ số vượt KPI rõ hoặc cải thiện so với tuần trước.
  Mục nào không có nội dung thì để chuỗi rỗng. Chi tiết nằm trong bảng.
- Bản tin hiển thị dạng BẢNG, mỗi chỉ số không đạt KPI là một dòng (một phần tử `sections`, đủ mọi cảnh báo trong \
dữ liệu). Code đã tự điền cột Thực hiện (giá trị, KPI, chênh lệch); bạn viết 2 cột:
  `causes` – Nguyên nhân: 3–4 gạch đầu dòng ngắn. Mỗi nguyên nhân phải nêu chiếm bao nhiêu % ảnh hưởng: lấy từ \
`nguyen_nhan_mat_don` (`ty_trong_pct` = % trên tổng đơn bị mất, kèm số đơn và `doanh_thu_mat_moi_tuan`) hoặc phân \
khúc Sub BU / kênh / DVVC "gánh X% phần thiếu hụt" trong `phat_hien_tinh_san`. Gạch đầu dòng CUỐI CÙNG luôn là hệ \
quả nếu tiếp tục: "Nếu kéo dài 4 tuần: hụt ~`don_thieu_hut_4_tuan` đơn, hụt doanh thu ~`doanh_thu_thieu_hut_4_tuan`" \
(doanh thu = đơn thiếu hụt × `doanh_thu_tb_moi_don`, đã trừ chiết khấu và VAT);
  `actions` – Gợi ý hành động: 2–3 gạch đầu dòng, cụ thể ai làm gì, ưu tiên theo tác động.
  Mỗi gạch đầu dòng tối đa khoảng 25 từ (ô bảng hẹp, đọc trên điện thoại). Không lặp lại giá trị và KPI của dòng đó. \
Hãy liên kết các chỉ số với nhau khi dữ liệu cho thấy (ví dụ tỷ lệ chốt thấp kéo tỷ lệ giao thành công từ data sạch \
xuống), đó là giá trị analyst mang lại so với bảng số.
- Giọng "loa phường" của bản tin "Nhịp đập kinh doanh": thân thiện, rõ ràng, không cường điệu.
- Nếu không có chỉ số nào dưới KPI: `sections` để trống, `hot` rỗng, khen ngợi trong `good` và nêu rủi ro sớm \
(chỉ số giảm so với tuần trước) trong `watch`.
- Định dạng: tiếng Việt, được dùng **in đậm** cho số liệu then chốt; không dùng tiêu đề markdown (#), không bảng.
- `market` là mã thị trường; `metric` là tên chỉ số đúng như trường `chi_so` trong `canh_bao`.

Quy tắc số liệu (bắt buộc):
- Chỉ dùng con số có trong <du_lieu>, giữ nguyên giá trị; phần trăm viết dấu phẩy thập phân, ví dụ 77,9%. \
Doanh thu chép nguyên chuỗi có sẵn (ví dụ "48,3 triệu đ", "1,25 tỷ đ"), không làm tròn lại.
- Số tiền luôn đi ngay sau cụm "hụt doanh thu" (không dùng "mất doanh thu" hay cách nói khác), ví dụ "hụt doanh thu 45,9 triệu đ/tuần", \
"Hủy chiếm 63% (252 đơn, hụt doanh thu 96,4 triệu đ/tuần)". Không viết trống kiểu "hụt 45,9 triệu đ".
- Không tự tính thêm con số mới (cộng, trừ, nhân, chia, làm tròn khác đi). Cần chênh lệch thì dùng trường có sẵn.
- Không suy đoán nguyên nhân ngoài dữ liệu như sự thật; nếu nêu giả thuyết thì ghi rõ "giả thuyết" và đề xuất cách kiểm chứng."""


def _r(x, nd=1):
    return None if x is None else round(x * 100, nd)


def build_facts(report: dict, kpi_type: str, s: dict, near_pp: float = 2) -> dict:
    """Bộ dữ liệu AI được đọc: đúng những gì Dashboard hiển thị cho phạm vi bản tin."""
    markets = []
    for m in s["scope"]:
        chi_so = {}
        for mk, mv in m["metrics"].items():
            st = m["status"][kpi_type].get(mk)
            chi_so[METRICS[mk][0]] = {
                "gia_tri_pct": _r(mv["value"]), "tuan_truoc_pct": _r(mv["prev"]),
                "chenh_lech_tuan_truoc_diem_pct": None if mv["value"] is None or mv["prev"] is None
                else round((mv["value"] - mv["prev"]) * 100, 1),
                "tu_so": mv["num"], "mau_so": mv["den"],
                **({"kpi_pct": _r(st["target"], 1), "dat_kpi": st["ok"],
                    "chenh_lech_kpi_diem_pct": None if st["gap"] is None else round(st["gap"] * 100, 1)}
                   if st and st["target"] is not None else {}),
            }
        markets.append({
            "thi_truong": m["market"],
            "cua_so_don_tao": {"chot": [fmt_date(x) for x in m["windows"]["chot"]],
                               "giao": [fmt_date(x) for x in m["windows"]["giao"]]},
            "chi_so": chi_so,
        })
    findings = [{
        "thi_truong": a["market"], "chi_so": a["label"], "gia_tri_pct": _r(a["value"]), "kpi_pct": _r(a["target"]),
        "chenh_lech_kpi_diem_pct": round(a["gap"] * 100, 1), "don_thieu_hut_moi_tuan": a["gap_orders"],
        "muc_do": "Gần đạt" if a["gap"] > -near_pp / 100 else "Không đạt KPI",
        "don_thieu_hut_4_tuan": a["gap_orders"] * PROJECT_WEEKS,
        "doanh_thu_tb_moi_don": money(a["revenue"]["aov"]),
        "doanh_thu_thieu_hut_moi_tuan": money(a["revenue"]["gap_week"]),
        "doanh_thu_thieu_hut_4_tuan": money(a["revenue"]["gap_period"]),
        "nguyen_nhan_mat_don": [{
            "nguyen_nhan": x["name"], "so_don": x["orders"], "ty_trong_pct": _r(x["share"], 0),
            "doanh_thu_mat_moi_tuan": money(x["rev_week"]), "doanh_thu_mat_4_tuan": money(x["rev_period"]),
        } for x in a["causes"]],
        "phat_hien_tinh_san": a["levels"],
    } for a in s["alerts"]]
    return {
        "ky_bao_cao": f"T = {fmt_date(report['run_date'])}/{report['run_date'][:4]} (Chủ nhật)",
        "loai_kpi": KPI_TYPE_LABEL[kpi_type],
        "dinh_nghia": "Chỉ số tính trên đơn duy nhất từ data sạch, theo ngày tạo đơn; tỷ lệ chốt dùng cửa sổ chốt, "
                      "các tỷ lệ giao dùng cửa sổ giao (7 ngày, lùi theo thời gian trung bình chốt/giao).",
        "thi_truong_khong_dat": s["failing"], "thi_truong_dat": s["passing"],
        "du_lieu_thi_truong": markets,
        "canh_bao": findings,
    }


# ---------------------------------------------------------------- kiểm tra số liệu
# Trong bài AI: bỏ qua số dính "/" (ngày 08/10, phân số 433/556 — các vế đã có trong dữ liệu).
_NUM = re.compile(r"(?<![\w/.,])(\d{1,3}(?:\.\d{3})+|\d+(?:,\d+)?)(?![\w/])")
# Trong dữ liệu: lấy cả số trong phân số ("400/1.000 data sạch") để làm danh sách số hợp lệ.
_NUM_ALL = re.compile(r"(?<![\w.,])(\d{1,3}(?:\.\d{3})+|\d+(?:,\d+)?)(?!\w)")


def _numbers_in(text: str, pattern=_NUM) -> list:
    out = []
    for m in pattern.finditer(text):
        tok = m.group(1)
        if "." in tok and "," not in tok:          # 1.234 = nghìn kiểu Việt
            out.append(float(tok.replace(".", "")))
        else:
            out.append(float(tok.replace(",", ".")))
    return out


def _allowed(facts) -> set:
    vals = set()

    def walk(x):
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            vals.add(round(float(x), 1)); vals.add(round(abs(float(x)), 1))
        elif isinstance(x, str):
            for n in _numbers_in(x, _NUM_ALL):
                vals.add(round(n, 1))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(facts)
    return vals


def unknown_numbers(ai: dict, facts: dict) -> list:
    allowed = _allowed(facts)
    bad = []
    for n in _numbers_in(json.dumps(ai, ensure_ascii=False)):
        if n <= 12 and n == int(n):        # số thứ tự, số tuần, "1–3 việc"…
            continue
        if not any(abs(n - a) <= 0.051 for a in allowed):
            bad.append(n)
    return sorted(set(bad))


_MONEY = re.compile(r"\d[\d.,]*\s*(?:triệu|tỷ)\s*đ")


def unlabeled_money(ai: dict) -> list:
    """Số tiền không có cụm "hụt doanh thu" ngay phía trước (vd "hụt 45,9 triệu đ" thay vì "hụt doanh thu 45,9 triệu đ")."""
    bad = []
    for text in [ai["hot"], ai["watch"], ai["good"]] + [x for s in ai["sections"] for x in s["causes"] + s["actions"]]:
        for m in _MONEY.finditer(text):
            before = re.sub(r"[*~]", "", text[max(0, m.start() - 30):m.start()]).lower()
            if "hụt doanh thu" not in before:
                bad.append(m.group(0))
    return bad


# ---------------------------------------------------------------- gọi Claude
_LIST = {"type": "array", "items": {"type": "string"}}
SCHEMA = {  # khuôn JSON tường minh (không $ref) cho Claude Code --json-schema
    "type": "object", "additionalProperties": False,
    "required": ["hot", "watch", "good", "sections"],
    "properties": {
        "hot": {"type": "string"}, "watch": {"type": "string"}, "good": {"type": "string"},
        "sections": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["market", "metric", "causes", "actions"],
            "properties": {"market": {"type": "string"}, "metric": {"type": "string"},
                           "causes": _LIST, "actions": _LIST}}},
    },
}


def _ask_claude_code(prompt: str) -> AIBulletin:
    """Chạy Claude Code CLI không tương tác, xác thực bằng CLAUDE_CODE_OAUTH_TOKEN (gói Claude Pro/Max)."""
    exe = shutil.which("claude")
    if not exe:
        log.info("Cài Claude Code CLI…")
        subprocess.run(["npm", "install", "-g", "@anthropic-ai/claude-code"], check=True, capture_output=True)
        exe = shutil.which("claude")
    cmd = [exe, "-p", "--output-format", "json", "--json-schema", json.dumps(SCHEMA),
           "--tools", "", "--no-session-persistence", "--system-prompt", SYSTEM_PROMPT]
    if os.getenv("AI_MODEL"):
        cmd += ["--model", os.environ["AI_MODEL"]]
    # secret trống vẫn thành biến môi trường rỗng; bỏ đi để CLI dùng OAuth token của gói Pro
    env = {k: v for k, v in os.environ.items() if not (k.startswith("ANTHROPIC_") and not v)}
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=900, env=env)
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        raise RuntimeError(f"Claude Code lỗi (mã {proc.returncode}): {(proc.stderr or proc.stdout)[-300:]}")
    if data.get("is_error") or data.get("subtype") != "success" or not data.get("structured_output"):
        raise RuntimeError(f"Claude Code không trả bản tin ({data.get('subtype')}): {str(data.get('result'))[:300]}")
    log.info("AI Analyst (Claude Code): %s", data.get("modelUsage", {}).keys())
    return AIBulletin.model_validate(data["structured_output"])


def _ask(prompt: str) -> AIBulletin:
    if backend() == "claude-code":
        return _ask_claude_code(prompt)
    return _ask_api(prompt)


def _ask_api(prompt: str) -> AIBulletin:
    import anthropic
    resp = anthropic.Anthropic().messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        output_config={"effort": EFFORT},
        output_format=AIBulletin,
        messages=[{"role": "user", "content": prompt}],
        # Bị từ chối do bộ lọc an toàn thì API tự chạy lại trên model dự phòng
        extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
        extra_body={"fallbacks": "default"},
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"Claude từ chối viết bản tin ({getattr(resp.stop_details, 'category', None)})")
    if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
        raise RuntimeError(f"Bản tin AI không hoàn chỉnh (stop_reason={resp.stop_reason})")
    log.info("AI Analyst: %s input / %s output tokens", resp.usage.input_tokens, resp.usage.output_tokens)
    return resp.parsed_output


def build_prompt(facts: dict) -> str:
    return ("Viết bản tin kỳ này từ dữ liệu Dashboard dưới đây.\n<du_lieu>\n"
            + json.dumps(facts, ensure_ascii=False, indent=1) + "\n</du_lieu>")


def write(report: dict, kpi_type: str, s: dict, near_pp: float = 2) -> dict:
    """Trả về dict AIBulletin đã qua kiểm tra số liệu; lỗi thì raise để bên gọi dùng mẫu."""
    facts = build_facts(report, kpi_type, s, near_pp)
    prompt = build_prompt(facts)
    ai = _ask(prompt).model_dump()
    bad, unlabeled = unknown_numbers(ai, facts), unlabeled_money(ai)
    if bad or unlabeled:
        log.warning("AI dùng số không có trong dữ liệu %s / số tiền thiếu chữ 'hụt doanh thu' %s — yêu cầu viết lại",
                    bad, unlabeled)
        note = "\n\nLần viết trước chưa đạt:"
        if bad:
            note += ("\n- Dùng các con số không có trong <du_lieu>: " + ", ".join(f"{n:g}".replace(".", ",") for n in bad)
                     + ". Lần này chỉ dùng đúng con số có sẵn trong dữ liệu, không tự tính thêm.")
        if unlabeled:
            note += ("\n- Số tiền thiếu cụm \"hụt doanh thu\" phía trước: " + ", ".join(unlabeled)
                     + ". Viết dạng \"hụt doanh thu 45,9 triệu đ/tuần\".")
        ai = _ask(prompt + note).model_dump()
        bad = unknown_numbers(ai, facts)
        if bad:
            raise ValueError(f"AI vẫn dùng số không có trong dữ liệu: {bad}")
        if unlabeled_money(ai):  # chỉ là cách diễn đạt, không sai số: vẫn dùng bản AI
            log.warning("AI vẫn có số tiền thiếu chữ 'hụt doanh thu': %s", unlabeled_money(ai))
    return ai
