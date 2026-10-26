# Gửi thử một card bản tin (file JSON) vào nhóm Lark bằng Bot — để xem trước định dạng trên Lark.
# Chạy:  powershell -ExecutionPolicy Bypass -File tools\send-card.ps1 -CardFile <đường dẫn card.json>
param(
  [Parameter(Mandatory = $true)][string]$CardFile,
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
  if ($Body) { $req["Body"] = [Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 50 -Compress)) }
  try { $r = Invoke-RestMethod @req } catch { $raw = $_.ErrorDetails.Message; if ($raw) { $r = $raw | ConvertFrom-Json } else { throw } }
  if ($r.code -ne 0) { throw "Lark lỗi $($r.code): $($r.msg)" }
  return $r
}

$cardJson = [IO.File]::ReadAllText($CardFile, [Text.Encoding]::UTF8)
$card = $cardJson | ConvertFrom-Json
$card.header.title.content = "[THỬ] " + $card.header.title.content
$content = $card | ConvertTo-Json -Depth 50 -Compress

$sec = Read-Host "Nhập App Secret của $AppId" -AsSecureString
$secret = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
$token = (Call-Lark POST "/open-apis/auth/v3/tenant_access_token/internal" @{ app_id = $AppId; app_secret = $secret }).tenant_access_token

$chats = @((Call-Lark GET "/open-apis/im/v1/chats?page_size=100" $null $token).data.items)
for ($i = 0; $i -lt $chats.Count; $i++) { Write-Host ("  [{0}] {1}" -f $i, $chats[$i].name) }
$pick = Read-Host "Chọn số nhóm nhận bản tin THỬ (Enter để hủy)"
if ($pick -eq "") { exit 0 }
$chat = $chats[[int]$pick]
$r = Call-Lark POST "/open-apis/im/v1/messages?receive_id_type=chat_id" @{ receive_id = $chat.chat_id; msg_type = "interactive"; content = $content } $token
Write-Host "Đã gửi bản tin THỬ vào '$($chat.name)'. message_id = $($r.data.message_id)" -ForegroundColor Green
