# Provision Hetzner Cloud CX22-class server for TBCC revenue island (CLI only after you have an API token).
# Does NOT start Telegram bots. Does NOT touch the GCP scrape micro.
#
# Browser only if needed (account + API token once):
#   https://accounts.hetzner.com/login
#   https://console.hetzner.cloud/  → project → Security → API Tokens → Generate
#
# Prereqs on this PC:
#   winget install HetznerCloud.cli   # or: https://github.com/hetznercloud/cli/releases
#   hcloud context create tbcc        # paste API token once
#
# Usage (from tbcc/):
#   .\scripts\revenue-island\create-hetzner-island.ps1
#   .\scripts\revenue-island\create-hetzner-island.ps1 -Location ash -SshKeyName laptop -WhatIf
# Optional Tailscale ephemeral key (from https://login.tailscale.com/admin/settings/keys ):
#   .\scripts\revenue-island\create-hetzner-island.ps1 -TailscaleAuthKey "tskey-auth-..."

param(
  [string]$Name = "tbcc-revenue-island",
  # Ashburn/Hillsboro: cpx21 (4GB). EU fsn1/nbg1/hel1: cx23 or cpx22 also fine.
  [string]$Type = "cpx21",
  [string]$Image = "ubuntu-24.04",
  [string]$Location = "ash",
  [string]$SshKeyName = "",
  [string]$TailscaleAuthKey = "",
  [string]$UserDataFile = "",
  [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$defaultUd = Join-Path $here "cloud-init-island.yaml"

function Assert-Hcloud {
  if (-not (Get-Command hcloud -ErrorAction SilentlyContinue)) {
    throw @"
hcloud CLI not found. Install then create a context with your API token:
  winget install HetznerCloud.cli
  hcloud context create tbcc
Token: Hetzner Console → Security → API Tokens
https://console.hetzner.cloud/
"@
  }
}

Assert-Hcloud

if (-not $SshKeyName) {
  $names = @(hcloud ssh-key list -o columns=name -o noheader 2>$null | ForEach-Object { ($_ -as [string]).Trim() } | Where-Object { $_ })
  if (-not $names -or $names.Count -eq 0) {
    Write-Host "No SSH keys in this hcloud context. Upload one:" -ForegroundColor Yellow
    Write-Host '  hcloud ssh-key create --name laptop --public-key-from-file $env:USERPROFILE\.ssh\id_ed25519.pub' -ForegroundColor DarkGray
    throw "Pass -SshKeyName after uploading a key."
  }
  $SshKeyName = $names[0]
  Write-Host "Using SSH key: $SshKeyName" -ForegroundColor DarkCyan
}

$udPath = if ($UserDataFile) { $UserDataFile } else { $defaultUd }
if (-not (Test-Path -LiteralPath $udPath)) {
  throw "Missing user-data: $udPath"
}

$tempUd = $null
if ($TailscaleAuthKey) {
  $tempUd = Join-Path $env:TEMP ("tbcc-island-cloud-init-{0}.yaml" -f [guid]::NewGuid().ToString("n"))
  $base = Get-Content -LiteralPath $udPath -Raw
  $keyEsc = $TailscaleAuthKey.Trim() -replace '\\', '\\\\'
  $inject = @"

  - path: /etc/tbcc-tailscale-authkey
    content: |
      $keyEsc
    owner: root:root
    permissions: "0600"
"@
  if ($base -notmatch '(?m)^write_files:') {
    throw "cloud-init missing write_files: block"
  }
  $patched = $base -replace '(?m)^(write_files:\r?\n)', ('$1' + $inject + "`n")
  Set-Content -LiteralPath $tempUd -Value $patched -NoNewline -Encoding utf8
  $udPath = $tempUd
  Write-Host "Injected Tailscale auth key into cloud-init (temp file)." -ForegroundColor DarkCyan
}

$createArgs = @(
  "server", "create",
  "--name", $Name,
  "--type", $Type,
  "--image", $Image,
  "--location", $Location,
  "--ssh-key", $SshKeyName,
  "--user-data-from-file", $udPath
)

Write-Host ("hcloud " + ($createArgs -join " ")) -ForegroundColor DarkGray
if ($WhatIf) {
  Write-Host "WhatIf: not creating." -ForegroundColor Yellow
  if ($tempUd) { Remove-Item -LiteralPath $tempUd -Force -ErrorAction SilentlyContinue }
  exit 0
}

& hcloud @createArgs
if ($LASTEXITCODE -ne 0) {
  if ($tempUd) { Remove-Item -LiteralPath $tempUd -Force -ErrorAction SilentlyContinue }
  throw "hcloud server create failed (exit $LASTEXITCODE)"
}

if ($tempUd) { Remove-Item -LiteralPath $tempUd -Force -ErrorAction SilentlyContinue }

$ip = (hcloud server ip $Name 2>$null)
Write-Host ""
Write-Host "Server created: $Name" -ForegroundColor Green
if ($ip) { Write-Host "IPv4: $ip" -ForegroundColor Green }
Write-Host "Wait ~60–90s for cloud-init (Docker). Then:" -ForegroundColor Cyan
Write-Host "  .\scripts\revenue-island\sync-island-files.ps1 -HostName root@$ip" -ForegroundColor DarkGray
Write-Host "  ssh root@$ip 'bash /opt/tbcc/scripts/revenue-island/bootstrap-island.sh'" -ForegroundColor DarkGray
Write-Host "GCP scrape micro: unchanged — leave it alone." -ForegroundColor DarkGray
Write-Host "Do NOT start bots until home payment/loot are stopped (see REVENUE_ISLAND.md)." -ForegroundColor Yellow
