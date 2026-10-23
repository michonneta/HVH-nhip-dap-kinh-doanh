"""Khối dữ liệu (cube) cho Dashboard: gom đơn data sạch theo ngày tạo × các chiều lọc × trạng thái × lý do.

Trình duyệt tự lọc và tính chỉ số trên khối này (GitHub Pages không có server truy vấn BigQuery).
- facts:     (ngày, thị trường, BU, kênh bán, team, seller, sub brand, tỉnh, trạng thái, lý do) → số đơn
- sku_facts: như facts + SKU → số đơn có chứa SKU đó (dùng khi lọc theo SKU/sản phẩm)

Trạng thái (theo group_code): C hủy · P đang xử lý · W chờ gửi kho (CONFIRMED/RESTOCKING/WAITINGSHIPMENT)
· S đang giao · D giao thành công · R hoàn · O khác (tính vào đơn chốt).
"""
import logging
import os
from collections import Counter
from datetime import date, timedelta

from google.cloud import bigquery

from . import metrics

log = logging.getLogger("nhip-dap")
HISTORY_DAYS = int(os.getenv("CUBE_HISTORY_DAYS", "400"))
TOP_REASONS = 25          # mỗi thị trường giữ 25 lý do hủy / hoàn nhiều nhất, còn lại gộp "Khác"
DIMS = ["mk", "bu", "ch", "team", "seller", "sb", "prov"]
STATUSES = ["C", "P", "W", "S", "D", "R", "O"]
NO_REASON, OTHER_REASON = "(chưa ghi lý do)", "Khác"

_ORDERS = """
WITH o AS (
  SELECT order_key,
    ANY_VALUE(event_date) AS d,
    ANY_VALUE(country) AS mk,
    IFNULL(NULLIF(ANY_VALUE(business_unit), ''), '(trống)') AS bu,
    IFNULL(NULLIF(ANY_VALUE(sales_channel), ''), '(trống)') AS ch,
    IFNULL(NULLIF(ANY_VALUE(team), ''), '(trống)') AS team,
    IFNULL(NULLIF(ANY_VALUE(seller_code), ''), '(trống)') AS seller,
    IFNULL(NULLIF(ANY_VALUE(sub_brand), ''), '(trống)') AS sb,
    IFNULL(NULLIF(ANY_VALUE(province), ''), '(trống)') AS prov,
    CASE ANY_VALUE(group_code)
      WHEN 'CANCELLED' THEN 'C' WHEN 'PROCESSING' THEN 'P' WHEN 'SHIPPING' THEN 'S'
      WHEN 'DELIVERED' THEN 'D' WHEN 'RETURNED' THEN 'R'
      WHEN 'CONFIRMED' THEN 'W' WHEN 'RESTOCKING' THEN 'W' WHEN 'WAITINGSHIPMENT' THEN 'W' ELSE 'O' END AS st,
    CASE ANY_VALUE(group_code)
      WHEN 'CANCELLED' THEN IFNULL(NULLIF(TRIM(ANY_VALUE(cancel_reason)), ''), '{no}')
      WHEN 'RETURNED' THEN IFNULL(NULLIF(TRIM(ANY_VALUE(returned_reason)), ''), '{no}') ELSE '' END AS reason,
    ARRAY_AGG(DISTINCT sku IGNORE NULLS) AS skus
  FROM `{table}`
  WHERE date_type = 'Ngày tạo đơn'
    AND event_date BETWEEN @min_date AND @max_date
    AND abandoned_order_label = 'Đơn thường'
    AND NOT REGEXP_CONTAINS(LOWER(NORMALIZE(IFNULL(all_tag_names, ''), NFC)), r'trùng|test|spam')
    AND IFNULL(group_code, '') != 'DELETED'
  GROUP BY order_key
)"""

FACTS_SQL = _ORDERS + """
SELECT d, mk, bu, ch, team, seller, sb, prov, st, reason, COUNT(*) AS n
FROM o GROUP BY d, mk, bu, ch, team, seller, sb, prov, st, reason"""

SKU_SQL = _ORDERS + """
SELECT d, mk, bu, ch, team, seller, sb, prov, st, reason, sku, COUNT(*) AS n
FROM o, UNNEST(o.skus) AS sku
GROUP BY d, mk, bu, ch, team, seller, sb, prov, st, reason, sku"""

PRODUCTS_SQL = """
SELECT sku, ANY_VALUE(product_name) AS name
FROM `{table}`
WHERE date_type = 'Ngày tạo đơn' AND event_date BETWEEN @min_date AND @max_date AND sku IS NOT NULL
GROUP BY sku"""


def _query(sql: str, min_date: date, max_date: date) -> list:
    params = [bigquery.ScalarQueryParameter("min_date", "DATE", min_date),
              bigquery.ScalarQueryParameter("max_date", "DATE", max_date)]
    job = metrics._bq().query(sql.format(table=metrics.SOURCE_TABLE, no=NO_REASON),
                              job_config=bigquery.QueryJobConfig(query_parameters=params))
    return [dict(r.items()) for r in job.result()]


def _reason_map(rows: list) -> dict:
    """{(trạng thái, thị trường, lý do gốc): lý do hiển thị} — top lý do mỗi thị trường, còn lại 'Khác'."""
    counts = Counter()
    for r in rows:
        if r["st"] in ("C", "R"):
            counts[(r["st"], r["mk"], r["reason"])] += r["n"]
    keep = set()
    for st in ("C", "R"):
        for mk in {k[1] for k in counts if k[0] == st}:
            top = sorted(((n, k) for k, n in counts.items() if k[0] == st and k[1] == mk), reverse=True)[:TOP_REASONS]
            keep |= {k for _, k in top}
    return {k: (k[2] if k in keep or k[2] == NO_REASON else OTHER_REASON) for k in counts}


def _pack(rows: list, start: date, reason_of: dict, extra: str = None) -> dict:
    """Bảng cột, giá trị chiều mã hóa thành chỉ số trong từ điển (gọn, trình duyệt đọc nhanh)."""
    cols = DIMS + (["sku"] if extra else [])
    dicts = {c: {} for c in cols + ["reason"]}
    agg = Counter()
    for r in rows:
        reason = reason_of.get((r["st"], r["mk"], r["reason"]), "") if r["st"] in ("C", "R") else ""
        key = ((r["d"] - start).days,) + tuple(r[c] for c in cols) + (r["st"], reason)
        agg[key] += r["n"]
    out = {c: [] for c in ["d"] + cols + ["st", "reason", "n"]}
    for key, n in sorted(agg.items()):
        out["d"].append(key[0])
        for i, c in enumerate(cols):
            out[c].append(dicts[c].setdefault(key[1 + i], len(dicts[c])))
        out["st"].append(STATUSES.index(key[-2]))
        out["reason"].append(dicts["reason"].setdefault(key[-1], len(dicts["reason"])))
        out["n"].append(n)
    return {"rows": len(agg), "cols": out, "dict": {c: list(v) for c, v in dicts.items()}}


def build_cube(today: date) -> dict:
    max_date = today
    min_date = today - timedelta(days=HISTORY_DAYS)
    facts = _query(FACTS_SQL, min_date, max_date)
    skus = _query(SKU_SQL, min_date, max_date)
    products = {r["sku"]: r["name"] for r in _query(PRODUCTS_SQL, min_date, max_date)}
    start = min((r["d"] for r in facts), default=min_date)
    reason_of = _reason_map(facts)
    cube = {
        "start": str(start), "end": str(max_date), "statuses": STATUSES,
        "facts": _pack(facts, start, reason_of),
        "sku_facts": _pack(skus, start, reason_of, extra="sku"),
        "products": products,
    }
    log.info("Cube: %s dòng facts, %s dòng SKU, từ %s", cube["facts"]["rows"], cube["sku_facts"]["rows"], start)
    return cube
