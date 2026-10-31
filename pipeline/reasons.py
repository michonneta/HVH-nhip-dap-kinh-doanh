"""Gộp lý do hủy / hoàn cùng nghĩa nhưng ghi bằng nhiều ngôn ngữ (Việt, Anh, Thái, Indonesia) về một tên chung.

Ví dụ "Customer changed their mind", "Khách đổi ý không mua", "Pelanggan berubah pikiran/batal beli" → "Khách đổi ý".
Lý do không khớp nhóm nào giữ nguyên tên gốc.
"""
import re

# (tên chung, regex các cách ghi) — thứ tự quan trọng: nhóm cụ thể đứng trước nhóm chung
GROUPS = [
    ("Không xác định", r"^(không xác định|other reason|lý do khác|unknown|khác|other)$"),
    ("Khách đổi ý", r"đổi ý|changed? (their|his|her)? ?mind|berubah pikiran|batal beli|want to cancel|huỷ ko mua|hủy ko mua"),
    ("Không có nhu cầu", r"không (có|còn) nhu cầu|no need|has no need|tidak memiliki kebutuhan|ไม่มีความต้องการ"),
    ("Không nghe máy", r"không nhấc máy|không nghe|no answer|tidak diangkat|ไม่รับสาย|unable to contact|tidak dapat dihubungi|"
                       r"thuê bao|subscriber unavailable|เบอร์ไม่ติดต่อ|tắt máy|hung up|วางสาย"),
    ("Sai số điện thoại", r"sai.*(sđt|số)|không có sđt|incorrect|non-existent|wrong number|salah|nomor telepon tidak ada|ผิด/ไม่มีเบอร์"),
    ("Bom hàng", r"bad history|bad transaction|lịch sử|hoàn hàng nhiều lần|refuse many time"),
    ("Không hỗ trợ COD", r"island|not supp?ort cod|area not"),
    ("Đã mua nơi khác", r"đã mua bên ngoài|already bought|sudah membeli|ซื้อจากที่อื่น|có người chốt rồi"),
    ("Không để lại thông tin", r"không để lại thông tin|didn.?t leave info|tidak meninggalkan informasi|ไม่ได้สั่ง"),
    ("Giá cao", r"giá cao|too expensive|harga tidak sesuai|ราคาไม่ถูกต้อง|giá không đúng"),
    ("Hủy từ sàn Shopee", r"hủy từ sàn shopee"),
    ("Hủy từ sàn Lazada", r"hủy từ sàn lazada"),
]
_COMPILED = [(name, re.compile(rx, re.IGNORECASE)) for name, rx in GROUPS]
UNKNOWN = "Không xác định"


def canonical(reason: str) -> str:
    s = (reason or "").strip()
    for name, rx in _COMPILED:
        if rx.search(s):
            return name
    return s


def grouped(rows: list, col: str) -> list:
    """rows: breakdown theo lý do [{seg, <col>...}] → [(tên chung, số đơn)] giảm dần; "(trống)" tách riêng ở cuối."""
    agg, blank = {}, 0
    for r in rows:
        n = r.get(col, 0)
        if n <= 0:
            continue
        if r["seg"] == "(trống)":
            blank += n
            continue
        if r["seg"].startswith("("):  # nhóm gộp kỹ thuật (vd "(lẻ)"): tính vào tổng ở nơi gọi, không xếp hạng
            continue
        name = canonical(r["seg"])
        agg[name] = agg.get(name, 0) + n
    out = sorted(agg.items(), key=lambda x: -x[1])
    if blank:
        out.append(("(trống)", blank))
    return out
