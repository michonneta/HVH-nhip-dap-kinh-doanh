"""Truy vấn BigQuery và tính các chỉ số cảnh báo tỷ lệ chốt / tỷ lệ giao."""
import os
from datetime import date, timedelta

from google.cloud import bigquery

SOURCE_TABLE = os.getenv("SOURCE_TABLE", "hv-data.a_data_mart.sales_orders")
BQ_PROJECT = os.getenv("BQ_PROJECT", "hv-data")

# key: (tên, cửa sổ dữ liệu, tử số, mẫu số)
METRICS = {
    "chot": ("Tỷ lệ chốt", "chot", "chot", "clean"),
    "huy": ("Tỷ lệ hủy", "chot", "huy", "clean"),
    "dang_xl": ("Tỷ lệ đang xử lý", "chot", "dang_xl", "clean"),
    "cho_giao": ("Tỷ lệ chờ giao", "giao", "cho_giao", "chot"),
    "giao_dvvc": ("Tỷ lệ giao DVVC", "giao", "giao_dvvc", "chot"),
    "giao": ("Tỷ lệ giao", "giao", "gtc", "giao_dvvc"),
    "hoan": ("Tỷ lệ hoàn", "giao", "hoan", "giao_dvvc"),
    "gtc_clean": ("Tỷ lệ giao thành công từ data sạch", "giao", "gtc", "clean"),
}
KPI_METRICS = ["chot", "giao", "gtc_clean"]
COUNT_COLS = ["clean", "chot", "huy", "dang_xl", "cho_giao", "giao_dvvc", "gtc", "hoan"]
DIM_LABELS = {
    "sub_bu": "Sub BU",
    "sales_channel": "Kênh bán",
    "partner_name": "Đơn vị vận chuyển",
    "cancel_reason": "Lý do hủy",
    "returned_reason": "Lý do hoàn",
}

_CLEAN_SQL = """
clean AS (
  SELECT order_key,
    ANY_VALUE(country) AS market,
    ANY_VALUE(event_date) AS d,
    ANY_VALUE(group_code) AS gc,
    IFNULL(NULLIF(ANY_VALUE(sub_bu), ''), '(trống)') AS sub_bu,
    IFNULL(NULLIF(ANY_VALUE(sales_channel), ''), '(trống)') AS sales_channel,
    IFNULL(NULLIF(ANY_VALUE(partner_name), ''), '(trống)') AS partner_name,
    IFNULL(NULLIF(ANY_VALUE(cancel_reason), ''), '(trống)') AS cancel_reason,
    IFNULL(NULLIF(ANY_VALUE(returned_reason), ''), '(trống)') AS returned_reason
  FROM `{table}`
  WHERE date_type = 'Ngày tạo đơn'
    AND event_date BETWEEN @min_date AND @max_date
    AND abandoned_order_label = 'Đơn thường'
    AND NOT REGEXP_CONTAINS(LOWER(NORMALIZE(IFNULL(all_tag_names, ''), NFC)), r'trùng|test|spam')
    AND IFNULL(group_code, '') != 'DELETED'
  GROUP BY order_key
)"""

_COUNTS_SQL = """
  COUNT(*) AS clean,
  COUNTIF(c.gc NOT IN ('CANCELLED', 'PROCESSING')) AS chot,
  COUNTIF(c.gc = 'CANCELLED') AS huy,
  COUNTIF(c.gc = 'PROCESSING') AS dang_xl,
  COUNTIF(c.gc IN ('CONFIRMED', 'RESTOCKING', 'WAITINGSHIPMENT', 'SHIPPING')) AS cho_giao,
  COUNTIF(c.gc IN ('SHIPPING', 'DELIVERED', 'RETURNED')) AS giao_dvvc,
  COUNTIF(c.gc = 'DELIVERED') AS gtc,
  COUNTIF(c.gc = 'RETURNED') AS hoan"""


def _cfg_cte(cfg: dict) -> str:
    rows = []
    for code, m in cfg["markets"].items():
        # code đã được validate (chữ in hoa/số), giá trị ngày là int
        rows.append(f"STRUCT('{code}' AS market, {int(m['chot_days'])} AS chot_days, {int(m['giao_days'])} AS giao_days)")
    return "cfg AS (SELECT * FROM UNNEST([" + ", ".join(rows) + "]))"


def _win_cte() -> str:
    return """
win AS (
  SELECT run_date, market, kind, period,
    DATE_SUB(run_date, INTERVAL lag + p_off + @wd - 1 DAY) AS d_from,
    DATE_SUB(run_date, INTERVAL lag + p_off DAY) AS d_to
  FROM UNNEST(@run_dates) AS run_date, cfg,
    UNNEST([STRUCT('chot' AS kind, chot_days AS lag), STRUCT('giao', giao_days)]),
    UNNEST([STRUCT('cur' AS period, 0 AS p_off), STRUCT('prev', @wd)])
)"""


def build_summary_sql(cfg: dict) -> str:
    return (
        "WITH " + _cfg_cte(cfg) + "," + _win_cte() + "," + _CLEAN_SQL.format(table=SOURCE_TABLE) + "\n"
        "SELECT w.run_date, w.market, w.kind, w.period, MIN(w.d_from) AS d_from, MIN(w.d_to) AS d_to," + _COUNTS_SQL + "\n"
        "FROM win w JOIN clean c ON c.market = w.market AND c.d BETWEEN w.d_from AND w.d_to\n"
        "GROUP BY 1, 2, 3, 4"
    )


def build_breakdown_sql(cfg: dict) -> str:
    dims = ", ".join(
        f"STRUCT('{d}' AS dim, c.{d} AS seg)" if i == 0 else f"('{d}', c.{d})"
        for i, d in enumerate(DIM_LABELS)
    )
    return (
        "WITH " + _cfg_cte(cfg) + "," + _win_cte() + "," + _CLEAN_SQL.format(table=SOURCE_TABLE) + "\n"
        "SELECT w.market, w.kind, x.dim, x.seg," + _COUNTS_SQL + "\n"
        "FROM win w JOIN clean c ON c.market = w.market AND c.d BETWEEN w.d_from AND w.d_to,\n"
        f"  UNNEST([{dims}]) AS x\n"
        "WHERE w.period = 'cur'\n"
        "GROUP BY 1, 2, 3, 4"
    )


_client = None


def _bq():
    global _client
    if _client is None:
        _client = bigquery.Client(project=BQ_PROJECT)
    return _client


def _run(sql: str, run_dates: list, cfg: dict) -> list:
    wd = int(cfg.get("window_days", 7))
    max_lag = max(max(m["giao_days"], m["chot_days"]) for m in cfg["markets"].values())
    params = [
        bigquery.ArrayQueryParameter("run_dates", "DATE", run_dates),
        bigquery.ScalarQueryParameter("wd", "INT64", wd),
        bigquery.ScalarQueryParameter("min_date", "DATE", min(run_dates) - timedelta(days=max_lag + 2 * wd)),
        bigquery.ScalarQueryParameter("max_date", "DATE", max(run_dates)),
    ]
    job = _bq().query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    return [dict(r.items()) for r in job.result()]


def last_sunday(today: date) -> date:
    # weekday(): Thứ 2 = 0 ... Chủ nhật = 6
    return today - timedelta(days=(today.weekday() + 1) % 7)


def _rate(counts: dict, metric: str):
    _, _, num, den = METRICS[metric]
    if not counts or not counts.get(den):
        return None
    return counts[num] / counts[den]


def fetch_summary(run_dates: list, cfg: dict) -> dict:
    """Một truy vấn cho nhiều ngày T: {(run_date, market, kind, period): {counts..., d_from, d_to}}"""
    rows = _run(build_summary_sql(cfg), sorted(run_dates), cfg)
    return {(r["run_date"], r["market"], r["kind"], r["period"]): r for r in rows}


def fetch_breakdown(run_date: date, cfg: dict) -> list:
    return _run(build_breakdown_sql(cfg), [run_date], cfg)


def market_metrics(summary: dict, run_date: date, market: str) -> dict:
    out = {}
    for mk, (label, kind, num, den) in METRICS.items():
        cur = summary.get((run_date, market, kind, "cur"))
        prev = summary.get((run_date, market, kind, "prev"))
        out[mk] = {
            "label": label,
            "value": _rate(cur, mk),
            "prev": _rate(prev, mk),
            "num": cur[num] if cur else 0,
            "den": cur[den] if cur else 0,
            "window": [str(cur["d_from"]), str(cur["d_to"])] if cur else None,
        }
    return out


def build_report(run_date: date, cfg: dict, with_analysis: bool = True, summary: dict = None) -> dict:
    """Báo cáo đầy đủ cho một ngày chạy T (thường là Chủ nhật). `summary` có thể truyền sẵn để tiết kiệm truy vấn."""
    summary = summary or fetch_summary([run_date], cfg)
    breakdown = fetch_breakdown(run_date, cfg) if with_analysis else []
    wd = int(cfg.get("window_days", 7))
    markets = []
    for code, mcfg in cfg["markets"].items():
        mm = market_metrics(summary, run_date, code)
        chot_to = run_date - timedelta(days=mcfg["chot_days"])
        giao_to = run_date - timedelta(days=mcfg["giao_days"])
        counts = {
            k: summary.get((run_date, code, k, "cur")) or {c: 0 for c in COUNT_COLS} for k in ("chot", "giao")
        }
        status = {}
        for kpi_type in ("survival", "monthly"):
            status[kpi_type] = {}
            for mk in KPI_METRICS:
                target = (mcfg.get("kpi") or {}).get(mk, {}).get(kpi_type)
                val = mm[mk]["value"]
                if target is None or val is None:
                    status[kpi_type][mk] = {"target": target, "ok": None, "gap": None}
                else:
                    status[kpi_type][mk] = {"target": target, "ok": val >= target, "gap": val - target}
        markets.append({
            "market": code,
            "windows": {
                "chot": [str(chot_to - timedelta(days=wd - 1)), str(chot_to)],
                "giao": [str(giao_to - timedelta(days=wd - 1)), str(giao_to)],
            },
            "counts": {k: {c: counts[k].get(c, 0) for c in COUNT_COLS} for k in counts},
            "metrics": mm,
            "status": status,
            "breakdown": _breakdown_for(breakdown, code) if with_analysis else {},
        })
    return {"run_date": str(run_date), "window_days": wd, "markets": markets}


def _breakdown_for(rows: list, market: str) -> dict:
    out = {"chot": {}, "giao": {}}
    for r in rows:
        if r["market"] != market:
            continue
        out[r["kind"]].setdefault(r["dim"], []).append({"seg": r["seg"], **{c: r[c] for c in COUNT_COLS}})
    return out


def build_trend(sundays: list, cfg: dict, summary: dict) -> dict:
    sundays = sorted(sundays)
    series = {}
    for code in cfg["markets"]:
        series[code] = {mk: [] for mk in METRICS}
        for d in sundays:
            mm = market_metrics(summary, d, code)
            for mk in METRICS:
                series[code][mk].append(mm[mk]["value"])
    return {"dates": [str(d) for d in sundays], "series": series}
