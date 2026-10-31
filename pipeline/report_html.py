"""Dựng file HTML Bản tin từ khuôn mẫu của skill (templates/report.html): giữ nguyên CSS, logo, script vẽ biểu đồ,
chỉ thay <title> và nội dung trong <main>."""
import html
import json
import re
from pathlib import Path

from .report import METRIC, n0, p0, p1, pts, tr, vnd, _win

TEMPLATE = Path(__file__).parent / "templates" / "report.html"
SOURCE = "Nguồn: hv-data.a_data_mart.sales_orders, đơn duy nhất từ data sạch theo ngày tạo đơn"


def _t(s) -> str:
    """Chữ thường → HTML an toàn; **x** → <strong>x</strong>."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(str(s or ""), quote=False))


def _ul(items):
    return "<ul>" + "".join(f"<li>{_t(x)}</li>" for x in items if x) + "</ul>"


def _chart(spec, title, source=SOURCE):
    if not spec:
        return ""
    data = {**spec, "title": title, "source": source}
    js = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f'<figure class="chart">\n<script type="application/json">{js}</script>\n</figure>\n'


def _cls(ok):
    return "up" if ok else "down"


def _sowhat(text):
    return f'<div class="sowhat"><b>Điều này có nghĩa là:</b> {_t(text)}</div>\n'


def _table(caption, head, rows):
    h = f'<div class="ct" style="margin-top:14px">{_t(caption)}</div>\n' if caption else ""
    right = ' class="r"'
    th = "".join(f"<th{right if i else ''}>{c}</th>" for i, c in enumerate(head))
    body = "".join("<tr>" + "".join(f"<td{right if i else ''}>{c}</td>" for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f"{h}<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>\n"


def _status_cell(c):
    if not c:
        return "–"
    return f'<span class="{_cls(c["met"])}">{p1(c["value"])} ({p0(c["target"])}) {"đạt" if c["met"] else "chưa đạt"}</span>'


def _delta_cell(d):
    return f'<span class="{_cls((d or 0) >= 0)}">{pts(d)}</span>'


def main_html(model: dict, narr: dict, author: str, logo: str) -> str:
    rd = model["run_date"]
    ov, fail, rev = model["overall"], model["failing"], model["revenue"]
    is_ai = author == "AI"
    out = [f"""<header class="hdr">
  {logo}
  <div class="meta"><b>Báo cáo tuần {model['week']}/{model['year']}</b>T = Chủ nhật {rd[8:10]}/{rd[5:7]}/{rd[:4]}<br>Phạm vi: {', '.join(model['markets'])} · KPI {model['kpi_name']}<br>Người lập: P.DVKH · {'AI Analyst' if is_ai else 'Phân tích tự động'}</div>
</header>
<div class="bar"></div>
<h1>{_t(narr['title_main'])} <em>{_t(narr['title_em'])}</em>{_t(narr['title_tail'])}</h1>
<p class="bq"><b>Câu hỏi kỳ này</b>Tỷ lệ chốt và tỷ lệ giao tuần {model['week']} có đạt KPI {model['kpi_name']} không, có tốt hơn tuần trước không, chỗ chưa đạt vì sao và làm hụt bao nhiêu doanh thu?</p>
<p class="lede">{_t(narr['lede'])}</p>
<section class="ask">
  <h3>{'Cần anh/chị quyết định trước ' + model['deadlines']['quyet_dinh'] if fail else 'Đề xuất của nhóm phân tích'}</h3>
  {_ul(narr['ask_items'])}
  <p class="impact">{_t(narr['impact'])}</p>
  <p class="trade">{_t(narr['trade'])}</p>
</section>
"""]
    # thẻ KPI: tỷ lệ chung + gọi tên thị trường đạt / chưa đạt
    def sub(k):
        o = ov[k]
        bits = []
        if o["failing"]:
            bits.append(f'<span class="down">{", ".join(o["failing"])} chưa đạt</span>')
        met_only = [x for x in o["met"] if x not in o["recovered"]]
        good = ([f"{', '.join(o['recovered'])} vừa đạt lại"] if o["recovered"] else []) + ([f"{', '.join(met_only)} đạt"] if met_only else [])
        if good:
            bits.append(f'<span class="up">{html.escape("; ".join(good))}</span>')
        return "; ".join(bits)
    pg = model["progress"]
    pg_txt = "" if not pg else " · ".join(f"{METRIC[k][0].split()[-1].capitalize()} {pts(v)}" for k, v in sorted(pg["deltas"].items(), key=lambda x: x[0] != "giao")) + " điểm %"
    chg = rev["change"]
    out.append(f"""<section class="kpis">
  <div class="kpi"><div class="l">Tỷ lệ chốt</div><div class="v">{p1(ov['chot']['cur'])}</div><div class="d">{sub('chot')}</div></div>
  <div class="kpi"><div class="l">Tỷ lệ giao</div><div class="v">{p1(ov['giao']['cur'])}</div><div class="d">{sub('giao')}</div></div>
  <div class="kpi"><div class="l">Tiến bộ nhất so với tuần trước</div><div class="v">{pg['market'] if pg else '–'}</div><div class="d up">{html.escape(pg_txt)}</div></div>
  <div class="kpi focus"><div class="l">Doanh thu hụt so với KPI</div><div class="v">{tr(rev['cur'])} triệu</div><div class="d {'up' if (chg or 0) <= 0 else 'down'}">{'' if chg is None else f"{chg * 100:+.0f}% so với tuần trước"}</div></div>
</section>
<section class="summary">
  <h3>Đọc nhanh: 3 điều cần biết</h3>
  {_ul(narr['summary'])}
</section>
""")
    # Bức tranh tổng
    ch = model["charts"]
    rows = [[f"<b>{r['market']}</b>", _status_cell(r["chot"]), _delta_cell(r["chot"] and r["chot"]["delta"]),
             _status_cell(r["giao"]), _delta_cell(r["giao"] and r["giao"]["delta"])] for r in model["rows"]]
    rows.append([f"<b>{len(model['rows'])} thị trường</b>", f"<b>{p1(ov['chot']['cur'])}</b>", _delta_cell(ov["chot"]["delta"]),
                 f"<b>{p1(ov['giao']['cur'])}</b>", _delta_cell(ov["giao"]["delta"])])
    out.append(f'<h2><span class="k">Bức tranh tổng</span>{_t(narr["overview_h2"])}</h2>\n'
               + _chart(ch.get("overview"), narr["overview_chart_title"])
               + _table("", ["Thị trường", "Tỷ lệ chốt (KPI)", "So với tuần trước", "Tỷ lệ giao (KPI)", "So với tuần trước"], rows)
               + _sowhat(narr["overview_sowhat"]))

    # Luận điểm 1: tỷ lệ chốt
    chot_f = [c for c in fail if c["metric"] == "chot"]
    t1 = ""
    if chot_f:
        r1 = []
        for c in chot_f:
            w = c["why"]
            r0 = w["reasons"][0] if w["reasons"] else None
            r1.append([f"<b>{c['market']}</b>", f'<span class="down">{p1(c["value"])} ({p0(c["target"])})</span>', _delta_cell(c["delta"]),
                       f"{html.escape(r0['reason'])}: <b>{r0['n']}/{w['cancels']} đơn ({p0(r0['share'])})</b>" if r0 else "–",
                       ", ".join(f"{html.escape(x['seg'])} <b>{p0(x['share'])}</b>" for x in w["channels"][:2]) or "–",
                       f"{tr(c['rev'])} triệu"])
        t1 = _table(f"Tỷ lệ chốt ở {', '.join(c['market'] for c in chot_f)} (chưa đạt KPI)",
                    ["Thị trường", "Tỷ lệ chốt (KPI)", "So với tuần trước", "Lý do hủy lớn nhất", "Kênh gánh phần thiếu", "Hụt mỗi tuần"], r1)
    out.append(f'<h2><span class="k">Luận điểm 1 · Tỷ lệ chốt</span>{_t(narr["chot_h2"])}</h2>\n{_ul(narr["chot_bullets"])}\n'
               + t1 + _chart(ch.get("chot"), narr["chot_chart_title"], SOURCE + "; lý do cùng nghĩa khác ngôn ngữ đã gộp")
               + _sowhat(narr["chot_sowhat"]))

    # Luận điểm 2: tỷ lệ giao
    giao_f = [c for c in fail if c["metric"] == "giao"]
    t2 = ""
    for c in giao_f[:1]:
        w = c["why"]
        r2 = [[f"<b>{html.escape(x['name'])}</b>" if x["diff"] < 0 else html.escape(x["name"]), n0(x["dvvc"]),
               f'<span class="{_cls(x["diff"] >= 0)}">{p1(x["rate"])}</span>', _delta_cell(x["diff"]),
               f"<b>{n0(x['overdue'])}</b>" if x["overdue"] else "0", n0(x["returns"])] for x in w["carriers"]]
        r2.append([f"<b>Toàn {c['market']}</b>", n0(w["dvvc"]), f"<b>{p1(c['value'])}</b>", _delta_cell(c["gap"]),
                   f"<b>{n0(w['overdue'])}</b>", n0(w["returns"])])
        t2 = _table(f"{c['market']}: tỷ lệ giao theo đơn vị vận chuyển, đơn tạo {_win(c['window'])}",
                    ["Đơn vị vận chuyển", "Đơn đã giao đơn vị", "Tỷ lệ giao", f"So với KPI {p0(c['target'])}", "Đơn quá hạn", "Đơn hoàn"], r2)
    out.append(f'<h2><span class="k">Luận điểm 2 · Tỷ lệ giao</span>{_t(narr["giao_h2"])}</h2>\n{_ul(narr["giao_bullets"])}\n'
               + t2 + _chart(ch.get("giao"), narr["giao_chart_title"]) + _sowhat(narr["giao_sowhat"]))

    # Luận điểm 3: doanh thu
    t3 = ""
    if rev["rows"]:
        r3 = [[f"<b>{c['short']}</b>" if not c["met"] else c["short"],
               "0" if c["met"] else str(c["gap_orders"]),
               '<span class="up">Đã đạt</span>' if c["met"] else str(c["need_orders"]),
               "–" if c["met"] else vnd(c["aov"] or 0),
               '<span class="up">0</span>' if c["met"] else f"<b>{tr(c['rev'])}</b>",
               tr(c["rev_prev"]), "0" if c["met"] else tr(c["rev"] * 4)] for c in rev["rows"]]
        r3.append(["<b>Tổng</b>", "", "", "", f"<b>{tr(rev['cur'])}</b>", tr(rev["prev"]), f"<b>{tr(rev['four_weeks'])}</b>"])
        t3 = _table("Doanh thu hụt theo chỉ số chưa đạt KPI (triệu đồng)",
                    ["Chỉ số chưa đạt", "Đơn thiếu so với KPI", "Cần thêm để đạt KPI", "Giá trị TB mỗi đơn", "Hụt mỗi tuần", "Tuần trước", "Nếu kéo dài 4 tuần"], r3)
    out.append(f'<h2><span class="k">Luận điểm 3 · Ảnh hưởng doanh thu</span>{_t(narr["rev_h2"])}</h2>\n{_ul(narr["rev_bullets"])}\n'
               + t3 + _chart(ch.get("rev"), narr["rev_chart_title"], SOURCE + "; doanh thu đã trừ chiết khấu và VAT")
               + _sowhat(narr["rev_sowhat"]))

    # Kế hoạch, rủi ro, kết luận
    acts = [[_t(a["task"]), _t(a["owner"]), _t(a["deadline"]), _t(a["result"])] for a in narr["actions"]]
    out.append(f'<h2><span class="k">Kế hoạch hành động</span>{_t(narr["actions_h2"])}</h2>\n'
               + _table("", ["Việc cần làm", "Ai làm", "Hạn chót", "Kết quả kỳ vọng"], acts))
    if narr["risks"]:
        out.append(f'<h2><span class="k">Rủi ro cần theo dõi</span>{_t(narr["risks_h2"])}</h2>\n{_ul(narr["risks"])}\n')
    out.append(f'<div class="conclusion"><span>=&gt;</span><div>{_t(narr["conclusion"])}</div></div>\n')

    tag = {"ok": '<span class="tag ok">Xác nhận</span>', "part": '<span class="tag part">Một phần</span>', "no": '<span class="tag no">Loại trừ</span>'}
    hy = [[_t(h["hypothesis"]), tag.get(h["result"], ""), _t(h["evidence"])] for h in narr["hypotheses"]]
    wins = "; ".join(f"{mk} chốt {_win(w['chot'])}, giao {_win(w['giao'])}" for mk, w in model["windows"].items())
    out.append(f"""<section class="method">
<h2><span class="k">Phụ lục</span>Cách chúng tôi đi đến kết luận</h2>
<p>Với từng chỉ số chưa đạt, nhóm phân tích kiểm tra các nguyên nhân có thể có theo đúng khâu.</p>
{_table("", ["Giả thuyết", "Kết quả", "Bằng chứng"], hy) if hy else ""}
<p><b>Dữ liệu và độ tin cậy:</b> bảng hv-data.a_data_mart.sales_orders; đơn duy nhất từ data sạch theo ngày tạo đơn. Cửa sổ đơn tạo theo thời gian chốt và giao trung bình của từng thị trường: {html.escape(wins)}. Tỷ lệ chung là tổng số đơn của các thị trường chia cho nhau, không phải trung bình các tỷ lệ. Doanh thu theo công thức của công ty: giá trị đơn trừ chiết khấu, quy đổi ra đồng, trừ VAT, chỉ tính đơn chờ gửi, đã xác nhận, đang giao và giao thành công. Doanh thu hụt là ước tính: số đơn thiếu so với KPI (làm tròn) nhân giá trị trung bình mỗi đơn của thị trường trong cùng cửa sổ; mốc "cần thêm để đạt KPI" làm tròn lên và đã kiểm tra bằng phép chia. Chốt và giao đo trên hai nhóm đơn khác nhau nên được cộng lại. Trạng thái đơn còn thay đổi sau khi chốt tuần, nên số tuần trước có thể khác bản tin đã gửi. Giới hạn: chưa có phí vận chuyển và giá vốn.</p>
</section>
<section class="terms">
  <h3>Giải thích thuật ngữ</h3>
  <ul>
    <li><b>KPI {model['kpi_name']}:</b> mức tối thiểu công ty đặt cho từng chỉ số của mỗi thị trường.</li>
    <li><b>Data sạch:</b> đơn khách để lại thông tin, sau khi bỏ đơn trùng, đơn test, đơn spam và đơn đã xóa.</li>
    <li><b>Tỷ lệ chốt:</b> số đơn khách xác nhận mua trên 100 data sạch. Tỷ lệ chốt chung {p1(ov['chot']['cur'])} nghĩa là cứ 100 khách để lại thông tin thì khoảng {round(ov['chot']['cur'] * 100) if ov['chot']['cur'] else 0} khách đồng ý mua.</li>
    <li><b>Tỷ lệ giao:</b> số đơn giao thành công trên 100 đơn đã giao cho đơn vị vận chuyển.</li>
    <li><b>Đơn quá hạn:</b> đơn vẫn đang giao dù đã quá thời gian giao trung bình của thị trường.</li>
    <li><b>Doanh thu hụt so với KPI:</b> doanh thu thu thêm được nếu chỉ số đạt KPI, bằng số đơn thiếu nhân giá trị trung bình mỗi đơn.</li>
    <li><b>Điểm %:</b> chênh lệch giữa hai tỷ lệ, ví dụ từ 85,1% lên 85,6% là tăng 0,5 điểm %.</li>
  </ul>
</section>
<footer class="ftr"><span>HV Holdings | P.DVKH · Phân tích dữ liệu | Tài liệu nội bộ</span><span>{'Viết bởi AI Analyst (Claude), số liệu tính và đối chiếu tự động' if is_ai else 'Viết theo mẫu quy tắc, số liệu tính tự động'}</span></footer>
""")
    return "".join(out)


def title_text(narr: dict) -> str:
    return f"{narr['title_main']} {narr['title_em']}{narr['title_tail']}".upper()


def render(model: dict, narr: dict, author: str) -> str:
    tpl = TEMPLATE.read_text(encoding="utf-8")
    logo = re.search(r'<img src="data:image/png;base64,[^"]+" alt="HV Holdings">', tpl).group(0)
    start = tpl.index('<main class="page">') + len('<main class="page">')
    end = tpl.index("</main>")
    page = tpl[:start] + "\n" + main_html(model, narr, author, logo) + tpl[end:]
    return re.sub(r"<title>.*?</title>", lambda _: f"<title>{html.escape(title_text(narr))} | HV Holdings</title>", page, count=1, flags=re.S)
