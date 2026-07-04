# Emergency stop — WT tab storm / duplicate run-tbcc-service tabs after failed close-tab.
# Run from repo:  tbcc\scripts\stop-wt-tab-storm.ps1
$ErrorActionPreference = "Continue"
$TbccRoot = Split-Path $PSScriptRoot -Parent
. (Join-Path $PSScriptRoot "tbcc-service-control.ps1")

Write-Host "TBCC tab storm cleanup..." -ForegroundColor Yellow

# Disable close-tab side effects for this session
$env:TBCC_WT_CLOSE_TAB = "0"

$tabDir = Join-Path $TbccRoot ".tbcc-run\tabs"
if (Test-Path -LiteralPath $tabDir) {
  Remove-Item -LiteralPath (Join-Path $tabDir "*") -Force -ErrorAction SilentlyContinue
  Write-Host "  Cleared stale .tbcc-run\tabs\*.wt-session" -ForegroundColor DarkGray
}

$k1 = @(Stop-TbccProcessesByCommandMatch -Pattern 'run-tbcc-service\.ps1')
$k2 = @(Stop-TbccProcessesByCommandMatch -Pattern 'wt\.exe.*new-tab.*TBCC-')
$k3 = @(Stop-TbccProcessesByCommandMatch -Pattern 'close-tab\s+--target')
Write-Host ("  Stopped run-tbcc-service wrappers: {0}" -f $k1.Count) -ForegroundColor DarkGray
Write-Host ("  Stopped stray wt new-tab launchers: {0}" -f $k2.Count) -ForegroundColor DarkGray
Write-Host ("  Stopped close-tab error shells: {0}" -f $k3.Count) -ForegroundColor DarkGray

Write-Host "Done. Remaining close-tab titled tabs should be gone; if not, close that WT window once." -ForegroundColor Green
Write-Host "Then cold start once:  cd tbcc && .\start.ps1 -WtTabs -Full" -ForegroundColor Cyan
Write-Host "Tabs now auto-close when each service exits (TBCC_WT_CLOSE_TAB defaults off)." -ForegroundColor DarkGray
