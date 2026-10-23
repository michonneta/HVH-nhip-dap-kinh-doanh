"""Đọc và kiểm tra config/config.json (KPI, thời gian trung bình, nhóm Lark, lịch gửi)."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.getenv("CONFIG_PATH", ROOT / "config" / "config.json"))
DOW = {"mon", "tue", "wed", "thu", "fri", "sat", "sun", "mon-fri", "*"}


def load() -> dict:
    return validate(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))


def validate(cfg: dict) -> dict:
    for code, m in (cfg.get("markets") or {}).items():
        if not code.isalnum() or not code.isupper() or len(code) > 6:
            raise ValueError(f"Mã thị trường không hợp lệ: {code}")
        m["giao_days"] = int(m.get("giao_days", 8))
        m["chot_days"] = int(m.get("chot_days", 4))
        if not (0 <= m["giao_days"] <= 60 and 0 <= m["chot_days"] <= 60):
            raise ValueError(f"Thời gian trung bình của {code} phải trong khoảng 0–60 ngày")
        for metric, levels in (m.get("kpi") or {}).items():
            for lvl, v in list(levels.items()):
                if v is None or v == "":
                    levels[lvl] = None
                    continue
                v = float(v)
                if not 0 <= v <= 1:
                    raise ValueError(f"KPI {code}/{metric}/{lvl} phải trong khoảng 0–1")
                levels[lvl] = v
    cfg["window_days"] = int(cfg.get("window_days", 7))
    cfg.setdefault("timezone", "Asia/Ho_Chi_Minh")
    cfg.setdefault("dashboard_url", "")
    cfg["send_when_ok"] = bool(cfg.get("send_when_ok", False))
    # recipients: nhóm Lark (chat_id do Bot tự lấy) + loại bản tin nhóm muốn nhận
    seen = set()
    for r in cfg.setdefault("recipients", []):
        if not str(r.get("chat_id", "")).startswith("oc_"):
            raise ValueError(f"Nhóm {r.get('name')}: chat_id không hợp lệ")
        if r["chat_id"] in seen:
            raise ValueError(f"Nhóm {r.get('name')} bị khai báo trùng")
        seen.add(r["chat_id"])
        r.setdefault("name", r["chat_id"])
        r["survival"] = bool(r.get("survival"))
        r["monthly"] = bool(r.get("monthly"))
        r["markets"] = [m for m in r.get("markets", []) if m in cfg["markets"]]
    for s in cfg.get("schedules", []):
        s["hour"], s["minute"] = int(s.get("hour", 8)), int(s.get("minute", 0))
        if not (0 <= s["hour"] <= 23 and 0 <= s["minute"] <= 59):
            raise ValueError(f"Lịch {s.get('name')}: giờ/phút không hợp lệ")
        if s.get("day_of_week", "sun") not in DOW:
            raise ValueError(f"Lịch {s.get('name')}: ngày không hợp lệ ({s.get('day_of_week')})")
        s.setdefault("day_of_week", "sun")
        s.setdefault("enabled", True)
        s.pop("group_ids", None)  # lịch áp dụng cho mọi nhóm đã đăng ký
    cfg["groups"] = derive_groups(cfg)
    return cfg


def derive_groups(cfg: dict) -> list:
    """Mỗi (nhóm, loại KPI) đã tick thành một "đích gửi" cho bản tin."""
    out = []
    for r in cfg["recipients"]:
        for kpi_type in ("survival", "monthly"):
            if r[kpi_type]:
                out.append({"id": f"{r['chat_id']}:{kpi_type}", "name": r["name"], "chat_id": r["chat_id"],
                            "kpi_type": kpi_type, "markets": r["markets"],
                            "send_when_ok": cfg["send_when_ok"], "enabled": True})
    return out
