"""Phân tích 4 cấp độ cho một chỉ số không đạt KPI.

Cấp 1: Điều gì đã xảy ra · Cấp 2: Tại sao · Cấp 3: Nguyên nhân chính, % tác động, hệ quả nếu kéo dài
Cấp 4: Chúng ta nên làm gì.
"""
import re

from .metrics import DIM_LABELS, METRICS

KPI_TYPE_LABEL = {"survival": "sinh tồn", "monthly": "tháng"}
PROJECT_WEEKS = 4
MIN_SEGMENT_DEN = 20  # bỏ qua phân khúc quá nhỏ khi tìm nguyên nhân chính
DOMINANT_SHARE = 0.8  # phân khúc chiếm >= 80% đơn thì gần như là cả thị trường, không chọn làm "nguyên nhân chính"
GENERIC_REASON = r"^(other reason|lý do khác|không xác định|khác|other|unknown)$"

# (regex lý do, đề xuất hành động)
REASON_PLAYBOOK = [
    (r"no answer|không nhấc|không nghe|did not pick|pick up|ไม่รับ|tidak dapat dihubungi|tidak diangkat|thuê bao|unreachable|cannot contact|không liên lạc|liên lạc",
     "Tăng số lần gọi lại và liên hệ đa kênh (SMS/Zalo/WhatsApp) với đơn chưa liên lạc được; xếp ca gọi vào khung giờ khách dễ nghe máy."),
    (r"nhu cầu|no need|changed.*mind|đổi ý|berubah|ต้องการ|want to cancel|batal",
     "Cùng Marketing rà soát chất lượng lead và thông điệp quảng cáo; cập nhật kịch bản xử lý từ chối cho telesale."),
    (r"trùng|duplicate|ซ้ำ",
     "Bổ sung lọc trùng tự động trước khi đẩy data cho telesale."),
    (r"sai|incorrect|salah|wrong number|non-existent|nomor telepon",
     "Bật kiểm tra định dạng SĐT (OTP/validate) tại form và landing page."),
    (r"bad history|lịch sử",
     "Áp dụng đặt cọc/chuyển khoản trước với khách có lịch sử bom hàng."),
    (r"island|not supp?ort cod|area",
     "Đề xuất thanh toán trước hoặc DVVC khác cho khu vực không hỗ trợ COD."),
    (r"hẹn|reschedule|deliver later",
     "Theo dõi danh sách đơn hẹn giao lại, nhắc khách 1 ngày trước khi phát lại."),
    (r"không để lại|didn.?t leave|tidak meninggalkan",
     "Kiểm tra nguồn ads/form có dấu hiệu lead ảo, chặn nguồn spam."),
    (r"sai sản phẩm|wrong product|wrong cod|giao chậm|late delivery|hỏng|damaged|fake",
     "Rà soát khâu đóng gói, đối chiếu COD và thời gian giao với kho/DVVC."),
]


def pct(x, digits=1):
    if x is None:
        return "–"
    return f"{x * 100:.{digits}f}%".replace(".", ",")


def pp(x, digits=1):
    """Điểm phần trăm có dấu."""
    if x is None:
        return "–"
    return f"{x * 100:+.{digits}f}".replace(".", ",") + " điểm %"


def num(n):
    return f"{n:,}".replace(",", ".")


def fmt_date(s):
    y, m, d = s.split("-")
    return f"{d}/{m}"


def _rate(row, metric):
    _, _, num, den = METRICS[metric]
    return row[num] / row[den] if row.get(den) else None


def _segment_shortfall(rows, metric, target):
    """Phần thiếu hụt (số đơn) so với KPI của từng phân khúc và % đóng góp."""
    _, _, num, den = METRICS[metric]
    items = []
    for r in rows:
        if r.get(den, 0) < MIN_SEGMENT_DEN or r["seg"] == "(trống)":
            continue
        missing = target * r[den] - r[num]
        items.append({"seg": r["seg"], "rate": r[num] / r[den], "den": r[den], "missing": missing})
    total_pos = sum(i["missing"] for i in items if i["missing"] > 0)
    for i in items:
        i["share"] = i["missing"] / total_pos if total_pos > 0 and i["missing"] > 0 else 0
    return sorted(items, key=lambda i: -i["missing"])


def _top_reasons(rows, col, limit=3):
    items = [r for r in rows if r["seg"] != "(trống)" and r.get(col, 0) > 0]
    total = sum(r[col] for r in rows if r.get(col, 0) > 0)
    items.sort(key=lambda r: -r[col])
    return [{"reason": r["seg"], "n": r[col], "share": r[col] / total if total else 0} for r in items[:limit]], total


def analyze(m: dict, metric: str, kpi_type: str) -> dict:
    """m: một phần tử trong report['markets']."""
    label, kind, _, _ = METRICS[metric]
    st = m["status"][kpi_type][metric]
    target = st["target"]
    mv = m["metrics"][metric]
    val, prev = mv["value"], mv["prev"]
    c = m["counts"][kind]
    bd = m["breakdown"].get(kind, {})
    w = m["windows"][kind]
    kpi_name = KPI_TYPE_LABEL[kpi_type]

    # ---- Cấp 1: Điều gì đã xảy ra
    l1 = [
        f"{label} đơn tạo {fmt_date(w[0])}–{fmt_date(w[1])} đạt **{pct(val)}** ({num(mv['num'])}/{num(mv['den'])} đơn), "
        f"thấp hơn KPI {kpi_name} {pct(target, 0)} **{pp(target - val).lstrip('+')}**."
    ]
    if prev is not None:
        trend = "giảm" if val < prev else "tăng"
        l1.append(f"So với tuần trước ({pct(prev)}): {trend} {pp(abs(val - prev)).lstrip('+')}.")

    # ---- Cấp 2: Tại sao
    l2 = []
    reasons = []  # (lý do, "hủy"/"hoàn", tỷ trọng) để tra cứu đề xuất ở cấp 4
    if metric == "chot":
        l2.append(
            f"Trong {num(c['clean'])} data sạch: {num(c['huy'])} đơn hủy ({pct(c['huy'] / c['clean'])}) "
            f"và {num(c['dang_xl'])} đơn còn đang xử lý ({pct(c['dang_xl'] / c['clean'])})."
        )
        top, _ = _top_reasons(bd.get("cancel_reason", []), "huy")
        if top:
            l2.append("Lý do hủy hàng đầu: " + "; ".join(
                f"{t['reason']} ({num(t['n'])} đơn, {pct(t['share'], 0)} đơn hủy)" for t in top) + ".")
            reasons += [(t["reason"], "hủy", t["share"]) for t in top]
    elif metric == "giao":
        shipping = c["giao_dvvc"] - c["gtc"] - c["hoan"]
        l2.append(
            f"Trong {num(c['giao_dvvc'])} đơn đã giao DVVC: {num(c['hoan'])} đơn hoàn ({pct(c['hoan'] / c['giao_dvvc'])}), "
            f"{num(shipping)} đơn vẫn đang giao ({pct(shipping / c['giao_dvvc'])}) dù đã quá thời gian giao trung bình."
        )
        top, _ = _top_reasons(bd.get("returned_reason", []), "hoan")
        if top:
            l2.append("Lý do hoàn hàng đầu: " + "; ".join(
                f"{t['reason']} ({num(t['n'])} đơn, {pct(t['share'], 0)} đơn hoàn)" for t in top) + ".")
            reasons += [(t["reason"], "hoàn", t["share"]) for t in top]
    else:  # gtc_clean
        shipping = c["giao_dvvc"] - c["gtc"] - c["hoan"]
        preship = c["cho_giao"] - shipping
        losses = [("hủy", c["huy"]), ("đang xử lý", c["dang_xl"]), ("chờ gửi kho", preship),
                  ("đang giao", shipping), ("hoàn", c["hoan"])]
        lost = sum(n for _, n in losses)
        if lost:
            parts = [f"{name} {num(n)} ({pct(n / lost, 0)})" for name, n in sorted(losses, key=lambda x: -x[1]) if n > 0]
            l2.append(f"{num(lost)}/{num(c['clean'])} data sạch chưa thành đơn giao thành công, gồm: " + ", ".join(parts) + ".")
        top_c, _ = _top_reasons(bd.get("cancel_reason", []), "huy", 2)
        top_r, _ = _top_reasons(bd.get("returned_reason", []), "hoan", 2)
        reasons += [(t["reason"], "hủy", t["share"]) for t in top_c] + [(t["reason"], "hoàn", t["share"]) for t in top_r]
        if top_c:
            l2.append("Hủy chủ yếu do: " + "; ".join(f"{t['reason']} ({num(t['n'])})" for t in top_c) + ".")
        if top_r:
            l2.append("Hoàn chủ yếu do: " + "; ".join(f"{t['reason']} ({num(t['n'])})" for t in top_r) + ".")

    # ---- Cấp 3: Nguyên nhân chính, % tác động, hệ quả
    l3 = []
    # DVVC chỉ có ý nghĩa với tỷ lệ giao (đơn hủy/đang xử lý chưa có DVVC)
    dims = ["sub_bu", "sales_channel"] + (["partner_name"] if metric == "giao" else [])
    main_driver = None
    for dim in dims:
        seg = _segment_shortfall(bd.get(dim, []), metric, target)
        worst = [s for s in seg if s["share"] > 0][:2]
        if not worst:
            continue
        for s in worst:
            # Phân khúc gần bằng cả thị trường thì không giúp khoanh vùng nguyên nhân
            if s["den"] < DOMINANT_SHARE * mv["den"] and (main_driver is None or s["share"] > main_driver["share"]):
                main_driver = {**s, "dim": dim}
        l3.append(f"{DIM_LABELS[dim]}: " + "; ".join(
            f"{s['seg']} đạt {pct(s['rate'])} trên {num(s['den'])} đơn, gánh **{pct(s['share'], 0)}** phần thiếu hụt"
            for s in worst) + ".")
    if metric == "chot":
        top, _ = _top_reasons(bd.get("cancel_reason", []), "huy", 1)
        if top and c["clean"]:
            l3.append(f"Riêng lý do \"{top[0]['reason']}\" làm mất {pp(top[0]['n'] / c['clean']).lstrip('+')} tỷ lệ chốt.")
    elif metric == "giao":
        top, _ = _top_reasons(bd.get("returned_reason", []), "hoan", 1)
        if top and c["giao_dvvc"]:
            l3.append(f"Riêng lý do \"{top[0]['reason']}\" làm mất {pp(top[0]['n'] / c['giao_dvvc']).lstrip('+')} tỷ lệ giao.")
    gap_orders = max(0, round((target - val) * mv["den"]))
    unit, effect = {
        "chot": ("đơn chốt", "data marketing bỏ ra không chuyển thành doanh thu"),
        "giao": ("đơn giao thành công", "chi phí vận chuyển 2 chiều và hàng hoàn tăng theo"),
        "gtc_clean": ("đơn giao thành công", "doanh thu thực nhận giảm tương ứng"),
    }[metric]
    l3.append(
        f"Nếu tiếp tục kéo dài: hụt ~{num(gap_orders)} {unit}/tuần so với KPI, tương đương "
        f"~{num(gap_orders * PROJECT_WEEKS)} {unit} sau {PROJECT_WEEKS} tuần; {effect}."
    )
    if metric == "chot":
        l3.append("Tỷ lệ chốt thấp sẽ kéo theo tỷ lệ giao thành công từ data sạch không đạt ở các tuần kế tiếp.")

    # ---- Cấp 4: Chúng ta nên làm gì
    l4 = []
    if main_driver:
        l4.append(
            f"Ưu tiên số 1: {DIM_LABELS[main_driver['dim']]} **{main_driver['seg']}** "
            f"(gánh {pct(main_driver['share'], 0)} thiếu hụt) — họp nhanh với owner, đặt mục tiêu đưa {label.lower()} "
            f"từ {pct(main_driver['rate'])} lên ≥ {pct(target, 0)} trong tuần tới."
        )
    seen = set()
    for reason, what, share in reasons:
        if re.search(GENERIC_REASON, reason.strip(), re.IGNORECASE):
            if share >= 0.3:
                l4.append(f"Chuẩn hóa ghi lý do {what}: {pct(share, 0)} đơn {what} đang ghi \"{reason}\" — yêu cầu "
                          f"{'telesale' if what == 'hủy' else 'DVVC/CSKH'} chọn lý do cụ thể để xác định đúng nguyên nhân.")
            continue
        for pattern, action in REASON_PLAYBOOK:
            if action not in seen and re.search(pattern, reason, re.IGNORECASE):
                l4.append(action)
                seen.add(action)
                break
    if metric == "chot" and c["clean"] and c["dang_xl"] / c["clean"] > 0.03:
        l4.append(f"Giải phóng {num(c['dang_xl'])} đơn còn ở trạng thái đang xử lý (quá {fmt_date(w[1])}).")
    if metric in ("giao", "gtc_clean"):
        shipping = c["giao_dvvc"] - c["gtc"] - c["hoan"]
        if c["giao_dvvc"] and shipping / c["giao_dvvc"] > 0.03:
            l4.append(f"Đốc thúc DVVC xử lý {num(shipping)} đơn đang giao quá thời gian trung bình.")
    if not l4:
        l4.append(f"Rà soát lại quy trình xử lý {label.lower()} cùng trưởng nhóm thị trường {m['market']}.")

    return {
        "market": m["market"], "metric": metric, "label": label, "kpi_type": kpi_type,
        "value": val, "target": target, "gap": val - target, "prev": prev,
        "gap_orders": gap_orders,
        "headline": (
            f"{label} {pct(val)} (KPI {pct(target, 0)}, {pp(val - target)})"
            + (f" — nguyên nhân chính: {DIM_LABELS[main_driver['dim']]} {main_driver['seg']} "
               f"({pct(main_driver['share'], 0)} thiếu hụt)" if main_driver else "")
        ),
        "levels": {"what": l1, "why": l2, "impact": l3, "action": l4[:5]},
    }


def alerts_for(report: dict, kpi_type: str, markets_filter=None) -> list:
    out = []
    for m in report["markets"]:
        if markets_filter and m["market"] not in markets_filter:
            continue
        for metric, st in m["status"][kpi_type].items():
            if st["ok"] is False:
                out.append(analyze(m, metric, kpi_type))
    out.sort(key=lambda a: a["gap"])
    return out
