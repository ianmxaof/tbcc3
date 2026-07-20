#Requires -Version 5.1
<#
.SYNOPSIS
  Push Mega+R2 rclone config to the revenue island and smoke-test.
  Reads TBCC_R2_ACCESS_KEY_ID + TBCC_R2_SECRET_ACCESS_KEY from tbcc/.env (never prints values).

.EXAMPLE
  cd tbcc
  .\scripts\revenue-island\wire-r2-rclone.ps1
  .\scripts\revenue-island\wire-r2-rclone.ps1 -StartExport
#>
param(
  [string]$HostName = "root@5.161.53.91",
  [switch]$StartExport,
  [switch]$DryRunExport
)

$ErrorActionPreference = "Stop"
$tbccRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$homeEnv = Join-Path $tbccRoot ".env"

function Read-DotEnvMap([string]$path) {
  $map = @{}
  foreach ($line in Get-Content -LiteralPath $path) {
    $t = $line.Trim()
    if (-not $t -or $t.StartsWith("#")) { continue }
    $i = $t.IndexOf("=")
    if ($i -lt 1) { continue }
    $k = $t.Substring(0, $i).Trim()
    $v = $t.Substring($i + 1).Trim()
    if (($v.StartsWith('"') -and $v.EndsWith('"')) -or ($v.StartsWith("'") -and $v.EndsWith("'"))) {
      $v = $v.Substring(1, $v.Length - 2)
    }
    $map[$k] = $v
  }
  return $map
}

if (-not (Test-Path -LiteralPath $homeEnv)) { throw "Missing $homeEnv" }
$envMap = Read-DotEnvMap $homeEnv

$need = @("TBCC_R2_ACCOUNT_ID", "TBCC_R2_ACCESS_KEY_ID", "TBCC_R2_SECRET_ACCESS_KEY")
$missing = @()
foreach ($k in $need) {
  if ([string]::IsNullOrWhiteSpace($envMap[$k])) { $missing += $k }
}
if ($missing.Count -gt 0) {
  Write-Host "Missing S3 credentials in tbcc/.env:" -ForegroundColor Red
  $missing | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
  Write-Host ""
  Write-Host "Add the Access Key ID + Secret from Cloudflare R2 → API Tokens → TBCC aof-media upload" -ForegroundColor Cyan
  Write-Host "(not the Bearer TBCC_CF_API_TOKEN). Then re-run this script." -ForegroundColor Cyan
  exit 2
}

$bucket = if ($envMap["TBCC_R2_BUCKET"]) { $envMap["TBCC_R2_BUCKET"] } else { "aof-media" }
$endpoint = $envMap["TBCC_R2_S3_ENDPOINT"]
if ([string]::IsNullOrWhiteSpace($endpoint)) {
  $endpoint = "https://$($envMap['TBCC_R2_ACCOUNT_ID']).r2.cloudflarestorage.com"
}

Write-Host "==> Sync migrate scripts to island" -ForegroundColor Cyan
scp -o BatchMode=yes `
  (Join-Path $PSScriptRoot "setup-rclone-r2-from-env.sh") `
  (Join-Path $PSScriptRoot "mega-export-to-r2.sh") `
  "${HostName}:/opt/tbcc/scripts/revenue-island/"

# Export env over SSH without writing secrets into a shell history line longer than needed:
# write a root-only env file on the island, source it, configure rclone, delete file.
$remoteEnv = "/root/.tbcc-r2-rclone.env"
$payload = @(
  "TBCC_R2_ACCOUNT_ID=$($envMap['TBCC_R2_ACCOUNT_ID'])"
  "TBCC_R2_ACCESS_KEY_ID=$($envMap['TBCC_R2_ACCESS_KEY_ID'])"
  "TBCC_R2_SECRET_ACCESS_KEY=$($envMap['TBCC_R2_SECRET_ACCESS_KEY'])"
  "TBCC_R2_BUCKET=$bucket"
  "TBCC_R2_S3_ENDPOINT=$endpoint"
) -join "`n"

$tmp = Join-Path $env:TEMP ("tbcc-r2-rclone-{0}.env" -f [guid]::NewGuid().ToString("n"))
try {
  [System.IO.File]::WriteAllText($tmp, $payload + "`n")
  scp -o BatchMode=yes $tmp "${HostName}:${remoteEnv}"
} finally {
  Remove-Item -Force -ErrorAction SilentlyContinue $tmp
}

Write-Host "==> Configure rclone r2 + smoke" -ForegroundColor Cyan
ssh -o BatchMode=yes $HostName "sed -i 's/\r`$//' /opt/tbcc/scripts/revenue-island/*.sh; chmod 600 $remoteEnv; chmod +x /opt/tbcc/scripts/revenue-island/*.sh; set -a; . $remoteEnv; set +a; rm -f $remoteEnv; bash /opt/tbcc/scripts/revenue-island/setup-rclone-r2-from-env.sh"

if ($DryRunExport) {
  Write-Host "==> Dry-run export" -ForegroundColor Cyan
  ssh -o BatchMode=yes $HostName "bash /opt/tbcc/scripts/revenue-island/mega-export-to-r2.sh --dry-run"
}

if ($StartExport) {
  Write-Host "==> Start background Mega→R2 export" -ForegroundColor Cyan
  ssh -o BatchMode=yes $HostName "bash /opt/tbcc/scripts/revenue-island/mega-export-to-r2.sh"
  ssh -o BatchMode=yes $HostName "bash /opt/tbcc/scripts/revenue-island/mega-export-to-r2.sh --status"
}

Write-Host "Done." -ForegroundColor Green
