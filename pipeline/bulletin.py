"""Bản tin "Nhịp đập kinh doanh" gửi Lark — card JSON 2.0 dạng bảng.

Trình bày theo Nguyên tắc Kim tự tháp (Barbara Minto): mở đầu + kết luận ở trên, bảng chi tiết bên dưới.
Bảng chỉ gồm các chỉ số KHÔNG đạt KPI: Thị trường | Chỉ số | Thực hiện | Cảnh báo | Nguyên nhân | Gợi ý hành động.
- Cột Thực hiện do code điền (số liệu luôn đúng).
- Nguyên nhân / Gợi ý hành động do AI Analyst viết (pipeline/ai_writer.py); AI lỗi thì lấy từ phân tích theo quy tắc.
"""
import os
from datetime import date

from .analysis import KPI_TYPE_LABEL, alerts_for, fmt_date, num, pct

SOURCE_TABLE = os.getenv("SOURCE_TABLE", "hv-data.a_data_mart.sales_orders")
METRIC_ORDER = ["chot", "giao", "gtc_clean"]
METRIC_DEF = {
    "chot": "Đơn chốt ÷ data sạch",
    "giao": "Đơn giao thành công ÷ đơn giao DVVC",
    "gtc_clean": "Đơn giao thành công ÷ data sạch",
}
WINDOW_KIND = {"chot": "chot", "giao": "giao", "gtc_clean": "giao"}


def scope_of(report: dict, kpi_type: str, markets: list) -> dict:
    """Thị trường trong phạm vi bản tin, cảnh báo và danh sách đạt / không đạt."""
    scope = [m for m in report["markets"]
             if (not markets or m["market"] in markets)
             and any(s["target"] is not None for s in m["status"][kpi_type].values())]
    alerts = alerts_for(report, kpi_type, [m["market"] for m in scope])
    failing = sorted({a["market"] for a in alerts})
    return {"scope": scope, "alerts": alerts, "failing": failing,
            "passing": [m["market"] for m in scope if m["market"] not in failing]}


def _pp(x):
    return f"{abs(x) * 100:.1f}".replace(".", ",")


def _rows(report: dict, s: dict, ai: dict, near_pp: float) -> list:
    """Một dòng bảng cho mỗi chỉ số không đạt; nhóm theo thị trường (thị trường nặng nhất trước)."""
    by_mk = {m["market"]: m for m in report["markets"]}
    ai_secs = {(x["market"], x["metric"]): x for x in (ai or {}).get("sections", [])}
    worst = {}
    for a in s["alerts"]:
        worst[a["market"]] = min(worst.get(a["market"], 0), a["gap"])
    alerts = sorted(s["alerts"], key=lambda a: (worst[a["market"]], a["market"], METRIC_ORDER.index(a["metric"])))
    rows = []
    for a in alerts:
        m = by_mk[a["market"]]
        mv, win = m["metrics"][a["metric"]], m["windows"][WINDOW_KIND[a["metric"]]]
        near = a["gap"] > -near_pp / 100
        sec = ai_secs.get((a["market"], a["label"]))
        causes = sec["causes"] if sec else (a["levels"]["why"] + a["levels"]["impact"])[:4]
        actions = sec["actions"] if sec else a["levels"]["action"][:3]
        prev = "" if a["prev"] is None else f"<br><font color='grey'>Tuần trước {pct(a['prev'])}</font>"
        rows.append({  # <br>: xuống dòng chắc chắn trong ô markdown của Lark
            "mk": a["market"],
            "metric": f"**{a['label']}**<br><font color='grey'>{METRIC_DEF[a['metric']]}. Đơn tạo {fmt_date(win[0])} – {fmt_date(win[1])}</font>",
            "val": f"**{pct(a['value'])}**<br>{num(mv['num'])} / {num(mv['den'])} đơn<br>"
                   f"KPI {pct(a['target'], 0)} · <font color='{'orange' if near else 'red'}'>▼ thiếu {_pp(a['gap'])} điểm</font>{prev}",
            "alert": [{"text": "Gần đạt" if near else "Không đạt KPI", "color": "orange" if near else "red"}],
            "why": "\n".join(f"- {x}" for x in causes),
            "act": "\n".join(f"- {x}" for x in actions),
        })
    return rows


def _table(rows: list) -> dict:
    col = lambda name, label, dtype, width: {"name": name, "display_name": label, "data_type": dtype,
                                             "width": width, "vertical_align": "top"}
    return {
        "tag": "table", "element_id": "bang_canh_bao",
        "page_size": 10, "row_height": "auto", "row_max_height": "600px", "freeze_first_column": True,
        "header_style": {"text_align": "left", "text_size": "normal", "background_style": "grey",
                         "text_color": "default", "bold": True, "lines": 1},
        "columns": [
            col("mk", "Thị trường", "text", "90px"),
            col("metric", "Chỉ số", "markdown", "170px"),
            col("val", "Thực hiện", "markdown", "170px"),
            col("alert", "Cảnh báo", "options", "120px"),
            col("why", "Nguyên nhân", "markdown", "340px"),
            col("act", "Gợi ý hành động", "markdown", "340px"),
        ],
        "rows": rows,
    }


def _template_summary(s: dict, kpi_name: str, near_pp: float) -> dict:
    """NÓNG / LƯU Ý / TIN VUI theo quy tắc, dùng khi AI không chạy được."""
    line = lambda a: f"{a['market']} {a['label'].lower()} {pct(a['value'])} (KPI {pct(a['target'], 0)})"
    hot = [a for a in s["alerts"] if a["gap"] <= -near_pp / 100]
    near = [a for a in s["alerts"] if a["gap"] > -near_pp / 100]
    return {
        "hot": ("; ".join(line(a) for a in hot) + ".") if hot else "",
        "watch": ("Gần đạt: " + "; ".join(line(a) for a in near) + ".") if near else "",
        "good": (f"{', '.join(s['passing'])} đạt toàn bộ KPI {kpi_name}.") if s["passing"] else "",
    }


def _summary(s: dict, kpi_name: str, ai: dict, week: int, near_pp: float, next_note: str) -> list:
    """Tóm tắt đầu bản tin: NÓNG (đỏ) / LƯU Ý (cam) / TIN VUI (xanh), rồi câu mời đọc chi tiết."""
    sm = ai or _template_summary(s, kpi_name, near_pp)
    els = [{"tag": "markdown", "text_size": "notation", "content": f"<font color='grey'>**TÓM TẮT BẢN TIN TUẦN {week}**</font>"}]
    for key, label, color in (("hot", "NÓNG:", "red"), ("watch", "LƯU Ý:", "orange"), ("good", "TIN VUI:", "green")):
        text = (sm.get(key) or "").strip()
        if not text:
            continue
        els.append({"tag": "column_set", "flex_mode": "none", "horizontal_spacing": "8px", "columns": [
            {"tag": "column", "width": "72px", "vertical_align": "top",
             "elements": [{"tag": "markdown", "content": f"<font color='{color}'>**{label}**</font>"}]},
            {"tag": "column", "width": "weighted", "weight": 1, "vertical_align": "top",
             "elements": [{"tag": "markdown", "content": text}]},
        ]})
    els.append({"tag": "hr"})
    els.append({"tag": "markdown", "content":
                f"<font color='grey'>Mời đọc chi tiết bản tin ở bên dưới. Cảm ơn anh em đã quan tâm, "
                f"bản tin tiếp theo sẽ phát vào {next_note or 'tuần sau'}.</font>"})
    return els


def build_bulletin(report: dict, group: dict, dashboard_url: str = "", ai: dict = None, near_pp: float = 2,
                   next_note: str = "") -> dict:
    """next_note: thời điểm phát bản tin kế tiếp, vd "sáng Chủ nhật tuần sau" (lấy từ lịch gửi)."""
    kpi_type = group["kpi_type"]
    kpi_name = KPI_TYPE_LABEL[kpi_type]
    s = scope_of(report, kpi_type, group.get("markets") or [])
    run = report["run_date"]
    week = date.fromisoformat(run).isocalendar()[1]  # tuần ISO của ngày T (Chủ nhật kết thúc tuần)

    elements = _summary(s, kpi_name, ai, week, near_pp, next_note)
    if s["alerts"]:
        elements.append(_table(_rows(report, s, ai, near_pp)))
    if s["passing"] and s["alerts"]:
        elements.append({"tag": "markdown", "content": f"✅ Đạt toàn bộ KPI {kpi_name}: {', '.join(s['passing'])}"})
    if dashboard_url:
        elements.append({"tag": "button", "type": "primary", "text": {"tag": "plain_text", "content": "📊 Mở Dashboard"},
                         "behaviors": [{"type": "open_url", "default_url": f"{dashboard_url.rstrip('/')}/?date={run}&kpi={kpi_type}"}]})
    author = "Phân tích bởi AI Analyst (Claude), số liệu đối chiếu tự động" if ai else "Phân tích tự động theo quy tắc"
    elements.append({"tag": "markdown", "text_size": "notation", "content":
                     f"<font color='grey'>Hết bản tin. Hẹn gặp lại anh chị em vào bản tin tuần sau! · {author} · "
                     f"Nguồn: {SOURCE_TABLE}, đơn duy nhất từ data sạch theo ngày tạo đơn.</font>"})

    card = {
        "schema": "2.0",
        "config": {"width_mode": "fill", "update_multi": True},
        "header": {
            "template": "red" if s["alerts"] else "green",
            "title": {"tag": "plain_text", "content": f"📢 Nhịp đập kinh doanh tuần {week}"},
            "subtitle": {"tag": "plain_text", "content":
                         "Tin nóng và tin mới về Tỷ lệ chốt, Tỷ lệ giao, Tỷ lệ giao thành công từ data sạch của từng thị trường."},
        },
        "body": {"elements": elements},
    }
    return {"has_alert": bool(s["alerts"]), **s, "card": card}


def draft_card(card: dict, targets: list, draft_id: str, dashboard_url: str = "") -> dict:
    """Bản nháp gửi nhóm duyệt: thêm dải "chờ duyệt" lên đầu card."""
    banner = [{"tag": "markdown", "content":
               f"🟡 **BẢN NHÁP CHỜ DUYỆT** — sẽ gửi tới: {', '.join(targets) or '(chưa có nhóm)'}\n"
               f"Mã nháp: `{draft_id}`. Duyệt hoặc yêu cầu viết lại tại Dashboard → tab **Bản tin**."}]
    if dashboard_url:
        banner.append({"tag": "button", "type": "default", "text": {"tag": "plain_text", "content": "✅ Mở để duyệt"},
                       "behaviors": [{"type": "open_url", "default_url": f"{dashboard_url.rstrip('/')}/?tab=bantin&draft={draft_id}"}]})
    banner.append({"tag": "hr"})
    header = {**card["header"], "template": "yellow",
              "title": {"tag": "plain_text", "content": "[NHÁP] " + card["header"]["title"]["content"]}}
    return {**card, "header": header, "body": {**card["body"], "elements": banner + card["body"]["elements"]}}


def test_card(name: str, kpi_types: list) -> dict:
    what = " và ".join(f"cảnh báo KPI {KPI_TYPE_LABEL[t]}" for t in kpi_types) or "bản tin (chưa chọn loại nào)"
    return {
        "schema": "2.0",
        "header": {"template": "blue", "title": {"tag": "plain_text", "content": "📢 Nhịp đập kinh doanh · Kiểm tra kết nối"}},
        "body": {"elements": [{"tag": "markdown", "content":
                               f"Alo alo! Nhóm **{name}** đã được đăng ký nhận {what} của bản tin *Nhịp đập kinh doanh*."}]},
    }
