"""Bản tin "Nhịp đập kinh doanh" gửi Lark.

Trình bày theo Nguyên tắc Kim tự tháp (Barbara Minto): kết luận trước → các luận điểm chính → dữ liệu chi tiết
4 cấp độ cho từng thị trường. Giọng văn "loa phường": mở đầu thông báo, kết thúc hẹn bản tin sau.

Thân bản tin do AI Analyst viết (pipeline/ai_writer.py); khi AI không chạy được thì dùng mẫu theo quy tắc ở đây.
Khung bản tin (tiêu đề, nút Dashboard, nguồn dữ liệu) luôn do code dựng để thống nhất.
"""
import os

from .analysis import KPI_TYPE_LABEL, alerts_for, fmt_date

SOURCE_TABLE = os.getenv("SOURCE_TABLE", "hv-data.a_data_mart.sales_orders")

LEVEL_TITLES = [
    ("what", "1️⃣ Điều gì đã xảy ra"),
    ("why", "2️⃣ Tại sao"),
    ("impact", "3️⃣ Nguyên nhân chính & tác động"),
    ("action", "4️⃣ Chúng ta nên làm gì"),
]


def scope_of(report: dict, kpi_type: str, markets: list) -> dict:
    """Thị trường trong phạm vi bản tin, cảnh báo và danh sách đạt / không đạt."""
    scope = [m for m in report["markets"]
             if (not markets or m["market"] in markets)
             and any(s["target"] is not None for s in m["status"][kpi_type].values())]
    alerts = alerts_for(report, kpi_type, [m["market"] for m in scope])
    failing = sorted({a["market"] for a in alerts})
    return {"scope": scope, "alerts": alerts, "failing": failing,
            "passing": [m["market"] for m in scope if m["market"] not in failing]}


def _template_body(s: dict, kpi_name: str) -> list:
    alerts, failing, passing, scope = s["alerts"], s["failing"], s["passing"], s["scope"]
    if not alerts:
        return [{"tag": "markdown", "content":
                 f"📣 **Alo alo!** Bản tin *Nhịp đập kinh doanh* xin thông báo: tuần này **tất cả {len(scope)} thị trường "
                 f"đều đạt KPI {kpi_name}**. Xin biểu dương toàn thể anh chị em, tiếp tục giữ vững phong độ!"}]
    elements = [{"tag": "markdown", "content":
                 f"📣 **Alo alo!** Bản tin *Nhịp đập kinh doanh* xin thông báo tới toàn thể anh chị em: "
                 f"tuần này có **{len(failing)}/{len(scope)} thị trường chưa đạt KPI {kpi_name}** "
                 f"({', '.join(failing)}), tổng cộng **{len(alerts)} chỉ số** cần xử lý ngay."}]
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
    return elements


def _ai_body(ai: dict) -> list:
    """ai: kết quả AIBulletin (dict) đã qua kiểm tra số liệu."""
    elements = [{"tag": "markdown", "content": ai["opening"]}]
    top = ["**🎯 Kết luận chính**", ai["conclusion"]] + [f"• {p}" for p in ai["key_points"]]
    elements.append({"tag": "markdown", "content": "\n".join(top)})
    for sec in ai["sections"]:
        elements.append({"tag": "hr"})
        lines = [f"**📍 {sec['market']} — {sec['metric']}**"]
        for key, title in LEVEL_TITLES:
            lines.append(f"**{title}**")
            lines += [f"• {x}" for x in sec[key]]
        elements.append({"tag": "markdown", "content": "\n".join(lines)})
    if ai.get("closing"):
        elements.append({"tag": "markdown", "content": ai["closing"]})
    return elements


def build_bulletin(report: dict, group: dict, dashboard_url: str = "", ai: dict = None) -> dict:
    kpi_type = group["kpi_type"]
    kpi_name = KPI_TYPE_LABEL[kpi_type]
    s = scope_of(report, kpi_type, group.get("markets") or [])
    run = report["run_date"]

    elements = _ai_body(ai) if ai else _template_body(s, kpi_name)
    elements.append({"tag": "hr"})
    windows = "; ".join(
        f"{m['market']}: chốt {fmt_date(m['windows']['chot'][0])}–{fmt_date(m['windows']['chot'][1])}, "
        f"giao {fmt_date(m['windows']['giao'][0])}–{fmt_date(m['windows']['giao'][1])}"
        for m in s["scope"]
    )
    if dashboard_url:
        elements.append({"tag": "action", "actions": [{
            "tag": "button", "type": "primary",
            "text": {"tag": "plain_text", "content": "📊 Mở Dashboard"},
            "url": f"{dashboard_url.rstrip('/')}/?date={run}&kpi={kpi_type}",
        }]})
    author = "Phân tích bởi AI Analyst (Claude), số liệu đã đối chiếu tự động" if ai else "Phân tích tự động theo quy tắc"
    elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content":
        f"Hết bản tin. Hẹn gặp lại anh chị em vào bản tin tuần sau! · {author} · Nguồn: {SOURCE_TABLE} · "
        f"Đơn theo ngày tạo — {windows}"}]})

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "red" if s["alerts"] else "green",
            "title": {"tag": "plain_text", "content":
                      f"📢 Nhịp đập kinh doanh · {'Cảnh báo' if s['alerts'] else 'Đạt'} KPI {kpi_name} · "
                      f"{fmt_date(run)}/{run[:4]}"},
        },
        "elements": elements,
    }
    return {"has_alert": bool(s["alerts"]), **s, "card": card}


def draft_card(card: dict, targets: list, draft_id: str, dashboard_url: str = "") -> dict:
    """Bản nháp gửi nhóm duyệt: thêm dải "chờ duyệt" lên đầu card."""
    banner = [{"tag": "markdown", "content":
               f"🟡 **BẢN NHÁP CHỜ DUYỆT** — sẽ gửi tới: {', '.join(targets) or '(chưa có nhóm)'}\n"
               f"Mã nháp: `{draft_id}`. Duyệt hoặc yêu cầu viết lại tại Dashboard → tab **Bản tin**."}]
    if dashboard_url:
        banner.append({"tag": "action", "actions": [{
            "tag": "button", "type": "default", "text": {"tag": "plain_text", "content": "✅ Mở để duyệt"},
            "url": f"{dashboard_url.rstrip('/')}/?tab=bantin&draft={draft_id}"}]})
    banner.append({"tag": "hr"})
    header = {**card["header"], "template": "yellow",
              "title": {"tag": "plain_text", "content": "[NHÁP] " + card["header"]["title"]["content"]}}
    return {**card, "header": header, "elements": banner + card["elements"]}


def test_card(name: str, kpi_types: list) -> dict:
    what = " và ".join(f"cảnh báo KPI {KPI_TYPE_LABEL[t]}" for t in kpi_types) or "bản tin (chưa chọn loại nào)"
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "blue", "title": {"tag": "plain_text", "content": "📢 Nhịp đập kinh doanh · Kiểm tra kết nối"}},
        "elements": [{"tag": "markdown", "content":
                      f"Alo alo! Nhóm **{name}** đã được đăng ký nhận {what} của bản tin *Nhịp đập kinh doanh*."}],
    }
