# Exit 0 only if home tray Status reports payment + loot not running.
# Use before starting island bots (no dual tokens).
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\revenue-island\assert-home-bots-down.ps1

$ErrorActionPreference = "Stop"
$tbccRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$cli = Join-Path $tbccRoot "scripts\tbcc-stack-cli.ps1"
if (-not (Test-Path -LiteralPath $cli)) {
  throw "Missing $cli"
}

$json = & powershell -NoProfile -ExecutionPolicy Bypass -File $cli -Action Status | Out-String
$obj = $json | ConvertFrom-Json
$pay = @($obj.services | Where-Object { $_.id -eq "payment" } | Select-Object -First 1)
$loot = @($obj.services | Where-Object { $_.id -eq "loot" } | Select-Object -First 1)

$bad = @()
if ($pay -and $pay.running) { $bad += "payment" }
if ($loot -and $loot.running) { $bad += "loot" }

if ($bad.Count -gt 0) {
  Write-Host ("REFUSE: home still running: {0}. Stop tray Services first." -f ($bad -join ", ")) -ForegroundColor Red
  exit 2
}

Write-Host "OK: home payment + loot not running." -ForegroundColor Green
exit 0
