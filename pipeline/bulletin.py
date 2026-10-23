"""Bản tin "Nhịp đập kinh doanh" gửi Lark.

Trình bày theo Nguyên tắc Kim tự tháp (Barbara Minto): kết luận trước → các luận điểm chính → dữ liệu chi tiết
4 cấp độ cho từng thị trường. Giọng văn "loa phường": mở đầu thông báo, kết thúc hẹn bản tin sau.
"""
import os

from .analysis import KPI_TYPE_LABEL, alerts_for, fmt_date, pct

SOURCE_TABLE = os.getenv("SOURCE_TABLE", "hv-data.a_data_mart.sales_orders")

LEVEL_TITLES = [
    ("what", "1️⃣ Điều gì đã xảy ra"),
    ("why", "2️⃣ Tại sao"),
    ("impact", "3️⃣ Nguyên nhân chính & tác động"),
    ("action", "4️⃣ Chúng ta nên làm gì"),
]


def build_bulletin(report: dict, group: dict, dashboard_url: str = "") -> dict:
    kpi_type = group["kpi_type"]
    kpi_name = KPI_TYPE_LABEL[kpi_type]
    scope = [m for m in report["markets"]
             if (not group.get("markets") or m["market"] in group["markets"])
             and any(s["target"] is not None for s in m["status"][kpi_type].values())]
    alerts = alerts_for(report, kpi_type, [m["market"] for m in scope])
    failing = sorted({a["market"] for a in alerts})
    passing = [m["market"] for m in scope if m["market"] not in failing]
    run = report["run_date"]
    run_vn = f"{fmt_date(run)}/{run[:4]}"

    elements = []
    if alerts:
        opening = (
            f"📣 **Alo alo!** Bản tin *Nhịp đập kinh doanh* xin thông báo tới toàn thể anh chị em: "
            f"tuần này có **{len(failing)}/{len(scope)} thị trường chưa đạt KPI {kpi_name}** "
            f"({', '.join(failing)}), tổng cộng **{len(alerts)} chỉ số** cần xử lý ngay."
        )
    else:
        opening = (
            f"📣 **Alo alo!** Bản tin *Nhịp đập kinh doanh* xin thông báo: tuần này **tất cả {len(scope)} thị trường "
            f"đều đạt KPI {kpi_name}**. Xin biểu dương toàn thể anh chị em, tiếp tục giữ vững phong độ!"
        )
    elements.append({"tag": "markdown", "content": opening})

    if alerts:
        # Đỉnh kim tự tháp: kết luận & điều cần làm ngay
        top_lines = ["**🎯 Kết luận chính**"]
        for a in alerts:
            top_lines.append(f"🔴 **{a['market']}** · {a['headline']}")
            top_lines.append(f"　→ {a['levels']['action'][0]}")
        elements.append({"tag": "markdown", "content": "\n".join(top_lines)})
        if passing:
            elements.append({"tag": "markdown", "content": f"✅ Đạt KPI {kpi_name}: {', '.join(passing)}"})

        # Thân kim tự tháp: chi tiết 4 cấp độ
        for a in alerts:
            elements.append({"tag": "hr"})
            lines = [f"**📍 {a['market']} — {a['label']}**"]
            for key, title in LEVEL_TITLES:
                lines.append(f"**{title}**")
                lines += [f"• {x}" for x in a["levels"][key]]
            elements.append({"tag": "markdown", "content": "\n".join(lines)})

    elements.append({"tag": "hr"})
    windows = "; ".join(
        f"{m['market']}: chốt {fmt_date(m['windows']['chot'][0])}–{fmt_date(m['windows']['chot'][1])}, "
        f"giao {fmt_date(m['windows']['giao'][0])}–{fmt_date(m['windows']['giao'][1])}"
        for m in scope
    )
    if dashboard_url:
        elements.append({"tag": "action", "actions": [{
            "tag": "button", "type": "primary",
            "text": {"tag": "plain_text", "content": "📊 Mở Dashboard"},
            "url": f"{dashboard_url.rstrip('/')}/?date={run}&kpi={kpi_type}",
        }]})
    elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content":
        f"Hết bản tin. Hẹn gặp lại anh chị em vào bản tin tuần sau! · Nguồn: {SOURCE_TABLE} · "
        f"Đơn theo ngày tạo — {windows}"}]})

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "red" if alerts else "green",
            "title": {"tag": "plain_text", "content":
                      f"📢 Nhịp đập kinh doanh · {'Cảnh báo' if alerts else 'Đạt'} KPI {kpi_name} · {run_vn}"},
        },
        "elements": elements,
    }
    return {"has_alert": bool(alerts), "alerts": alerts, "failing": failing, "passing": passing, "card": card}


def test_card(name: str, kpi_types: list) -> dict:
    what = " và ".join(f"cảnh báo KPI {KPI_TYPE_LABEL[t]}" for t in kpi_types) or "bản tin (chưa chọn loại nào)"
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "blue", "title": {"tag": "plain_text", "content": "📢 Nhịp đập kinh doanh · Kiểm tra kết nối"}},
        "elements": [{"tag": "markdown", "content":
                      f"Alo alo! Nhóm **{name}** đã được đăng ký nhận {what} của bản tin *Nhịp đập kinh doanh*."}],
    }
