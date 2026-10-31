"""Lời văn cho Bản tin "Nhịp đập kinh doanh": AI Analyst viết theo skill bao-cao-dinh-ky-consultant
(phần lõi + hồ sơ Nhịp đập kinh doanh); AI lỗi thì dùng mẫu theo quy tắc (template()).

Mọi con số lấy từ mô hình (report.build_model); AI chỉ được dùng số có trong dữ liệu (ai_writer.ask_checked).
"""
from typing import Literal

from pydantic import BaseModel

from . import ai_writer
from .report import METRIC, n0, p0, p1, pts, tr, vnd, _win


class Action(BaseModel):
    task: str
    owner: str
    deadline: str
    result: str


class Hypothesis(BaseModel):
    hypothesis: str
    result: Literal["ok", "part", "no"]
    evidence: str


class Narrative(BaseModel):
    title_main: str          # trước phần nhấn mạnh
    title_em: str            # phần nhấn mạnh (màu xanh)
    title_tail: str          # sau phần nhấn mạnh, có thể rỗng
    lede: str
    ask_items: list[str]
    impact: str
    trade: str
    summary: list[str]
    overview_h2: str
    overview_chart_title: str
    overview_sowhat: str
    chot_h2: str
    chot_bullets: list[str]
    chot_chart_title: str
    chot_sowhat: str
    giao_h2: str
    giao_bullets: list[str]
    giao_chart_title: str
    giao_sowhat: str
    rev_h2: str
    rev_bullets: list[str]
    rev_chart_title: str
    rev_sowhat: str
    actions_h2: str
    actions: list[Action]
    risks_h2: str
    risks: list[str]
    conclusion: str
    hypotheses: list[Hypothesis]


_S = {"type": "string"}
_LS = {"type": "array", "items": _S}
SCHEMA = {  # khuôn JSON tường minh (không $ref) cho Claude Code --json-schema
    "type": "object", "additionalProperties": False,
    "required": list(Narrative.model_fields),
    "properties": {
        **{k: (_LS if k in ("ask_items", "summary", "chot_bullets", "giao_bullets", "rev_bullets", "risks") else _S)
           for k in Narrative.model_fields if k not in ("actions", "hypotheses")},
        "actions": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                               "required": ["task", "owner", "deadline", "result"],
                                               "properties": {k: _S for k in ("task", "owner", "deadline", "result")}}},
        "hypotheses": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                  "required": ["hypothesis", "result", "evidence"],
                                                  "properties": {"hypothesis": _S, "evidence": _S,
                                                                 "result": {"type": "string", "enum": ["ok", "part", "no"]}}}},
    },
}

SYSTEM_PROMPT = """Bạn là Data Analyst đang trở thành Cố vấn chiến lược của P.DVKH – HV HOLDINGS. Bạn viết Bản tin \
"Nhịp đập kinh doanh" hằng tuần theo skill bao-cao-dinh-ky-consultant, hồ sơ Dashboard "Nhịp đập kinh doanh". \
Code đã tính sẵn mọi con số, bảng và biểu đồ; bạn chỉ viết lời cho từng ô trong khuôn JSON.

Người đọc: trưởng thị trường, trưởng nhóm telesale, vận hành giao hàng, CSKH và quản lý. Họ bận, nghĩ bằng tiền, \
thường chỉ đọc tiêu đề, đoạn mở và khối quyết định.

Bản tin trả lời 4 câu hỏi: tỷ lệ chốt và tỷ lệ giao có đạt KPI không, có tốt hơn tuần trước không, chỗ chưa đạt vì sao, \
làm hụt bao nhiêu doanh thu. Kết luận trước, bằng chứng sau (Kim tự tháp). Ba luận điểm cố định: Tỷ lệ chốt, Tỷ lệ giao, \
Ảnh hưởng doanh thu.

Quy tắc bắt buộc:
- Gọi tên, không đếm: luôn viết rõ chỉ số + thị trường ("tỷ lệ chốt không đạt ở ML, VN"); không viết "7/10 chỉ số đạt", \
"3 chỉ số còn lại", "3/5 thị trường".
- Tiêu đề (title_main + title_em + title_tail, ghép liền thành một câu): chỉ số chưa đạt ở thị trường nào + số tiền hụt \
mỗi tuần + phần còn lại đạt hay xu hướng; cả câu tối đa khoảng 28 từ. title_em là cụm về số tiền hụt. Ví dụ: title_main \
"Tỷ lệ chốt không đạt ở ML, VN và tỷ lệ giao không đạt ở TH", title_em "làm hụt 31,9 triệu mỗi tuần", title_tail ", dù các \
thị trường còn lại đều đạt KPI".
- lede: 3-4 câu theo mạch bối cảnh, vấn đề, hệ quả nếu không làm gì (quy ra tiền), hướng xử lý. Có thể bọc số then chốt \
bằng **...**.
- ask_items: 1-3 việc cần cấp trên duyệt (đổi đơn vị vận chuyển, thay quy trình, dồn nguồn lực), mỗi việc 1 câu. \
impact: một câu tác động bằng tiền. trade: một câu đánh đổi; thiếu số liệu thì nói rõ là chưa lượng hóa được.
- summary: đúng 3 dòng theo thứ tự Tỷ lệ chốt, Tỷ lệ giao, Doanh thu; mỗi dòng có số.
- Mỗi *_h2 là một câu khẳng định (kết luận của phần, tối đa khoảng 22 từ), không phải nhãn chủ đề. *_chart_title là câu kết luận người đọc \
rút ra từ biểu đồ của phần đó (xem mô tả biểu đồ trong dữ liệu), không phải tên biểu đồ.
- *_bullets: 2 gạch đầu dòng ngắn (tối đa khoảng 30 từ), chỉ ý chính; số chi tiết đã nằm trong bảng của phần đó.
- *_sowhat: 1-2 câu, nói tác động kinh doanh và hướng xử lý (không cần viết "Điều này có nghĩa là").
- actions: 3-5 việc, mỗi việc có task, owner (vai trò, ví dụ "Vận hành TH", "Trưởng nhóm telesale ML"), deadline (dùng \
đúng ngày trong trường "han"), result định lượng (dùng mốc "can_them_de_dat" khi nói số đơn cần thêm).
- risks: chỉ các chỉ số trong "rui_ro" (đạt KPI nhưng sát ngưỡng hoặc giảm), mỗi dòng gồm tín hiệu, ngưỡng, phản ứng.
- conclusion: tối đa 2 câu, nhất quán với tiêu đề (không viết dấu "=>", khuôn đã có).
- hypotheses: 4-6 giả thuyết đã kiểm tra theo khâu (chốt: khách đổi ý, không liên lạc được, bom hàng/không hỗ trợ COD, \
một kênh kéo xuống; giao: đơn vị vận chuyển, khách từ chối nhận), result là ok (Xác nhận), part (Một phần) hoặc no \
(Loại trừ), evidence có số.
- Khi không có chỉ số nào chưa đạt ở một khâu: phần đó khẳng định khâu đó đạt ở mọi thị trường và nêu điểm cần giữ; \
khi không có gì cần duyệt, ask_items nêu đề xuất của nhóm phân tích.

Quy tắc số liệu và giọng văn:
- Chỉ dùng con số có trong <du_lieu>, giữ nguyên giá trị và cách viết (dấu phẩy thập phân, ví dụ 85,9%; tiền ví dụ \
"31,9 triệu đồng"). Không tự tính thêm con số mới.
- Phân biệt điểm % (chênh lệch hai tỷ lệ) với %.
- Câu ngắn, chủ động, tiếng Việt kinh doanh; không dùng từ chuyên môn dữ liệu (pipeline, mart, pp, YoY); không biểu tượng \
cảm xúc; không liên kết.
- Giọng chuyên gia: tự tin, điềm tĩnh, nói thẳng. Nhận định về hành vi khách chưa có số liệu thì ghi "giả thuyết" kèm \
cách kiểm chứng; không bịa nguyên nhân ngoài dữ liệu."""


# ---------------------------------------------------------------- dữ liệu cho AI
def _cell_facts(c, total):
    f = {"chi_so": c["label"], "thi_truong": c["market"], "goi_ngan": c["short"], "ty_le": p1(c["value"]),
         "kpi": p0(c["target"]), "so_voi_kpi_diem": pts(c["gap"]), "so_voi_tuan_truoc_diem": pts(c["delta"]),
         "cua_so_don_tao": _win(c["window"]), "tu_so_mau_so": f"{n0(c['num'])}/{n0(c['den'])}"}
    if not c["met"]:
        f.update(don_thieu=c["gap_orders"], can_them_de_dat=c["need_orders"],
                 gia_tri_tb_moi_don=vnd(c["aov"] or 0), hut_moi_tuan=f"{tr(c['rev'])} triệu đồng",
                 ty_trong_trong_tong_hut=p0(c["rev"] / total) if total else "0%",
                 hut_tuan_truoc=f"{tr(c['rev_prev'])} triệu đồng")
    return f


def _why_facts(c):
    w = c["why"]
    if c["metric"] == "chot":
        return {"don_huy": w["cancels"], "don_dang_xu_ly": w["processing"],
                "ly_do_huy": [{"ly_do": r["reason"], "so_don": r["n"], "ty_trong_don_huy": p0(r["share"])} for r in w["reasons"]],
                "khong_ro_ly_do": {"so_don": w["unknown"]["n"], "ty_trong_don_huy": p0(w["unknown"]["share"])},
                "bom_hang_va_khong_ho_tro_cod": {"so_don": w["bom_cod"]["n"], "ty_trong_don_huy": p0(w["bom_cod"]["share"])},
                "kenh_ganh_phan_thieu": [{"kenh": x["seg"], "ty_le_chot": p1(x["rate"]), "so_don": x["den"], "ganh": p0(x["share"])} for x in w["channels"]],
                "sub_bu_ganh_phan_thieu": [{"sub_bu": x["seg"], "ty_le_chot": p1(x["rate"]), "ganh": p0(x["share"])} for x in w["sub_bu"]]}
    f = w["fate"]
    return {"don_da_giao_don_vi_van_chuyen": n0(w["dvvc"]), "don_khong_giao_duoc": w["lost"],
            "don_qua_han": w["overdue"], "ty_trong_qua_han": p0(w["overdue_share"]),
            "don_hoan": w["returns"], "ty_trong_hoan": p0(w["returns_share"]), "don_hoan_co_ghi_ly_do": w["returns_with_reason"],
            "doanh_thu_dang_treo_cua_don_qua_han": f"{tr(w['overdue_rev'])} triệu đồng",
            "don_vi_van_chuyen": [{"ten": x["name"], "don": n0(x["dvvc"]), "ty_le_giao": p1(x["rate"]), "so_voi_kpi_diem": pts(x["diff"]),
                                   "don_qua_han": x["overdue"], "don_hoan": x["returns"]} for x in w["carriers"]],
            "kenh_ganh_phan_thieu": [{"kenh": x["seg"], "ty_le_giao": p1(x["rate"]), "ganh": p0(x["share"])} for x in w["channels"]],
            "don_qua_han_tuan_truoc": None if not f else {
                "so_don_qua_han_luc_gui_ban_tin_tuan_truoc": f["overdue_then"], "da_thanh_hoan": f["returned"],
                "da_giao_duoc": f["delivered"], "van_dang_giao": f["still"]}}


def build_facts(model: dict) -> dict:
    total = model["revenue"]["cur"]
    ov = model["overall"]
    charts = model["charts"]
    return {
        "ky_bao_cao": f"Tuần {model['week']}/{model['year']}, T = Chủ nhật {model['run_date'][8:10]}/{model['run_date'][5:7]}/{model['run_date'][:4]}",
        "loai_kpi": model["kpi_name"], "thi_truong": model["markets"], "han": model["deadlines"],
        "trang_thai": [{"thi_truong": r["market"],
                        **{f"{k}": None if not r[k] else {"ty_le": p1(r[k]["value"]), "kpi": p0(r[k]["target"]), "dat_kpi": r[k]["met"],
                                                         "so_voi_kpi_diem": pts(r[k]["gap"]), "so_voi_tuan_truoc_diem": pts(r[k]["delta"])}
                           for k in METRIC},
                        "ty_le_hoan": p1(r["return_rate"]["cur"]), "ty_le_hoan_tuan_truoc": p1(r["return_rate"]["prev"])}
                       for r in model["rows"]],
        "ty_le_chung_cac_thi_truong": {k: {"ty_le": p1(ov[k]["cur"]), "tuan_truoc": p1(ov[k]["prev"]), "so_voi_tuan_truoc_diem": pts(ov[k]["delta"]),
                                           "dat": ov[k]["met"], "chua_dat": ov[k]["failing"], "vua_dat_lai": ov[k]["recovered"]} for k in METRIC},
        "chua_dat": [{**_cell_facts(c, total), "nguyen_nhan": _why_facts(c)} for c in model["failing"]],
        "vua_dat_lai": [{**_cell_facts(c, total), "hut_tuan_truoc": f"{tr(c['rev_prev'])} triệu đồng"} for c in model["recovered"]],
        "tien_bo_nhat": None if not model["progress"] else {"thi_truong": model["progress"]["market"],
                                                             **{k: pts(v) for k, v in model["progress"]["deltas"].items()}},
        "rui_ro": [_cell_facts(c, total) for c in model["risks"]],
        "doanh_thu_hut": {"tuan_nay": f"{tr(total)} triệu đồng", "tuan_truoc": f"{tr(model['revenue']['prev'])} triệu đồng",
                          "thay_doi": None if model["revenue"]["change"] is None else f"{model['revenue']['change'] * 100:+.0f}%",
                          "neu_keo_dai_4_tuan": f"{tr(model['revenue']['four_weeks'])} triệu đồng",
                          "giu_lai_neu_sua_hai_chi_so_hut_nhieu_nhat": f"{tr(sum(c['rev'] for c in model['failing'][:2]))} triệu đồng"},
        "bieu_do": {k: {"mo_ta": v.get("subtitle"), "chu_thich": (v.get("note") or {}).get("text")} for k, v in charts.items()},
    }


def build_prompt(facts: dict) -> str:
    import json
    return ("Viết lời cho Bản tin Nhịp đập kinh doanh kỳ này từ dữ liệu dưới đây.\n<du_lieu>\n"
            + json.dumps(facts, ensure_ascii=False, indent=1) + "\n</du_lieu>")


def write(model: dict) -> dict:
    """Lời văn do AI viết (đã kiểm tra số liệu); lỗi thì raise để bên gọi dùng template()."""
    facts = build_facts(model)
    return ai_writer.ask_checked(SYSTEM_PROMPT, SCHEMA, Narrative, build_prompt(facts), facts)


# ---------------------------------------------------------------- mẫu theo quy tắc (khi AI lỗi)
def _join(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " và " + xs[-1] if xs else ""


def template(model: dict) -> dict:
    ov, fail, rev = model["overall"], model["failing"], model["revenue"]
    chot_f = [c for c in fail if c["metric"] == "chot"]
    giao_f = [c for c in fail if c["metric"] == "giao"]
    total = rev["cur"]
    dl = model["deadlines"]
    parts = ([f"tỷ lệ chốt không đạt ở {', '.join(ov['chot']['failing'])}"] if ov["chot"]["failing"] else []) + \
            ([f"tỷ lệ giao không đạt ở {', '.join(ov['giao']['failing'])}"] if ov["giao"]["failing"] else [])
    all_met = sorted(set(model["markets"]) - {c["market"] for c in fail})
    if fail:
        title_main = _join(parts)
        title_main = title_main[0].upper() + title_main[1:]
        title_em = f"làm hụt {tr(total)} triệu mỗi tuần"
        title_tail = ", dù các thị trường còn lại đều đạt KPI" if all_met else ""
    else:
        title_main = f"Tỷ lệ chốt và tỷ lệ giao đạt KPI ở {', '.join(model['markets'])}"
        title_em, title_tail = "không hụt doanh thu tuần này", ""

    def status(k):
        o = ov[k]
        name = METRIC[k][0].lower()
        if not o["failing"]:
            return f"{name.capitalize()} đạt KPI ở {', '.join(o['met'])}."
        return f"{name.capitalize()} đạt KPI ở {', '.join(o['met']) or 'không thị trường nào'} nhưng **chưa đạt ở {', '.join(o['failing'])}**."

    chg = rev["change"]
    lede = f"Tuần {model['week']}, {status('chot')[0].lower() + status('chot')[1:]} {status('giao')}"
    if fail:
        lede += (f" {_join(c['short'] for c in fail)} làm doanh thu hụt **{tr(total)} triệu đồng mỗi tuần**"
                 + (f", {'giảm' if chg < 0 else 'tăng'} {abs(chg) * 100:.0f}% so với tuần trước" if chg is not None else "") + ".")
        lede += f" Nếu không xử lý, sau 4 tuần khoản hụt là {tr(rev['four_weeks'])} triệu đồng."
    ask = []
    for c in giao_f[:1]:
        w = c["why"]
        bad = [x for x in w["carriers"] if x["diff"] < 0]
        good = [x["name"] for x in w["carriers"] if x["diff"] >= 0]
        if bad and w["overdue"]:
            ask.append(f"Duyệt yêu cầu {bad[0]['name']} xử lý {n0(w['overdue'])} đơn quá hạn ở {c['market']} trong 48 giờ"
                       + (f"; tuyến chậm chuyển sang {_join(good)}." if good else "."))
    for c in chot_f[:1]:
        ch = c["why"]["channels"]
        if ch:
            ask.append(f"Duyệt cho nhóm telesale {c['market']} ưu tiên gọi xác nhận đơn kênh {ch[0]['seg']}, "
                       f"kênh đang gánh {p0(ch[0]['share'])} phần chốt thiếu.")
    if not ask:
        ask = ["Giữ nguyên cách vận hành hiện tại và theo dõi các chỉ số sát ngưỡng trong mục rủi ro."]
    top2 = fail[:2]
    impact = (f"Tác động: đưa {_join(c['short'] for c in top2)} về KPI giữ lại khoảng {tr(sum(c['rev'] for c in top2))} triệu đồng mỗi tuần."
              if top2 else "Tác động: giữ mức không hụt doanh thu.")
    trade = "Đánh đổi: thay đơn vị vận chuyển hoặc dồn nhân sự có thể làm tăng chi phí; chưa có số liệu chi phí để lượng hóa."

    def sum_line(k):
        o = ov[k]
        fl = [c for c in fail if c["metric"] == k]
        name = METRIC[k][0]
        if not fl:
            return f"{name}: đạt KPI ở {', '.join(o['met'])}, chung {p1(o['cur'])}."
        return f"{name}: chưa đạt ở " + "; ".join(f"{c['market']} (thiếu {pts(c['gap'], False)} điểm %, {pts(c['delta'])} so với tuần trước)" for c in fl) + "."
    summary = [sum_line("chot"), sum_line("giao"),
               f"Doanh thu: hụt {tr(total)} triệu đồng mỗi tuần" + (f", nhiều nhất ở {fail[0]['short']} ({tr(fail[0]['rev'])} triệu)." if fail else ".")]

    def chot_part():
        if not chot_f:
            return (f"Tỷ lệ chốt đạt KPI ở {', '.join(ov['chot']['met'])}", [f"Tỷ lệ chốt chung {p1(ov['chot']['cur'])}, {pts(ov['chot']['delta'])} điểm % so với tuần trước."],
                    "Tỷ lệ chốt các thị trường so với KPI", "Giữ nhịp gọi xác nhận hiện tại.")
        h2 = f"{', '.join(c['market'] for c in chot_f)} chưa đạt KPI chốt"
        bl = []
        for c in chot_f:
            w = c["why"]
            r0 = w["reasons"][0] if w["reasons"] else None
            ch = w["channels"][0] if w["channels"] else None
            bl.append(f"{c['market']} thiếu {pts(c['gap'], False)} điểm %"
                      + (f"; lý do hủy lớn nhất là {r0['reason'].lower()} ({p0(r0['share'])} đơn hủy)" if r0 else "")
                      + (f", kênh {ch['seg']} gánh {p0(ch['share'])} phần thiếu." if ch else "."))
        return h2, bl[:2], "Lý do hủy hàng đầu ở thị trường chưa đạt KPI chốt", \
            f"Cần thêm " + "; ".join(f"{c['need_orders']} đơn chốt mỗi tuần ở {c['market']}" for c in chot_f) + " để đạt KPI."

    def giao_part():
        if not giao_f:
            return (f"Tỷ lệ giao đạt KPI ở {', '.join(ov['giao']['met'])}", [f"Tỷ lệ giao chung {p1(ov['giao']['cur'])}, {pts(ov['giao']['delta'])} điểm % so với tuần trước."],
                    "Tỷ lệ giao các thị trường so với KPI", "Giữ chất lượng giao hiện tại.")
        c = giao_f[0]
        w = c["why"]
        bad = [x for x in w["carriers"] if x["diff"] < 0]
        h2 = f"Tỷ lệ giao chưa đạt ở {', '.join(x['market'] for x in giao_f)}" + (f", phần thiếu nằm ở {bad[0]['name']}" if bad else "")
        bl = [f"{c['market']} thiếu {pts(c['gap'], False)} điểm %: {n0(w['overdue'])} đơn quá hạn ({p0(w['overdue_share'])}) và {n0(w['returns'])} đơn hoàn ({p0(w['returns_share'])}).",
              f"{n0(w['returns_with_reason'])}/{n0(w['returns'])} đơn hoàn có ghi lý do."]
        sw = f"{n0(w['overdue'])} đơn quá hạn là {tr(w['overdue_rev'])} triệu đồng còn cứu được; giao thêm {c['need_orders']} đơn là đủ đạt KPI."
        return h2, bl, "Trạng thái nhóm đơn quá hạn kỳ trước" if w["fate"] else "Tỷ lệ giao theo kênh so với KPI", sw

    ch2, cbl, cct, csw = chot_part()
    gh2, gbl, gct, gsw = giao_part()
    actions = []
    for c in giao_f:
        w = c["why"]
        bad = [x for x in w["carriers"] if x["diff"] < 0]
        actions.append({"task": f"Yêu cầu {bad[0]['name'] if bad else 'đơn vị vận chuyển'} xử lý {n0(w['overdue'])} đơn quá hạn",
                        "owner": f"Vận hành {c['market']}", "deadline": dl["viec_gap"],
                        "result": f"Giao thành công ít nhất {c['need_orders']} đơn, giao {c['market']} đạt {p0(c['target'])}"})
    for c in chot_f:
        ch = c["why"]["channels"]
        actions.append({"task": f"Ưu tiên gọi xác nhận đơn{' kênh ' + ch[0]['seg'] if ch else ''}, bắt buộc chọn lý do hủy",
                        "owner": f"Trưởng nhóm telesale {c['market']}", "deadline": dl["viec_tuan"],
                        "result": f"Thêm {c['need_orders']} đơn chốt mỗi tuần, chốt {c['market']} đạt {p0(c['target'])}"})
    if not actions:
        actions = [{"task": "Theo dõi các chỉ số sát ngưỡng", "owner": "Trưởng thị trường", "deadline": dl["viec_dai"], "result": "Giữ đạt KPI"}]
    risks = [f"{c['short']} {p1(c['value'])}, trên KPI {p0(c['target'])} {pts(c['gap'], False)} điểm %, {pts(c['delta'])} so với tuần trước: "
             f"nếu xuống dưới {p0(c['target'])} cần rà soát ngay." for c in model["risks"]]
    hyps = []
    for c in chot_f:
        w = c["why"]
        if w["reasons"]:
            hyps.append({"hypothesis": f"Chốt {c['market']} thấp do {w['reasons'][0]['reason'].lower()}", "result": "ok" if w["reasons"][0]["share"] >= 0.3 else "part",
                         "evidence": f"{w['reasons'][0]['n']}/{w['cancels']} đơn hủy ({p0(w['reasons'][0]['share'])})"})
        hyps.append({"hypothesis": f"Chốt {c['market']} thấp do bom hàng, khu vực không hỗ trợ COD", "result": "ok" if w["bom_cod"]["share"] >= 0.3 else "no",
                     "evidence": f"{w['bom_cod']['n']}/{w['cancels']} đơn hủy ({p0(w['bom_cod']['share'])})"})
    for c in giao_f:
        w = c["why"]
        bad = [x for x in w["carriers"] if x["diff"] < 0]
        hyps.append({"hypothesis": f"Giao {c['market']} thấp do đơn vị vận chuyển", "result": "ok" if bad else "no",
                     "evidence": f"{bad[0]['name']} giao {p1(bad[0]['rate'])}, có {n0(bad[0]['overdue'])} đơn quá hạn" if bad else "Các đơn vị đều đạt KPI"})
    return {
        "title_main": title_main, "title_em": title_em, "title_tail": title_tail, "lede": lede, "ask_items": ask,
        "impact": impact, "trade": trade, "summary": summary,
        "overview_h2": (f"Chỉ {_join(c['short'] for c in fail)} dưới KPI" if fail else "Mọi chỉ số đạt KPI"),
        "overview_chart_title": "Tỷ lệ chốt và tỷ lệ giao so với KPI theo thị trường",
        "overview_sowhat": "Ưu tiên xử lý theo số tiền hụt, chi tiết ở các phần dưới." if fail else "Giữ nhịp vận hành hiện tại.",
        "chot_h2": ch2, "chot_bullets": cbl, "chot_chart_title": cct, "chot_sowhat": csw,
        "giao_h2": gh2, "giao_bullets": gbl, "giao_chart_title": gct, "giao_sowhat": gsw,
        "rev_h2": f"{_join(c['short'] for c in fail)} làm hụt {tr(total)} triệu đồng mỗi tuần" if fail else "Không hụt doanh thu tuần này",
        "rev_bullets": [f"Nếu giữ nguyên mức này thêm 4 tuần, tổng hụt là {tr(rev['four_weeks'])} triệu đồng."] if fail else ["Không có chỉ số nào dưới KPI."],
        "rev_chart_title": "Doanh thu hụt theo chỉ số, tuần trước và tuần này",
        "rev_sowhat": "Mỗi chỉ số kéo về KPI là tiền quay lại ngay; ưu tiên theo số tiền hụt." if fail else "Giữ mức hiện tại.",
        "actions_h2": "Việc cần làm để đưa các chỉ số về KPI" if fail else "Việc cần làm tuần tới",
        "actions": actions, "risks_h2": "Chỉ số đang đạt nhưng cần theo dõi", "risks": risks,
        "conclusion": (f"Ưu tiên số một là {fail[0]['short']}, nơi hụt nhiều nhất ({tr(fail[0]['rev'])} triệu đồng mỗi tuần)." if fail
                       else "Tuần này mọi chỉ số đạt KPI; giữ nhịp và theo dõi các chỉ số sát ngưỡng."),
        "hypotheses": hyps,
    }
