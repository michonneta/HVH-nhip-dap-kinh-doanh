"""Mô hình số liệu cho Bản tin "Nhịp đập kinh doanh" theo hồ sơ nội dung của Dashboard.

Bốn câu hỏi: tỷ lệ chốt / tỷ lệ giao có đạt KPI không, có tốt hơn kỳ trước không, chưa đạt vì sao, hụt bao nhiêu doanh thu.
Code tính mọi con số, bảng và dữ liệu biểu đồ ở đây; AI (report_writer) chỉ viết lời dựa trên mô hình này.
"""
import math
from datetime import date, timedelta

from .analysis import DOMINANT_SHARE, KPI_TYPE_LABEL, MIN_SEGMENT_DEN, fmt_date
from .reasons import UNKNOWN, grouped

# metric: (tên, cửa sổ, tử số, mẫu số)
METRIC = {"chot": ("Tỷ lệ chốt", "chot", "chot", "clean"), "giao": ("Tỷ lệ giao", "giao", "gtc", "giao_dvvc")}
SHORT = {"chot": "Chốt", "giao": "Giao"}
PROJECT_WEEKS = 4
DOW_VI = ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật"]


# ---------------------------------------------------------------- định dạng kiểu Việt Nam
def p1(x):
    """Tỷ lệ 0..1 → "85,9%"."""
    return "–" if x is None else f"{x * 100:.1f}%".replace(".", ",")


def p0(x):
    return "–" if x is None else f"{x * 100:.0f}%"


def pts(x, sign=True):
    """Chênh lệch tỷ lệ (0..1) → "+3,0" / "-4,1" điểm %."""
    if x is None:
        return "–"
    v = round(x * 100, 1)
    return (f"{v:+.1f}" if sign else f"{abs(v):.1f}").replace(".", ",")


def n0(n):
    return f"{n:,.0f}".replace(",", ".")


def tr(v):
    """Đồng → "17,5" (triệu)."""
    return f"{v / 1e6:.1f}".replace(".", ",")


def vnd(v):
    return f"{n0(round(v))} đ"


def _half_up(x):
    return int(math.floor(x + 0.5))


# ---------------------------------------------------------------- tính toán
def _aov(c):
    return c["doanh_thu"] / c["don_dt"] if c.get("don_dt") else None


def gap_orders(target, den, num):
    """Đơn thiếu so với KPI (dùng tính tiền): làm tròn."""
    return max(0, _half_up(target * den - num))


def need_orders(target, den, num):
    """Số đơn cần thêm để đạt KPI: làm tròn lên rồi kiểm tra lại bằng phép chia."""
    if not den or num / den >= target:
        return 0
    n = max(0, math.ceil(target * den - num - 1e-9))
    while (num + n) / den < target:
        n += 1
    return n


def shortfall(rows, numc, denc, target, total_den):
    """Phân khúc gánh phần thiếu: [{seg, rate, den, share}] giảm dần theo phần thiếu.

    Bỏ phân khúc dưới MIN_SEGMENT_DEN đơn, phân khúc "(trống)" và phân khúc gần bằng cả thị trường (≥ DOMINANT_SHARE).
    """
    items = []
    for r in rows:
        den = r.get(denc, 0)
        if den < MIN_SEGMENT_DEN or r["seg"] == "(trống)" or den >= DOMINANT_SHARE * total_den:
            continue
        items.append({"seg": r["seg"], "rate": r[numc] / den, "den": den, "missing": target * den - r[numc]})
    pos = sum(i["missing"] for i in items if i["missing"] > 0)
    out = [{**i, "share": i["missing"] / pos} for i in items if i["missing"] > 0 and pos > 0]
    return sorted(out, key=lambda i: -i["missing"])


def _cell(m, k, kpi_type):
    label, kind, numc, denc = METRIC[k]
    st = m["status"][kpi_type][k]
    if st["target"] is None or m["metrics"][k]["value"] is None:
        return None
    mv, c, cp = m["metrics"][k], m["counts"][kind], m["counts_prev"][kind]
    t = st["target"]
    cell = {
        "market": m["market"], "metric": k, "label": label, "short": f"{SHORT[k]} {m['market']}",
        "value": mv["value"], "prev": mv["prev"], "target": t, "met": mv["value"] >= t,
        "gap": mv["value"] - t, "delta": None if mv["prev"] is None else mv["value"] - mv["prev"],
        "num": mv["num"], "den": mv["den"], "window": m["windows"][kind],
        "gap_orders": 0, "need_orders": 0, "aov": _aov(c), "rev": 0.0, "rev_prev": 0.0,
    }
    if not cell["met"]:
        cell["gap_orders"] = gap_orders(t, mv["den"], mv["num"])
        cell["need_orders"] = need_orders(t, mv["den"], mv["num"])
        cell["rev"] = cell["gap_orders"] * (cell["aov"] or 0)
    if cp.get(denc) and cp[numc] / cp[denc] < t:  # kỳ trước chưa đạt: hụt kỳ trước để so sánh
        cell["rev_prev"] = gap_orders(t, cp[denc], cp[numc]) * (_aov(cp) or 0)
    return cell


def _chot_why(m, cell):
    c, bd = m["counts"]["chot"], m["breakdown"].get("chot", {})
    reasons = grouped(bd.get("cancel_reason", []), "huy")
    huy = c["huy"] or 1
    named = [(r, n) for r, n in reasons if r != "(trống)"]
    get = lambda name: next((n for r, n in reasons if r == name), 0)
    return {
        "cancels": c["huy"], "processing": c["dang_xl"],
        "reasons": [{"reason": r, "n": n, "share": n / huy} for r, n in named[:6]],
        "unknown": {"n": get(UNKNOWN) + get("(trống)"), "share": (get(UNKNOWN) + get("(trống)")) / huy},
        "bom_cod": {"n": get("Bom hàng") + get("Không hỗ trợ COD"), "share": (get("Bom hàng") + get("Không hỗ trợ COD")) / huy},
        "channels": shortfall(bd.get("sales_channel", []), "chot", "clean", cell["target"], cell["den"])[:3],
        "sub_bu": shortfall(bd.get("sub_bu", []), "chot", "clean", cell["target"], cell["den"])[:3],
    }


def _giao_why(m, cell, fate):
    c, bd = m["counts"]["giao"], m["breakdown"].get("giao", {})
    lost = c["giao_dvvc"] - c["gtc"]
    overdue = c["giao_dvvc"] - c["gtc"] - c["hoan"]
    with_reason = sum(r["hoan"] for r in bd.get("returned_reason", []) if r["seg"] != "(trống)")
    carriers = []
    for r in sorted(bd.get("partner_name", []), key=lambda r: -r.get("giao_dvvc", 0)):
        if r["seg"] == "(trống)" or r.get("giao_dvvc", 0) < MIN_SEGMENT_DEN:
            continue
        carriers.append({"name": r["seg"], "dvvc": r["giao_dvvc"], "rate": r["gtc"] / r["giao_dvvc"],
                         "diff": r["gtc"] / r["giao_dvvc"] - cell["target"],
                         "overdue": r["giao_dvvc"] - r["gtc"] - r["hoan"], "returns": r["hoan"]})
    return {
        "dvvc": c["giao_dvvc"], "lost": lost, "overdue": overdue, "returns": c["hoan"],
        "overdue_share": overdue / lost if lost else 0, "returns_share": c["hoan"] / lost if lost else 0,
        "returns_with_reason": with_reason,
        "overdue_rev": overdue * (cell["aov"] or 0),
        "carriers": carriers[:5],
        "channels": shortfall(bd.get("sales_channel", []), "gtc", "giao_dvvc", cell["target"], cell["den"])[:3],
        "fate": fate,
    }


def _fate(m, snap):
    """Nhóm đơn quá hạn kỳ trước: so số liệu lúc gửi bản tin kỳ trước (snapshot) với hiện tại."""
    if not snap:
        return None
    now = m["counts_prev"]["giao"]
    then_overdue = snap["giao_dvvc"] - snap["gtc"] - snap["hoan"]
    if then_overdue < 10:
        return None
    return {"overdue_then": then_overdue, "returned": max(0, now["hoan"] - snap["hoan"]),
            "delivered": max(0, now["gtc"] - snap["gtc"]), "still": now["giao_dvvc"] - now["gtc"] - now["hoan"],
            "then_at": snap.get("at", "")}


def snapshot_of(report: dict, at: str) -> dict:
    """Số liệu cửa sổ giao hiện tại của từng thị trường, lưu lại để tuần sau xem đơn quá hạn đi về đâu."""
    return {m["market"]: {**{k: m["counts"]["giao"][k] for k in ("giao_dvvc", "gtc", "hoan")}, "at": at}
            for m in report["markets"]}


def deadlines(run_date: date) -> dict:
    d = lambda k: run_date + timedelta(days=k)
    fmt = lambda x: f"{DOW_VI[x.weekday()]} {x:%d/%m}"
    return {"quyet_dinh": fmt(d(2)), "viec_gap": f"{d(2):%d/%m}", "viec_tuan": f"{d(3):%d/%m}", "viec_dai": f"{d(7):%d/%m}"}


def build_model(report: dict, kpi_type: str, markets: list, near_pp: float, prev_snapshot: dict = None) -> dict:
    run = date.fromisoformat(report["run_date"])
    scope = [m for m in report["markets"]
             if (not markets or m["market"] in markets)
             and any(s["target"] is not None for s in m["status"][kpi_type].values() if s)
             and "chot" in m["status"][kpi_type]]
    rows = []
    for m in scope:
        cells = {k: _cell(m, k, kpi_type) for k in METRIC}
        rows.append({"market": m["market"], **cells,
                     "return_rate": {"cur": _safe(m["counts"]["giao"], "hoan", "giao_dvvc"),
                                     "prev": _safe(m["counts_prev"]["giao"], "hoan", "giao_dvvc")}})
    cells = [r[k] for r in rows for k in METRIC if r[k]]
    failing = sorted([c for c in cells if not c["met"]], key=lambda c: -c["rev"])
    recovered = [c for c in cells if c["met"] and c["rev_prev"] > 0]

    def overall(k, period):
        _, kind, numc, denc = METRIC[k]
        src = "counts" if period == "cur" else "counts_prev"
        num = sum(m[src][kind][numc] for m in scope if m["status"][kpi_type][k]["target"] is not None)
        den = sum(m[src][kind][denc] for m in scope if m["status"][kpi_type][k]["target"] is not None)
        return num / den if den else None

    ov = {k: {"cur": overall(k, "cur"), "prev": overall(k, "prev")} for k in METRIC}
    for k in METRIC:
        ov[k]["delta"] = None if ov[k]["prev"] is None or ov[k]["cur"] is None else ov[k]["cur"] - ov[k]["prev"]
        ov[k]["met"] = [r["market"] for r in rows if r[k] and r[k]["met"]]
        ov[k]["failing"] = [r["market"] for r in rows if r[k] and not r[k]["met"]]
        ov[k]["recovered"] = [c["market"] for c in recovered if c["metric"] == k]

    progress = max(rows, key=lambda r: sum((r[k]["delta"] or 0) for k in METRIC if r[k]), default=None)
    risks = [c for c in cells if c["met"] and ((c["gap"] * 100 < near_pp) or (c["delta"] is not None and c["delta"] * 100 <= -1.0))]

    by_mk = {m["market"]: m for m in scope}
    for c in failing:
        m = by_mk[c["market"]]
        c["why"] = _chot_why(m, c) if c["metric"] == "chot" else _giao_why(m, c, _fate(m, (prev_snapshot or {}).get(c["market"])))

    rev_cur = sum(c["rev"] for c in failing)
    rev_prev = sum(c["rev_prev"] for c in cells)
    model = {
        "run_date": report["run_date"], "week": run.isocalendar()[1], "year": run.isocalendar()[0],
        "kpi_type": kpi_type, "kpi_name": KPI_TYPE_LABEL[kpi_type], "markets": [m["market"] for m in scope],
        "near_pp": near_pp, "rows": rows, "overall": ov, "failing": failing, "recovered": recovered,
        "progress": None if not progress else {"market": progress["market"],
                                               "deltas": {k: progress[k]["delta"] for k in METRIC if progress[k]}},
        "risks": risks, "deadlines": deadlines(run),
        "revenue": {"cur": rev_cur, "prev": rev_prev, "change": (rev_cur - rev_prev) / rev_prev if rev_prev else None,
                    "four_weeks": rev_cur * PROJECT_WEEKS,
                    "rows": [c for c in sorted(failing + recovered, key=lambda c: -max(c["rev"], c["rev_prev"]))]},
        "windows": {m["market"]: m["windows"] for m in scope},
    }
    model["charts"] = charts(model)
    return model


def _safe(c, numc, denc):
    return c[numc] / c[denc] if c.get(denc) else None


# ---------------------------------------------------------------- dữ liệu biểu đồ (tiêu đề do người viết đặt)
def charts(model) -> dict:
    rows, out = model["rows"], {}
    gap = lambda c: None if not c else round(c["gap"] * 100, 1)
    chot_gaps = [gap(r["chot"]) or 0.0 for r in rows]
    out["overview"] = {
        "type": "bar", "unit": " điểm %", "decimals": 1, "categories": [r["market"] for r in rows],
        "series": [{"name": "Tỷ lệ chốt", "values": chot_gaps}, {"name": "Tỷ lệ giao", "values": [gap(r["giao"]) or 0.0 for r in rows]}],
        "subtitle": f"Tỷ lệ chốt và tỷ lệ giao trừ KPI {model['kpi_name']}, tuần {model['week']}, điểm %",
    }
    worst = min(range(len(rows)), key=lambda i: chot_gaps[i], default=None)
    if worst is not None and chot_gaps[worst] < 0:  # chú thích gắn vào cột tỷ lệ chốt (chuỗi đầu) thiếu nhiều nhất
        out["overview"]["note"] = {"i": worst, "text": f"Chốt {rows[worst]['market']} thiếu {pts(rows[worst]['chot']['gap'], False)} điểm %",
                                   "dx": 0, "dy": -60, "wrap": 14}

    chot_fail = [c for c in model["failing"] if c["metric"] == "chot"]
    if chot_fail:
        items = [(f"{c['market']} · {r['reason']}", r["n"], c, r) for c in chot_fail for r in c["why"]["reasons"][:4]]
        items.sort(key=lambda x: -x[1])
        items = items[:6]
        tops = {c["market"]: c["why"]["reasons"][0]["reason"] for c in chot_fail if c["why"]["reasons"]}
        hl = [i for i, (_, _, c, r) in enumerate(items) if tops.get(c["market"]) == r["reason"]]
        worst_c = min(chot_fail, key=lambda c: c["gap"])
        ni = next((i for i, (_, _, c, r) in enumerate(items) if c is worst_c and tops.get(c["market"]) == r["reason"]), None)
        out["chot"] = {"type": "hbar", "unit": " đơn", "decimals": 0, "highlight": hl,
                       "categories": [x[0] for x in items], "values": [x[1] for x in items],
                       "subtitle": f"Lý do hủy hàng đầu ở {', '.join(c['market'] for c in chot_fail)} (chưa đạt KPI chốt), "
                                   f"đơn tạo {_win(chot_fail[0]['window'])}, số đơn"}
        if ni is not None:
            out["chot"]["note"] = {"i": ni, "text": f"{p0(items[ni][3]['share'])} số đơn hủy ở {worst_c['market']}", "wrap": 24}

    giao_fail = [c for c in model["failing"] if c["metric"] == "giao"]
    if giao_fail:
        c = giao_fail[0]
        f = c["why"]["fate"]
        if f:
            out["giao"] = {"type": "bar", "unit": " đơn", "decimals": 0, "highlight": [0],
                           "categories": ["Thành hoàn", "Vẫn đang giao", "Giao được"],
                           "values": [f["returned"], f["still"], f["delivered"]],
                           "subtitle": f"Nhóm {n0(f['overdue_then'])} đơn quá hạn của tuần trước ở {c['market']}: trạng thái đến nay, số đơn",
                           "note": {"i": 0, "text": f"{n0(f['returned'])}/{n0(f['overdue_then'])} đơn thành hoàn", "dx": 95, "dy": -6}}
        elif c["why"]["channels"]:
            bd = [x for x in c["why"]["channels"]]
            out["giao"] = {"type": "hbar", "unit": " điểm %", "decimals": 1,
                           "categories": [x["seg"] for x in bd], "values": [round((x["rate"] - c["target"]) * 100, 1) for x in bd],
                           "highlight": [0],
                           "subtitle": f"Tỷ lệ giao theo kênh bán trừ KPI {p0(c['target'])}, {c['market']}, đơn tạo {_win(c['window'])}, điểm %",
                           "note": {"i": 0, "text": f"Gánh {p0(bd[0]['share'])} phần thiếu", "wrap": 24}}

    rv = model["revenue"]["rows"]
    if rv:
        out["rev"] = {"type": "bar", "unit": " triệu", "decimals": 1, "categories": [c["short"] for c in rv],
                      "series": [{"name": "Tuần trước", "values": [round(c["rev_prev"] / 1e6, 1) for c in rv], "color": "#58585a"},
                                 {"name": f"Tuần {model['week']}", "values": [round(c["rev"] / 1e6, 1) for c in rv], "color": "#26a557"}],
                      "subtitle": f"Doanh thu hụt so với KPI {model['kpi_name']} mỗi tuần theo chỉ số chưa đạt, triệu đồng"}
        ri = next((i for i, c in enumerate(rv) if c["met"]), None)
        if ri is not None:
            out["rev"]["note"] = {"i": ri, "text": f"{rv[ri]['short']} đạt KPI, hết hụt", "dx": 70, "dy": -30}
    return out


def _win(w):
    return f"{fmt_date(w[0])}–{fmt_date(w[1])}"
