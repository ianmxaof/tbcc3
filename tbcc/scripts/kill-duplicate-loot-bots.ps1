# One-shot: kill all loot_bot workers (fixes 409 / duplicate Roll handlers).
param([string]$TbccRoot = "")
if (-not $TbccRoot) { $TbccRoot = Split-Path $PSScriptRoot -Parent }
. (Join-Path $PSScriptRoot "tbcc-service-control.ps1")

$killed = @(Stop-TbccProcessesByCommandMatch -Pattern 'bots\.loot_bot')
Write-Host ("Stopped {0} loot_bot process(es)." -f $killed.Count) -ForegroundColor $(if ($killed.Count -gt 0) { 'Yellow' } else { 'Green' })
$left = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
  $_.CommandLine -and $_.CommandLine -match 'bots\.loot_bot'
})
if ($left.Count -gt 0) {
  Write-Host ("WARNING: {0} loot_bot still running — close TBCC-LootBot tabs and cold-start." -f $left.Count) -ForegroundColor Red
} else {
  Write-Host "OK — start exactly one TBCC-LootBot tab." -ForegroundColor Green
}
