# Nhịp đập kinh doanh — Cảnh báo tỷ lệ chốt, tỷ lệ giao (P.DVKH)

Chạy hoàn toàn trên GitHub, không cần server:

Luồng làm việc của một Data Analyst: **Dashboard** (dữ liệu tự cập nhật) → **AI Analyst đọc dữ liệu Dashboard và viết
bản tin** → người duyệt → gửi nhóm Lark.

```
BigQuery ──API──▶ dữ liệu Dashboard (docs/data, mã hóa) ──▶ GitHub Pages: Dashboard · Bản tin · Cấu hình · Lịch sử
                         │
                         ▼  (đến lịch gửi)
                  AI Analyst (Claude) viết bản tin ── kiểm tra số liệu ──▶ BẢN NHÁP ──▶ nhóm duyệt (Lark)
                                                                                │  bấm "Duyệt gửi" trên Dashboard
                                                                                ▼
                                                              Bot "AI Analyst HVH" gửi tới các nhóm đã đăng ký
```

## Cấu trúc
| Đường dẫn | Vai trò |
|---|---|
| `config/config.json` | KPI, thời gian TB chốt/giao, nhóm nhận bản tin (`recipients`), lịch gửi — sửa trên dashboard |
| `tools/test-lark.ps1` | Thử gửi tin bằng Bot ngay trên máy Windows (không cần GitHub) |
| `pipeline/metrics.py` | SQL BigQuery + tính 8 chỉ số (kỳ này và kỳ trước) |
| `pipeline/report.py` | Mô hình số liệu Bản tin: trạng thái chốt/giao so với KPI, nguyên nhân, doanh thu hụt, dữ liệu biểu đồ |
| `pipeline/reasons.py` | Gộp lý do hủy/hoàn cùng nghĩa khác ngôn ngữ (Việt, Anh, Thái, Indonesia) |
| `pipeline/report_writer.py` | Lời văn Bản tin: AI Analyst viết theo skill bao-cao-dinh-ky-consultant; mẫu theo quy tắc khi AI lỗi |
| `pipeline/report_html.py` · `templates/report.html` | Dựng Bản tin HTML từ khuôn mẫu đã duyệt (logo, màu thương hiệu, biểu đồ) |
| `pipeline/report_image.py` | Chụp Bản tin HTML thành ảnh JPEG (Playwright, chỉ cài khi gửi) |
| `pipeline/ai_writer.py` | Gọi Claude (gói Pro/Max hoặc API), kiểm tra số liệu và cách gọi tên |
| `pipeline/bulletin.py` | Card Lark tóm tắt Bản tin (tiêu đề, đoạn mở, khối quyết định, 4 thẻ KPI, Đọc nhanh, kết luận) |
| `pipeline/lark.py` | Lark app bot: tenant token, gửi card và ảnh theo chat_id, liệt kê nhóm |
| `pipeline/run.py` | `tick` / `build` / `send` / `test` / `chats` / `approve` / `redraft` / `reject` |
| `.github/workflows/nhip-dap.yml` | Lịch chạy + chạy tay |
| `docs/` | Trang GitHub Pages; `docs/data/` do workflow sinh ra |
| `state/send_log.json` | Nhật ký gửi, chống gửi trùng |

## Cài đặt (một lần)

### 1. Đưa lên GitHub bằng GitHub Desktop
1. GitHub Desktop → **File → Add local repository…** → chọn thư mục dự án → **Add repository**.
2. Bấm **Publish repository**: đặt tên (vd `HVH-nhip-dap-kinh-doanh`), **bỏ tick "Keep this code private"**
   (GitHub Pages miễn phí cần repo public) → **Publish repository**.
3. Bấm **View on GitHub** để mở repo trên trình duyệt, làm tiếp các bước dưới.
4. Mỗi khi sửa code trên máy: GitHub Desktop → **Fetch/Pull origin** (lấy dữ liệu bot vừa commit) → nhập mô tả → **Commit to main** → **Push origin**.

**Settings → Pages → Build and deployment → Source**: chọn **GitHub Actions** (workflow tự triển khai thư mục `docs/`
sau mỗi lần cập nhật dữ liệu; commit của bot không tự kích hoạt kiểu "Deploy from a branch").
Trang sẽ ở `https://<owner>.github.io/<repo>/`.

GitHub Pages miễn phí yêu cầu repo **public**: mã nguồn và `config/config.json` (KPI, chat_id) ai cũng xem được.
   Số liệu kinh doanh trong `docs/data` luôn được **mã hóa** bằng `DASHBOARD_PASSWORD`; App Secret và khóa GCP chỉ nằm trong GitHub Secrets.

### 2. BigQuery (Google Cloud)
Tạo service account, cấp **BigQuery Job User** trên project `hv-data` và **BigQuery Data Viewer** trên dataset `a_data_mart`,
tạo khóa JSON → lưu nguyên nội dung vào secret `GCP_SA_KEY`.

### 3. Lark app "AI Analyst HVH" (open.larksuite.com/app)
1. **Add Features → Bot**: bật Bot.
2. **Permissions & Scopes**: thêm `im:message:send_as_bot` (gửi tin), `im:chat:readonly` (liệt kê nhóm để lấy chat_id)
   và `im:resource` (tải ảnh Bản tin đầy đủ lên Lark).
3. **Version Management & Release**: tạo phiên bản mới và phát hành để quyền có hiệu lực.
4. Trong từng nhóm chat Lark (VD "Sinh tồn", "KPI tháng"): **Settings → Bots → Add bot → AI Analyst HVH**.

### 4. GitHub Secrets (Settings → Secrets and variables → Actions)
| Secret | Giá trị |
|---|---|
| `GCP_SA_KEY` | Nội dung file khóa JSON của service account |
| `LARK_APP_ID` | App ID (`cli_…`) |
| `LARK_APP_SECRET` | App Secret (mục Credentials & Basic Info) |
| `DASHBOARD_PASSWORD` | Mật khẩu mã hóa dữ liệu Dashboard. Đã bật phân quyền thì không cần phát cho ai (xem *Phân quyền người dùng*) |
| `CLAUDE_CODE_OAUTH_TOKEN` | **Dùng gói Claude Pro/Max** cho AI Analyst: trên máy chạy `claude setup-token`, đăng nhập, dán token nhận được (`sk-ant-oat…`) |
| `ANTHROPIC_API_KEY` | *(Thay thế)* API key trả phí theo lượng dùng tại platform.claude.com. Có cả hai thì dùng API key |

### 5. Chạy lần đầu
1. **Actions → Nhịp đập kinh doanh → Run workflow**, `cmd = build`. Sau ~2 phút mở trang Pages, nhập mật khẩu.
2. Tab **Cấu hình** → mở **Kết nối GitHub** ở cuối trang, nhập token (fine-grained, chỉ repo này, quyền
   *Contents: Read and write* + *Actions: Read and write*). Chỉ cần một lần trên mỗi máy.

## Chọn nhóm nhận bản tin
Bot đã kết nối API một lần (Secrets), mọi thứ còn lại tự động:
1. Trong Lark, thêm Bot **AI Analyst HVH** vào nhóm.
2. Tab Cấu hình → **Nhóm nhận bản tin** → **+ Thêm nhóm**: chọn nhóm trong danh sách các nhóm có Bot
   (nhóm mới hiện trong ≤ 30 phút, hoặc bấm **Làm mới**).
3. Bên phải chỉ hiện cấu hình của nhóm đang chọn: tick **Cảnh báo KPI sinh tồn** và/hoặc **KPI tháng**, giới hạn thị trường
   nếu cần. Thay đổi tự lưu; bấm **Gửi thử** để kiểm tra.

Bấm **Bỏ nhóm khỏi danh sách** = nhóm ngừng nhận. Xóa Bot khỏi nhóm trong Lark = hệ thống tự ngừng gửi (nhóm hiện nhãn "Bot đã rời nhóm").
Nhóm đổi tên trong Lark thì tên trên dashboard và bản tin tự cập nhật.

## Dashboard "Báo cáo chất lượng chuyển đổi"
- **Logo**: đặt file logo gốc (PNG/SVG nền trong suốt) tại `docs/assets/logo.png`; chưa có file thì hiển thị chữ "HV HOLDINGS".
  Màu theo bảng màu thương hiệu (#26a557, #71bf44, #06a7e1, #58585a); đỏ / cam chỉ dùng cho không đạt / gần đạt / xấu đi.
- **Tab Tổng quan**: bộ lọc Loại báo cáo (Tuần / Tháng / Quý), Từ – Đến, Thị trường, BU, Kênh bán, Nhóm, Nhân viên, SubBrand,
  SKU / Sản phẩm (tìm theo mã hoặc tên), Tỉnh →
  1. 3 thẻ KPI (tỷ lệ chốt, tỷ lệ giao, tỷ lệ giao thành công từ data sạch) của kỳ cuối, so với kỳ trước và KPI;
  2. Bảng tổng hợp theo thị trường × kỳ, dòng phụ so với KPI sinh tồn / KPI tháng (xanh đạt, cam thiếu < `near_pp` điểm %,
     đỏ không đạt), cột xu hướng (sparkline) và cảnh báo;
  3. Bảng chi tiết theo tab Thị trường / BU / Kênh bán / Nhóm / Nhân viên / SubBrand / SKU / Tỉnh với đủ 16 chỉ số
     (cột đầu cố định khi cuộn ngang);
  4. Top lý do hủy đơn và top lý do hoàn (số đơn, tỷ trọng).
- **Dữ liệu**: mỗi lần build, `pipeline/cube.py` gom đơn data sạch theo ngày tạo × chiều lọc × trạng thái × lý do
  (~400 ngày gần nhất), nén + mã hóa thành `docs/data/cube.json`; trình duyệt tự lọc và tính (vài chục ms).
  Kỳ tuần dùng đúng quy tắc cửa sổ của bản tin nên số trên Dashboard khớp bản tin.
- **Tab Bản tin**: menu lịch sử bản tin bên trái, bản tin mới nhất hiển thị chính; duyệt / viết lại / hủy bản nháp.
- **Tab Cấu hình** (chỉ Admin): nhóm nhận bản tin, AI Analyst & duyệt, lịch gửi, KPI, phân quyền người dùng,
  kết nối GitHub, nhật ký gửi.

## Phân quyền người dùng
- **Admin**: chỉnh cấu hình, duyệt / viết lại / hủy bản tin, quản lý người dùng. **View**: chỉ xem Tổng quan và Bản tin
  (không thấy tab Cấu hình, không có nút duyệt).
- **Bật lần đầu**: mở Dashboard bằng mật khẩu chung → tab Cấu hình → nhập GitHub token ở *Kết nối GitHub* →
  *Phân quyền người dùng* → **Bật phân quyền**, tạo tài khoản Admin của chính mình. Từ đó mọi người đăng nhập bằng
  email + mật khẩu; token trở thành token dùng chung cho mọi Admin (không cần nhập trên từng máy).
- **Thêm người dùng**: **+ Thêm người dùng** → email, tên, quyền, mật khẩu tạm (≥ 10 ký tự). Gửi mật khẩu tạm riêng cho
  người đó. Đổi quyền hoặc quên mật khẩu: **Đổi quyền / mật khẩu** (cấp mật khẩu mới). Mỗi người tự đổi được mật khẩu khi là Admin;
  View nhờ Admin đặt lại.
- **Cơ chế**: `docs/data/users.json` công khai nhưng chỉ chứa dữ liệu đã mã hóa — mỗi tài khoản là một hộp khóa mở bằng
  mật khẩu của chính người đó (PBKDF2 600.000 vòng + AES-256-GCM), tra cứu theo mã băm email. Hộp khóa của View chỉ mở được
  mật khẩu dữ liệu; hộp khóa của Admin mở thêm GitHub token. Vì vậy View không thể ghi gì kể cả khi tự sửa trang.
  Tên Admin bấm duyệt / hủy được ghi vào bản tin ("duyệt bởi …").
- **Sau khi bật**: mật khẩu chung cũ vẫn mở được dữ liệu ("Đăng nhập khôi phục"). Đổi nó: cập nhật Secret
  `DASHBOARD_PASSWORD` trên GitHub, rồi Cấu hình → *Phân quyền người dùng* → **Đổi mật khẩu dữ liệu**, nhập đúng mật khẩu mới.
- **Khôi phục**: nếu không còn Admin nào đăng nhập được, chủ repo dùng "Đăng nhập khôi phục" (DASHBOARD_PASSWORD) + GitHub
  token → **Tạo lại phân quyền** (xóa toàn bộ tài khoản cũ, cấp lại từ đầu).
- **Xóa tài khoản** chặn đăng nhập ngay. Người am hiểu kỹ thuật có thể đã lưu lại khóa khi còn quyền; muốn thu hồi tuyệt đối
  thì đổi mật khẩu dữ liệu, đổi GitHub token, rồi Tạo lại phân quyền.

## Bản tin: AI viết → duyệt → gửi
- **Kết nối AI**: với gói Claude Pro/Max, workflow chạy Claude Code CLI không tương tác (`claude -p --json-schema …`)
  bằng `CLAUDE_CODE_OAUTH_TOKEN`; lượt dùng tính vào hạn mức của gói (mỗi bản tin ~1 phút). Có `ANTHROPIC_API_KEY` thì gọi
  Claude API trực tiếp.
- **Nội dung** theo mẫu đã duyệt (skill `bao-cao-dinh-ky-consultant`, hồ sơ "Nhịp đập kinh doanh"), trả lời 4 câu hỏi:
  tỷ lệ chốt / tỷ lệ giao có đạt KPI không, có tốt hơn tuần trước không, chưa đạt vì sao, hụt bao nhiêu doanh thu.
  Bố cục: tiêu đề gọi tên chỉ số + thị trường chưa đạt, câu hỏi kỳ này, đoạn mở, khối quyết định, 4 thẻ KPI (tỷ lệ chung),
  Đọc nhanh, Bức tranh tổng, 3 luận điểm (Tỷ lệ chốt, Tỷ lệ giao, Ảnh hưởng doanh thu) mỗi phần có bảng + biểu đồ,
  kế hoạch hành động, rủi ro, kết luận "=>", phụ lục giả thuyết, giải thích thuật ngữ.
- **Ai làm gì**: code (`report.py`) tính mọi con số, bảng và biểu đồ; AI Analyst (Claude, model `claude-opus-5-5`) chỉ viết
  lời. Mọi con số AI viết phải có trong dữ liệu và không được viết kiểu "x/y chỉ số"; sai thì AI viết lại 1 lần, vẫn sai
  số hoặc AI lỗi thì dùng mẫu theo quy tắc (không bao giờ lỡ lịch). Bản tin ghi rõ "AI Analyst" hay "mẫu quy tắc".
- **Gửi vào Lark**: một card tóm tắt (lớp đọc 30 giây) và ngay sau đó là **ảnh toàn bộ bản tin** (chụp bằng Chromium
  không giao diện). Ảnh tải lên Lark một lần lúc tạo bản nháp, duyệt gửi dùng lại ảnh đó. Thiếu quyền `im:resource` thì
  vẫn gửi card và báo lỗi ảnh ở tab Bản tin.
- **Đơn quá hạn tuần trước**: mỗi tuần lưu số đơn cửa sổ giao vào `state/giao_snapshots.json`; tuần sau bản tin cho biết
  nhóm đơn quá hạn đó đã thành hoàn, giao được hay vẫn đang giao.
- **Duyệt** (bật mặc định, tab Cấu hình → *AI Analyst & duyệt bản tin*): đến lịch, bản tin thành **bản nháp**, gửi vào
  **nhóm duyệt** (tùy chọn) với nhãn [NHÁP] kèm ảnh. Vào Dashboard → tab **Bản tin** xem bản tin đầy đủ hoặc card Lark,
  bấm **Duyệt gửi** / **Viết lại** / **Hủy**. Tắt duyệt thì bản tin gửi thẳng tới các nhóm theo lịch.
- Bản nháp lưu mã hóa trong `docs/data/drafts.json` (bản tin HTML giữ cho 12 bản nháp gần nhất).

## Vận hành
- **Lịch gửi**: workflow chạy mỗi 30 phút; lịch đến hạn (theo `timezone` trong cấu hình) gửi tới mọi nhóm đã tick ở lượt
  chạy kế tiếp, thường trễ 5–60 phút do GitHub cron. Lượt bị trễ quá 6 giờ thì bỏ qua. Mỗi nhóm chỉ nhận 1 lần cho mỗi
  lần hẹn; nhóm gửi lỗi được thử lại ở lượt sau.
- **Danh sách nhóm Lark** được đồng bộ mỗi lượt 30 phút (chỉ gọi Lark, không truy vấn BigQuery) và chỉ commit khi có thay đổi.
- **Dữ liệu dashboard** tự làm mới mỗi ~20 giờ, khi đến lịch gửi, khi sửa `config/config.json`, hoặc bấm *Làm mới dữ liệu ngay*.
  Giữ phân tích 26 tuần, biểu đồ xu hướng 12 tuần; 4 tuần gần nhất được tính lại mỗi lần build vì trạng thái đơn còn thay đổi.
- **Chi phí BigQuery**: mỗi lần build 1 truy vấn tổng hợp + 4 truy vấn phân tích (~0,1–0,2 GB/truy vấn).
- GitHub tắt lịch chạy của repo public không có hoạt động 60 ngày; các commit dữ liệu của workflow giữ repo luôn hoạt động.

## Quy tắc tính
| Khái niệm | Cách tính |
|---|---|
| Data sạch | Đơn duy nhất (`order_key`), `date_type = 'Ngày tạo đơn'`, `abandoned_order_label = 'Đơn thường'`, `all_tag_names` không chứa "trùng"/"test"/"spam", `group_code != 'DELETED'` |
| Đơn chốt / hủy / đang xử lý / chờ giao / giao DVVC / GTC / hoàn | Theo `group_code` như tài liệu |
| Cửa sổ chốt | 7 ngày tạo đơn kết thúc tại **T − thời gian TB chốt đơn** |
| Cửa sổ giao | 7 ngày tạo đơn kết thúc tại **T − thời gian TB giao hàng** |
| So sánh tuần trước | Cùng cửa sổ lùi 7 ngày |

KPI "giao thành công từ data sạch" = KPI chốt × KPI giao (khớp ML 72%, PH 70%, ID 72%; TH, VN suy ra cùng công thức).
CAM chưa có KPI nên chỉ hiển thị.

## Chạy trên máy (tùy chọn)
```bash
pip install -r requirements.txt
gcloud auth application-default login
python -m pipeline.run build
```
Đặt thêm `LARK_APP_ID`, `LARK_APP_SECRET`, `DASHBOARD_PASSWORD` nếu cần gửi tin / mã hóa.
