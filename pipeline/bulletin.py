"""Card Lark (JSON 2.0) tóm tắt Bản tin "Nhịp đập kinh doanh": lớp 30 giây của bản tin HTML.

Tiêu đề, câu hỏi kỳ này, đoạn mở, khối quyết định, 4 thẻ KPI, Đọc nhanh, kết luận. Bản tin đầy đủ (biểu đồ, bảng,
kế hoạch hành động) gửi ngay sau card dưới dạng ảnh (report_image.py).
"""
import os

from .analysis import KPI_TYPE_LABEL
from .report import METRIC, p1, pts, tr
from .report_html import title_text

SOURCE_TABLE = os.getenv("SOURCE_TABLE", "hv-data.a_data_mart.sales_orders")


def _md(content, size=None):
    return {"tag": "markdown", "content": content, **({"text_size": size} if size else {})}


def _box(elements, weight=1):
    return {"tag": "column", "width": "weighted", "weight": weight, "background_style": "grey",
            "padding": "8px 12px 8px 12px", "vertical_spacing": "4px", "elements": elements}


def _kpi_sub(o):
    bits = []
    if o["failing"]:
        bits.append(f"<font color='red'>{', '.join(o['failing'])} chưa đạt</font>")
    met_only = [x for x in o["met"] if x not in o["recovered"]]
    good = ([f"{', '.join(o['recovered'])} vừa đạt lại"] if o["recovered"] else []) + ([f"{', '.join(met_only)} đạt"] if met_only else [])
    if good:
        bits.append(f"<font color='green'>{'; '.join(good)}</font>")
    return "; ".join(bits)


def build_card(model: dict, narr: dict, dashboard_url: str = "", author: str = "AI") -> dict:
    rd, ov, rev = model["run_date"], model["overall"], model["revenue"]
    fail = model["failing"]
    pg = model["progress"]
    pg_txt = "" if not pg else " · ".join(f"{METRIC[k][0].split()[-1].capitalize()} {pts(v)}"
                                          for k, v in sorted(pg["deltas"].items(), key=lambda x: x[0] != "giao")) + " điểm %"
    chg = rev["change"]
    kpis = [
        ("TỶ LỆ CHỐT", p1(ov["chot"]["cur"]), _kpi_sub(ov["chot"])),
        ("TỶ LỆ GIAO", p1(ov["giao"]["cur"]), _kpi_sub(ov["giao"])),
        ("TIẾN BỘ NHẤT SO VỚI TUẦN TRƯỚC", pg["market"] if pg else "–", f"<font color='green'>{pg_txt}</font>" if pg_txt else ""),
        ("DOANH THU HỤT SO VỚI KPI", f"{tr(rev['cur'])} triệu",
         "" if chg is None else f"<font color='{'green' if chg <= 0 else 'red'}'>{chg * 100:+.0f}% so với tuần trước</font>"),
    ]
    ask_title = f"CẦN ANH/CHỊ QUYẾT ĐỊNH TRƯỚC {model['deadlines']['quyet_dinh'].upper()}" if fail else "ĐỀ XUẤT CỦA NHÓM PHÂN TÍCH"
    elements = [
        _md(f"<font color='grey'>**CÂU HỎI KỲ NÀY** Tỷ lệ chốt và tỷ lệ giao tuần {model['week']} có đạt KPI {model['kpi_name']} không, "
            f"có tốt hơn tuần trước không, chỗ chưa đạt vì sao và làm hụt bao nhiêu doanh thu?</font>", "notation"),
        _md(narr["lede"]),
        {"tag": "column_set", "flex_mode": "none", "columns": [_box([
            _md(f"<font color='green'>**{ask_title}**</font>"),
            _md("\n".join(f"- {x}" for x in narr["ask_items"])),
            _md(narr["impact"], "notation"),
            _md(f"<font color='grey'>{narr['trade']}</font>", "notation"),
        ])]},
        {"tag": "column_set", "flex_mode": "bisect", "horizontal_spacing": "8px",
         "columns": [_box([_md(f"<font color='grey'>{label}</font>", "notation"), _md(f"**{value}**", "heading"), _md(sub, "notation")])
                     for label, value, sub in kpis]},
        _md("**ĐỌC NHANH: 3 ĐIỀU CẦN BIẾT**\n" + "\n".join(f"- {x}" for x in narr["summary"])),
        {"tag": "hr"},
        _md(f"<font color='green'>**=>**</font> **{narr['conclusion']}**"),
        _md("<font color='grey'>Ảnh toàn bộ bản tin (bảng trạng thái, nguyên nhân, doanh thu hụt, kế hoạch hành động) gửi ngay bên dưới.</font>",
            "notation"),
    ]
    if dashboard_url:
        elements.append({"tag": "button", "type": "primary", "text": {"tag": "plain_text", "content": "Mở Dashboard"},
                         "behaviors": [{"type": "open_url", "default_url": f"{dashboard_url.rstrip('/')}/?date={rd}&kpi={model['kpi_type']}"}]})
    by = "AI Analyst (Claude), số liệu đối chiếu tự động" if author == "AI" else "mẫu theo quy tắc, số liệu tính tự động"
    elements.append(_md(f"<font color='grey'>Viết bởi {by} · Nguồn: {SOURCE_TABLE}, đơn duy nhất từ data sạch theo ngày tạo đơn.</font>",
                        "notation"))
    return {
        "schema": "2.0",
        "config": {"width_mode": "fill", "update_multi": True},
        "header": {
            "template": "red" if fail else "green",
            "title": {"tag": "plain_text", "content": title_text(narr)},
            "subtitle": {"tag": "plain_text", "content": f"Nhịp đập kinh doanh · Tuần {model['week']} · T = {rd[8:10]}/{rd[5:7]}/{rd[:4]} · KPI {model['kpi_name']}"},
        },
        "body": {"elements": elements},
    }


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
        "header": {"template": "blue", "title": {"tag": "plain_text", "content": "Nhịp đập kinh doanh · Kiểm tra kết nối"}},
        "body": {"elements": [{"tag": "markdown", "content":
                               f"Alo alo! Nhóm **{name}** đã được đăng ký nhận {what} của bản tin *Nhịp đập kinh doanh*."}]},
    }
