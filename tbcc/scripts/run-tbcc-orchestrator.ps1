# TBCC stack orchestrator tab - stop / restart / cold-start inside Windows Terminal.
param(
  [Parameter(Mandatory = $true)][string]$TbccRoot,
  [Parameter(Mandatory = $true)][ValidateSet("Stop", "Restart", "ColdStart")][string]$Action,
  [switch]$NoOpen
)

$ErrorActionPreference = "Continue"
trap {
  Write-Host ""
  Write-Host ("FATAL: " + $_.Exception.Message) -ForegroundColor Red
  if ($_.ScriptStackTrace) { Write-Host $_.ScriptStackTrace -ForegroundColor DarkGray }
  Write-Host "Press Enter to close this tab..." -ForegroundColor DarkGray
  try { [void][System.Console]::ReadLine() } catch {}
  exit 1
}

. (Join-Path $PSScriptRoot "tbcc-error-hub.ps1")
Initialize-TbccServiceConsole -TbccRoot $TbccRoot -Title "TBCC-Orchestrator"

$core = Join-Path $PSScriptRoot "tbcc-orchestrate.ps1"
if (-not (Test-Path -LiteralPath $core)) {
  Write-Host "Missing tbcc-orchestrate.ps1" -ForegroundColor Red
  Write-Host "Press Enter to close this tab..." -ForegroundColor DarkGray
  try { [void][System.Console]::ReadLine() } catch {}
  exit 1
}

& $core -TbccRoot $TbccRoot -Action $Action -NoOpen:$NoOpen
exit $LASTEXITCODE
