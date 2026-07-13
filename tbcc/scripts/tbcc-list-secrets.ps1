# List TBCC secrets in .env (names only) and Windows Credential Manager (TBCC/*).
#
# Usage:
#   .\scripts\tbcc-list-secrets.ps1
#   .\scripts\tbcc-list-secrets.ps1 -ShowLengths
#
param([switch]$ShowLengths)

$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path $PSScriptRoot -Parent
$envPath = Join-Path $tbccRoot ".env"

Write-Host "tbcc/.env keys (primary store)" -ForegroundColor Cyan
if (Test-Path -LiteralPath $envPath) {
  foreach ($line in Get-Content -LiteralPath $envPath -Encoding UTF8) {
    if ($line -match '^\s*(TBCC_[A-Z0-9_]+|BUFFER_[A-Z0-9_]+|OPENROUTER_[A-Z0-9_]+|REPLICATE_[A-Z0-9_]+|API_ID|API_HASH)\s*=\s*(.*)$') {
      $k = $Matches[1]
      $v = $Matches[2]
      if ($ShowLengths) {
        Write-Host ("  {0,-40} {1} chars" -f $k, $v.Length)
      } else {
        Write-Host ("  {0}" -f $k)
      }
    }
  }
} else {
  Write-Host "  (missing .env)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Windows Credential Manager (TBCC/* backup)" -ForegroundColor Cyan
$out = & cmdkey /list 2>$null | Out-String
$targets = [regex]::Matches($out, "Target:\s*(TBCC/\S+)") | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
if ($targets.Count) {
  foreach ($t in $targets) { Write-Host "  $t" }
} else {
  Write-Host "  (none - capture-secret backs up here after save)" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "GCP Secret Manager is separate (cloud). Local capture writes .env + cmdkey only." -ForegroundColor DarkYellow
Write-Host "Capture: right-click desktop -> TBCC: Save clipboard API key to .env" -ForegroundColor Gray
Write-Host "Or:      .\scripts\tbcc-capture-secret.ps1 -FromClipboard" -ForegroundColor Gray
