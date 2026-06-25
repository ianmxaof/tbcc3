# TBCC flywheel tick (internal — NOT github.com/openclaw/openclaw)
param([string]$TbccRoot = "")
if (-not $TbccRoot) { $TbccRoot = Split-Path $PSScriptRoot -Parent }
$logDir = Join-Path $TbccRoot ".tbcc-run"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$log = Join-Path $logDir "openclaw-tick.log"
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
& (Join-Path $TbccRoot "scripts\run-tbcc-flywheel-tick.ps1") 2>&1 | ForEach-Object {
  "$ts $_" | Add-Content -LiteralPath $log -Encoding utf8
}
