# Stop lean-forbidden processes (forum, album composer, macro search, enrichment).
param([string]$TbccRoot = "")
if (-not $TbccRoot) { $TbccRoot = Split-Path $PSScriptRoot -Parent }
. (Join-Path $PSScriptRoot "tbcc-service-control.ps1")
. (Join-Path $PSScriptRoot "tbcc-process-audit.ps1")

if (-not (Test-TbccLeanProfile -Root $TbccRoot)) {
  Write-Host "TBCC_STACK_PROFILE is not lean - use tray Stop or close tabs manually." -ForegroundColor Yellow
}

$killed = New-Object System.Collections.ArrayList
foreach ($title in @('AOF-Forum', 'TBCC-AlbumComposer', 'TBCC-MacroSearchBot', 'TBCC-NSFW-Detect', 'TBCC-CLIP-Categorize', 'TBCC-Lustpress')) {
  $n = @(Stop-TbccProcessesByServiceTitle -Title $title -TbccRoot $TbccRoot -GracefulTabClose)
  foreach ($p in $n) { [void]$killed.Add($p) }
}
foreach ($row in $script:TbccLeanForbiddenPatterns) {
  $n = @(Stop-TbccProcessesByCommandMatch -Pattern $row.Pattern)
  foreach ($p in $n) { [void]$killed.Add($p) }
}

Start-Sleep -Milliseconds 800
$unique = @($killed | Select-Object -Unique)
Write-Host "Stopped $($unique.Count) lean-extra process trees." -ForegroundColor Green
