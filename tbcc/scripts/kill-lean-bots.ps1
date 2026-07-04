# One-shot: kill lean-forbidden bot workers (macro search) and their WT/cmd tab shells.
param([string]$TbccRoot = "")
if (-not $TbccRoot) { $TbccRoot = Split-Path $PSScriptRoot -Parent }
. (Join-Path $PSScriptRoot "tbcc-service-control.ps1")

$k1 = @(Stop-TbccProcessesByCommandMatch -Pattern 'bots\.macro_search_bot')
$k2 = @(Stop-TbccProcessesByCommandMatch -Pattern 'title\s+"TBCC-MacroSearchBot"')
$k3 = @(Stop-TbccProcessesByCommandMatch -Pattern 'run-tbcc-service\.ps1.*MacroSearchBot')

Start-Sleep -Milliseconds 800
$left = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and $_.CommandLine -match [regex]::Escape($TbccRoot) -and
    $_.CommandLine -match 'bots\.macro_search_bot'
  })
Write-Host ("Stopped macro={0} shells={1} wrappers={2}; {3} worker(s) still up." -f `
    $k1.Count, $k2.Count, $k3.Count, $left.Count)
if ($left.Count -gt 0) {
  Write-Host "Close TBCC-MacroSearchBot tabs manually, then cold start." -ForegroundColor Yellow
}
