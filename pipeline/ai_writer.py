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

from .analysis import KPI_TYPE_LABEL, METRICS, fmt_date

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
    market: str
    metric: str
    what: list[str]
    why: list[str]
    impact: list[str]
    action: list[str]


class AIBulletin(BaseModel):
    opening: str
    conclusion: str
    key_points: list[str]
    sections: list[Section]
    closing: str


SYSTEM_PROMPT = """Bạn là Data Analyst của Phòng Dịch vụ khách hàng (P.DVKH) – HV HOLDINGS. Mỗi kỳ bạn đọc dữ liệu \
Dashboard "Nhịp đập kinh doanh" (tỷ lệ chốt, tỷ lệ giao của các thị trường ML, PH, CAM, TH, VN, ID) và viết bản tin \
gửi vào nhóm Lark của phòng.

Đối tượng đọc: trưởng nhóm và nhân viên vận hành, đọc trên điện thoại, cần biết ngay việc gì phải làm.

Cách viết:
- Theo Nguyên tắc Kim tự tháp (Barbara Minto): `conclusion` là điều quan trọng nhất trong 1–2 câu; `key_points` là \
3–5 luận điểm chính, mỗi ý gắn với một hành động; chi tiết để ở `sections`.
- Mỗi chỉ số không đạt KPI là một phần tử trong `sections`, sắp theo mức nghiêm trọng, đủ 4 cấp độ:
  `what` – điều gì đã xảy ra (giá trị, KPI, chênh lệch, so tuần trước);
  `why` – tại sao (cơ cấu hủy / đang xử lý / hoàn / đang giao, lý do hàng đầu);
  `impact` – nguyên nhân chính tác động bao nhiêu % tới phần thiếu hụt và hệ quả nếu kéo dài;
  `action` – nên làm gì, cụ thể ai/việc gì, ưu tiên theo tác động.
  Mỗi cấp độ 1–3 gạch đầu dòng ngắn. Hãy liên kết các chỉ số với nhau khi dữ liệu cho thấy (ví dụ tỷ lệ chốt thấp kéo \
tỷ lệ giao thành công từ data sạch xuống), đó là giá trị analyst mang lại so với bảng số.
- Giọng "loa phường" của bản tin "Nhịp đập kinh doanh": `opening` bắt đầu bằng "📣 **Alo alo!**", thân thiện, \
rõ ràng, không cường điệu; `closing` một câu hẹn bản tin sau và động viên đội.
- Nếu không có chỉ số nào dưới KPI: `sections` để trống, khen ngợi ngắn gọn và nêu điểm cần giữ hoặc rủi ro sớm \
(chỉ số giảm so với tuần trước) trong `key_points`.
- Định dạng: tiếng Việt, được dùng **in đậm** cho số liệu then chốt; không dùng tiêu đề markdown (#), không bảng.
- `market` là mã thị trường; `metric` là tên chỉ số đúng như trong dữ liệu.

Quy tắc số liệu (bắt buộc):
- Chỉ dùng con số có trong <du_lieu>, giữ nguyên giá trị; phần trăm viết dấu phẩy thập phân, ví dụ 77,9%.
- Không tự tính thêm con số mới (cộng, trừ, nhân, chia, làm tròn khác đi). Cần chênh lệch thì dùng trường có sẵn.
- Không suy đoán nguyên nhân ngoài dữ liệu như sự thật; nếu nêu giả thuyết thì ghi rõ "giả thuyết" và đề xuất cách kiểm chứng."""


def _r(x, nd=1):
    return None if x is None else round(x * 100, nd)


def build_facts(report: dict, kpi_type: str, s: dict) -> dict:
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


# ---------------------------------------------------------------- gọi Claude
_LIST = {"type": "array", "items": {"type": "string"}}
SCHEMA = {  # khuôn JSON tường minh (không $ref) cho Claude Code --json-schema
    "type": "object", "additionalProperties": False,
    "required": ["opening", "conclusion", "key_points", "sections", "closing"],
    "properties": {
        "opening": {"type": "string"}, "conclusion": {"type": "string"}, "key_points": _LIST,
        "closing": {"type": "string"},
        "sections": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["market", "metric", "what", "why", "impact", "action"],
            "properties": {"market": {"type": "string"}, "metric": {"type": "string"},
                           "what": _LIST, "why": _LIST, "impact": _LIST, "action": _LIST}}},
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


def write(report: dict, kpi_type: str, s: dict) -> dict:
    """Trả về dict AIBulletin đã qua kiểm tra số liệu; lỗi thì raise để bên gọi dùng mẫu."""
    facts = build_facts(report, kpi_type, s)
    prompt = build_prompt(facts)
    ai = _ask(prompt).model_dump()
    bad = unknown_numbers(ai, facts)
    if bad:
        log.warning("AI dùng số không có trong dữ liệu %s — yêu cầu viết lại", bad)
        note = ("\n\nLần viết trước đã dùng các con số không có trong <du_lieu>: "
                + ", ".join(f"{n:g}".replace(".", ",") for n in bad)
                + ". Lần này chỉ dùng đúng con số có sẵn trong dữ liệu, không tự tính thêm.")
        ai = _ask(prompt + note).model_dump()
        bad = unknown_numbers(ai, facts)
        if bad:
            raise ValueError(f"AI vẫn dùng số không có trong dữ liệu: {bad}")
    return ai
