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
| `pipeline/metrics.py` | SQL BigQuery + tính 8 chỉ số |
| `pipeline/analysis.py` | Phân tích 4 cấp độ |
| `pipeline/ai_writer.py` | AI Analyst: đọc dữ liệu Dashboard, viết bản tin (Claude API), kiểm tra số liệu |
| `pipeline/bulletin.py` | Khung bản tin Lark (Kim tự tháp Minto, giọng "loa phường"); mẫu dự phòng khi AI lỗi |
| `pipeline/lark.py` | Lark app bot: tenant token, gửi card theo chat_id, liệt kê nhóm |
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
2. **Permissions & Scopes**: thêm `im:message:send_as_bot` (gửi tin) và `im:chat:readonly` (liệt kê nhóm để lấy chat_id).
3. **Version Management & Release**: tạo phiên bản mới và phát hành để quyền có hiệu lực.
4. Trong từng nhóm chat Lark (VD "Sinh tồn", "KPI tháng"): **Settings → Bots → Add bot → AI Analyst HVH**.

### 4. GitHub Secrets (Settings → Secrets and variables → Actions)
| Secret | Giá trị |
|---|---|
| `GCP_SA_KEY` | Nội dung file khóa JSON của service account |
| `LARK_APP_ID` | App ID (`cli_…`) |
| `LARK_APP_SECRET` | App Secret (mục Credentials & Basic Info) |
| `DASHBOARD_PASSWORD` | Mật khẩu mở dashboard (gửi cho người được xem) |
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
- **Tab Tổng quan**: bộ lọc Loại báo cáo (Tuần / Tháng / Quý), Từ – Đến, Thị trường, BU, Kênh bán, Team, Seller, SubBrand,
  SKU / Sản phẩm (tìm theo mã hoặc tên), Province →
  1. 3 thẻ KPI (tỷ lệ chốt, tỷ lệ giao, tỷ lệ giao thành công từ data sạch) của kỳ cuối, so với kỳ trước và KPI;
  2. Bảng tổng hợp theo thị trường × kỳ, dòng phụ so với KPI sinh tồn / KPI tháng (xanh đạt, cam thiếu < `near_pp` điểm %,
     đỏ không đạt), cột xu hướng (sparkline) và cảnh báo;
  3. Bảng chi tiết theo tab Thị trường / BU / Kênh bán / Team / Seller / SubBrand / SKU / Province với đủ 16 chỉ số;
  4. Top lý do hủy đơn và top lý do hoàn (số đơn, tỷ trọng).
- **Dữ liệu**: mỗi lần build, `pipeline/cube.py` gom đơn data sạch theo ngày tạo × chiều lọc × trạng thái × lý do
  (~400 ngày gần nhất), nén + mã hóa thành `docs/data/cube.json`; trình duyệt tự lọc và tính (vài chục ms).
  Kỳ tuần dùng đúng quy tắc cửa sổ của bản tin nên số trên Dashboard khớp bản tin.
- **Tab Bản tin**: menu lịch sử bản tin bên trái, bản tin mới nhất hiển thị chính; duyệt / viết lại / hủy bản nháp.
- **Tab Cấu hình**: nhóm nhận bản tin, AI Analyst & duyệt, lịch gửi, KPI, kết nối GitHub, nhật ký gửi.

## Bản tin: AI viết → duyệt → gửi
- **Kết nối AI**: với gói Claude Pro/Max, workflow chạy Claude Code CLI không tương tác (`claude -p --json-schema …`)
  bằng `CLAUDE_CODE_OAUTH_TOKEN`; lượt dùng tính vào hạn mức của gói (mỗi bản tin ~1 phút). Có `ANTHROPIC_API_KEY` thì gọi
  Claude API trực tiếp.
- **AI Analyst** (Claude, model `claude-opus-5-5`) đọc đúng bộ dữ liệu Dashboard của kỳ báo cáo: chỉ số, KPI,
  so với tuần trước và các phát hiện code đã tính sẵn (phân khúc gây thiếu hụt, lý do hủy/hoàn). AI viết kết luận,
  4 cấp độ cho từng chỉ số không đạt và đề xuất hành động. AI không tự tính số.
- **Kiểm tra số liệu**: mọi con số trong bài phải có trong dữ liệu; sai thì AI viết lại 1 lần, vẫn sai hoặc AI lỗi
  thì bản tin dùng mẫu theo quy tắc (không bao giờ lỡ lịch). Bản tin ghi rõ "AI Analyst" hay "mẫu quy tắc".
- **Duyệt** (bật mặc định, tab Cấu hình → *AI Analyst & duyệt bản tin*): đến lịch, bản tin thành **bản nháp**, gửi vào
  **nhóm duyệt** (tùy chọn) với nhãn [NHÁP]. Vào Dashboard → tab **Bản tin**: **Duyệt gửi** / **Viết lại** / **Hủy**.
  Tắt duyệt thì bản tin gửi thẳng tới các nhóm theo lịch.
- Bản nháp lưu mã hóa trong `docs/data/drafts.json`.

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
