# Nhịp đập kinh doanh — Cảnh báo tỷ lệ chốt, tỷ lệ giao (P.DVKH)

Chạy hoàn toàn trên GitHub, không cần server:

```
GitHub Actions (mỗi 30 phút)                       GitHub Pages (https://<owner>.github.io/<repo>/)
  ├─ BigQuery API: hv-data.a_data_mart.sales_orders     └─ docs/index.html đọc docs/data/*.json (mã hóa AES-256)
  ├─ tính chỉ số + phân tích 4 cấp độ                        ├─ Dashboard / Lịch sử gửi
  ├─ ghi docs/data (mã hóa) + state/send_log.json            └─ Cấu hình → commit config/config.json qua GitHub API
  └─ Bot Lark "AI Analyst HVH" gửi bản tin tới chat_id           Gửi ngay / Làm mới → kích hoạt workflow
```

## Cấu trúc
| Đường dẫn | Vai trò |
|---|---|
| `config/config.json` | KPI, thời gian TB chốt/giao, nhóm nhận bản tin (`recipients`), lịch gửi — sửa trên dashboard |
| `tools/test-lark.ps1` | Thử gửi tin bằng Bot ngay trên máy Windows (không cần GitHub) |
| `pipeline/metrics.py` | SQL BigQuery + tính 8 chỉ số |
| `pipeline/analysis.py` | Phân tích 4 cấp độ |
| `pipeline/bulletin.py` | Bản tin Lark (Kim tự tháp Minto, giọng "loa phường") |
| `pipeline/lark.py` | Lark app bot: tenant token, gửi card theo chat_id, liệt kê nhóm |
| `pipeline/run.py` | `tick` / `build` / `send` / `test` / `chats` |
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

**Settings → Pages → Build and deployment**: *Deploy from a branch* → `main` / `/docs`.
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
