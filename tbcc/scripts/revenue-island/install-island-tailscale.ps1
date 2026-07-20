# Install Tailscale on the revenue island and join the tailnet (CLI).
# Needs a one-time reusable/ephemeral auth key from:
#   https://login.tailscale.com/admin/settings/keys
#
#   .\scripts\revenue-island\install-island-tailscale.ps1 -HostName root@5.161.53.91 -AuthKey "tskey-auth-..."
# Or set TBCC_TAILSCALE_AUTHKEY in tbcc/.env (not committed) and omit -AuthKey.

param(
  [Parameter(Mandatory = $true)][string]$HostName,
  [string]$AuthKey = "",
  [string]$Hostname = "tbcc-revenue-island"
)

$ErrorActionPreference = "Stop"
$tbccRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$envPath = Join-Path $tbccRoot ".env"

if (-not $AuthKey) {
  if (Test-Path -LiteralPath $envPath) {
    foreach ($line in Get-Content -LiteralPath $envPath) {
      if ($line -match '^\s*TBCC_TAILSCALE_AUTHKEY\s*=\s*(.+)\s*$') {
        $AuthKey = $Matches[1].Trim().Trim('"').Trim("'")
        break
      }
    }
  }
}
if (-not $AuthKey) {
  throw "Pass -AuthKey tskey-auth-... or set TBCC_TAILSCALE_AUTHKEY in tbcc/.env (create key at https://login.tailscale.com/admin/settings/keys )."
}
if ($AuthKey -notmatch '^tskey-') {
  throw "AuthKey should look like tskey-auth-... or tskey-client-..."
}

Write-Host "Installing Tailscale on $HostName ..." -ForegroundColor Cyan

# Install + up in one remote script; key only via env on remote for the session
$remote = @"
set -euo pipefail
if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
systemctl enable --now tailscaled
# Prefer SSH + MagicDNS hostname for dashboard over public :8000
tailscale up --auth-key='$AuthKey' --ssh --hostname='$Hostname' --accept-dns=true
tailscale status
echo TAILSCALE_IPV4=`$(tailscale ip -4)
"@

# Avoid dumping key in local process list more than needed: pass via ssh stdin script
$remoteFile = "/tmp/tbcc-island-tailscale-setup.sh"
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remote))
& ssh $HostName "echo $b64 | base64 -d > $remoteFile; chmod 700 $remoteFile; bash $remoteFile; rm -f $remoteFile"

Write-Host ""
Write-Host "Done. From home (Tailscale connected):" -ForegroundColor Green
Write-Host "  curl http://$Hostname`:8000/health" -ForegroundColor DarkGray
Write-Host "  # or MagicDNS / 100.x IP from: tailscale status" -ForegroundColor DarkGray
Write-Host "Dashboard: set API to that host, or keep using dashboard-tunnel.ps1" -ForegroundColor DarkGray
Write-Host "Do NOT paste auth keys into chat." -ForegroundColor Yellow
