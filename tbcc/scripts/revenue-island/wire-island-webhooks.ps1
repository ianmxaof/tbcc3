# Print + optionally open dashboard URLs to wire Gumroad Ping + NOWPayments IPN to the island API.
#
#   .\scripts\revenue-island\wire-island-webhooks.ps1
#   .\scripts\revenue-island\wire-island-webhooks.ps1 -HostName root@5.161.53.91 -OpenBrowser

param(
  [string]$HostName = "root@5.161.53.91",
  [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"
$remoteUrlFile = "/opt/tbcc/infra/.api-public-url"
$raw = & ssh $HostName "cat $remoteUrlFile 2>/dev/null || grep -E '^TBCC_PUBLIC_API_BASE_URL=' /opt/tbcc/infra/.env.revenue-island | head -1"
$base = ""
foreach ($line in ($raw -split "`n")) {
  $t = $line.Trim()
  if ($t -match '^TBCC_PUBLIC_API_BASE_URL=(.+)$') { $base = $Matches[1].Trim(); break }
  if ($t -match '^https://') { $base = $t; break }
}
if (-not $base) { throw "Could not read public API base from island ($remoteUrlFile)" }
$base = $base.TrimEnd("/")

$gumroadPing = "$base/webhooks/gumroad"
$nowpaymentsIpn = "$base/webhooks/nowpayments"

Write-Host ""
Write-Host "=== Island webhook URLs (copy into dashboards) ===" -ForegroundColor Cyan
Write-Host "Public API base:  $base"
Write-Host "Gumroad Ping:     $gumroadPing"
Write-Host "NOWPayments IPN:  $nowpaymentsIpn"
Write-Host ""
Write-Host "Gumroad: Settings -> Advanced -> Ping -> paste Ping URL above" -ForegroundColor Yellow
Write-Host "NOWPayments: Payment Settings -> IPN callback URL (optional; TBCC also sends per-invoice ipn_callback_url)" -ForegroundColor Yellow
Write-Host ""

if ($OpenBrowser) {
  Start-Process "https://gumroad.com/settings/advanced"
  Start-Process "https://account.nowpayments.io/store-settings"
}

# Clipboard (Windows)
try {
  Set-Clipboard -Value "$gumroadPing`n$nowpaymentsIpn"
  Write-Host "Copied both URLs to clipboard." -ForegroundColor Green
} catch {
  Write-Host "Clipboard copy skipped." -ForegroundColor DarkGray
}
