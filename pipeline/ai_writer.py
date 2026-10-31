"""AI Analyst: gọi Claude để viết lời cho bản tin, và các bước kiểm tra chung.

Nguyên tắc:
- Code tính mọi con số; AI chỉ diễn giải, liên kết và đề xuất (nội dung cụ thể ở report_writer.py).
- Mọi con số AI viết ra phải có trong dữ liệu đầu vào (kiểm tra tự động); sai thì cho viết lại 1 lần,
  vẫn sai thì báo lỗi để bản tin quay về mẫu theo quy tắc.
"""
import json
import logging
import os
import re
import shutil
import subprocess

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


# "7/10 chỉ số", "3/5 thị trường", "3 chỉ số còn lại": bắt người đọc tự đoán là những chỉ số nào
_COUNTING = re.compile(r"\b\d+\s*/\s*\d+\s+(chỉ số|thị trường)|\b(\d+|hai|ba|bốn|năm)\s+chỉ số còn lại", re.IGNORECASE)


def counting_phrases(ai: dict) -> list:
    return sorted({m.group(0) for m in _COUNTING.finditer(json.dumps(ai, ensure_ascii=False))})


# ---------------------------------------------------------------- gọi Claude
def ask(system: str, schema: dict, model_cls, prompt: str):
    """Trả về đối tượng model_cls (pydantic) do Claude điền theo khuôn JSON `schema`."""
    if backend() == "claude-code":
        return _ask_claude_code(system, schema, model_cls, prompt)
    return _ask_api(system, model_cls, prompt)


def _ask_claude_code(system, schema, model_cls, prompt):
    """Chạy Claude Code CLI không tương tác, xác thực bằng CLAUDE_CODE_OAUTH_TOKEN (gói Claude Pro/Max)."""
    exe = shutil.which("claude")
    if not exe:
        log.info("Cài Claude Code CLI…")
        subprocess.run(["npm", "install", "-g", "@anthropic-ai/claude-code"], check=True, capture_output=True)
        exe = shutil.which("claude")
    cmd = [exe, "-p", "--output-format", "json", "--json-schema", json.dumps(schema),
           "--tools", "", "--no-session-persistence", "--system-prompt", system]
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
        raise RuntimeError(f"Claude Code không trả kết quả ({data.get('subtype')}): {str(data.get('result'))[:300]}")
    log.info("AI Analyst (Claude Code): %s", data.get("modelUsage", {}).keys())
    return model_cls.model_validate(data["structured_output"])


def _ask_api(system, model_cls, prompt):
    import anthropic
    resp = anthropic.Anthropic().messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=system,
        output_config={"effort": EFFORT},
        output_format=model_cls,
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


def ask_checked(system: str, schema: dict, model_cls, prompt: str, facts: dict) -> dict:
    """ask() + kiểm tra số liệu và cách gọi tên; sai thì cho viết lại 1 lần, vẫn sai số thì raise."""
    out = ask(system, schema, model_cls, prompt).model_dump()
    bad, counting = unknown_numbers(out, facts), counting_phrases(out)
    if bad or counting:
        log.warning("AI dùng số không có trong dữ liệu %s / câu đếm %s — yêu cầu viết lại", bad, counting)
        note = "\n\nLần viết trước chưa đạt:"
        if bad:
            note += ("\n- Dùng các con số không có trong <du_lieu>: " + ", ".join(f"{n:g}".replace(".", ",") for n in bad)
                     + ". Lần này chỉ dùng đúng con số có sẵn trong dữ liệu, không tự tính thêm.")
        if counting:
            note += ("\n- Có câu đếm thay cho gọi tên: " + "; ".join(counting)
                     + ". Viết rõ chỉ số và thị trường, ví dụ \"tỷ lệ chốt không đạt ở ML, VN\".")
        out = ask(system, schema, model_cls, prompt + note).model_dump()
        bad = unknown_numbers(out, facts)
        if bad:
            raise ValueError(f"AI vẫn dùng số không có trong dữ liệu: {bad}")
        if counting_phrases(out):  # chỉ là cách diễn đạt, không sai số: vẫn dùng bản AI
            log.warning("AI vẫn có câu đếm: %s", counting_phrases(out))
    return out
