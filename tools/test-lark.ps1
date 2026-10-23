# Kiểm tra luồng gửi tin Lark bằng Bot của Lark app (không cần Webhook).
# Chạy:  powershell -ExecutionPolicy Bypass -File tools\test-lark.ps1
# App Secret chỉ nhập vào cửa sổ này, không lưu ở đâu.
param(
  [string]$AppId = "cli_aa5b4a1a70b85f0a",
  [string]$Base = "https://open.larksuite.com"
)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Call-Lark($Method, $Path, $Body = $null, $Token = $null) {
  $headers = @{}
  if ($Token) { $headers["Authorization"] = "Bearer $Token" }
  $req = @{ Method = $Method; Uri = "$Base$Path"; Headers = $headers; ContentType = "application/json; charset=utf-8" }
  if ($Body) { $req["Body"] = [Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 20 -Compress)) }
  try { $r = Invoke-RestMethod @req }
  catch {
    $raw = $_.ErrorDetails.Message
    if ($raw) { $r = $raw | ConvertFrom-Json } else { throw }
  }
  if ($r.code -ne 0) {
    $hint = switch ($r.code) {
      99991663 { "App Secret/App ID sai." }
      99991672 { "Thiếu quyền: thêm im:chat:readonly và im:message:send_as_bot ở Permissions & Scopes, rồi phát hành phiên bản mới." }
      230002   { "Bot chưa có trong nhóm này." }
      230006   { "Chưa bật tính năng Bot (Add Features → Bot) hoặc chưa phát hành phiên bản." }
      default  { "" }
    }
    throw "Lark lỗi $($r.code): $($r.msg). $hint"
  }
  return $r
}

$sec = Read-Host "Nhập App Secret của $AppId" -AsSecureString
$secret = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))

Write-Host "`n1) Lấy tenant_access_token..." -ForegroundColor Cyan
$token = (Call-Lark POST "/open-apis/auth/v3/tenant_access_token/internal" @{ app_id = $AppId; app_secret = $secret }).tenant_access_token
Write-Host "   OK"

Write-Host "`n2) Các nhóm Bot đang tham gia:" -ForegroundColor Cyan
$chats = @(); $pageToken = ""
try {
  do {
    $q = "?page_size=100" + $(if ($pageToken) { "&page_token=$pageToken" } else { "" })
    $d = (Call-Lark GET "/open-apis/im/v1/chats$q" $null $token).data
    $chats += @($d.items); $pageToken = $d.page_token
  } while ($d.has_more)
} catch {
  Write-Host "   Không đọc được danh sách nhóm: $($_.Exception.Message)" -ForegroundColor Yellow
}
if ($chats.Count) {
  for ($i = 0; $i -lt $chats.Count; $i++) { Write-Host ("   [{0}] {1}   chat_id = {2}" -f $i, $chats[$i].name, $chats[$i].chat_id) }
  $pick = Read-Host "`nChọn số nhóm để gửi tin thử (Enter để bỏ qua)"
  if ($pick -eq "") { exit 0 }
  $chat = $chats[[int]$pick]
} else {
  Write-Host "   (Bot chưa ở trong nhóm nào, hoặc app thiếu quyền im:chat:readonly)" -ForegroundColor Yellow
  $manual = Read-Host "`nNếu đã biết chat_id (dạng oc_...), nhập vào đây để gửi thử; Enter để thoát"
  if ($manual -eq "") { exit 1 }
  $chat = [pscustomobject]@{ chat_id = $manual.Trim(); name = $manual.Trim() }
}

Write-Host "`n3) Gửi tin thử vào '$($chat.name)'..." -ForegroundColor Cyan
$card = @{
  config   = @{ wide_screen_mode = $true }
  header   = @{ template = "blue"; title = @{ tag = "plain_text"; content = "📢 Nhịp đập kinh doanh · Kiểm tra kết nối" } }
  elements = @(
    @{ tag = "markdown"; content = "Alo alo! Nhóm **$($chat.name)** đã kết nối với Bot **AI Analyst HVH** để nhận bản tin *Nhịp đập kinh doanh*." },
    @{ tag = "note"; elements = @(@{ tag = "plain_text"; content = "Tin kiểm tra gửi lúc $(Get-Date -Format 'HH:mm dd/MM/yyyy')" }) }
  )
}
$r = Call-Lark POST "/open-apis/im/v1/messages?receive_id_type=chat_id" @{
  receive_id = $chat.chat_id; msg_type = "interactive"; content = ($card | ConvertTo-Json -Depth 20 -Compress)
} $token
Write-Host "   Đã gửi. message_id = $($r.data.message_id)" -ForegroundColor Green
Write-Host "`nDán chat_id này vào nhóm tương ứng trong config/config.json (hoặc tab Cấu hình trên dashboard):"
Write-Host "   $($chat.chat_id)" -ForegroundColor Green
