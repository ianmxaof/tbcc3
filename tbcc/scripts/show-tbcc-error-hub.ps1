# TBCC Error Hub monitor — tail the unified log (first tab when using .\start.ps1 -WtTabs).
param(
  [Parameter(Mandatory = $true)][string]$TbccRoot
)

$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "tbcc-error-hub.ps1")
Initialize-TbccServiceConsole -TbccRoot $TbccRoot -Title "TBCC-Errors"

$paths = Get-TbccErrorHubPaths -TbccRoot $TbccRoot
if (-not (Test-Path -LiteralPath $paths.LogPath)) {
  Initialize-TbccErrorHub -TbccRoot $TbccRoot | Out-Null
}

function Write-TbccHubBanner {
  Clear-Host
  Write-Host ""
  Write-Host "  TBCC Error Hub" -ForegroundColor Magenta
  Write-Host "  Unified log for all service tabs (errors + warnings)." -ForegroundColor Gray
  Write-Host ("  File: " + $paths.LogPath) -ForegroundColor DarkGray
  Write-Host '  Long messages are truncated with .... - open the service tab for full output.' -ForegroundColor DarkGray
  Write-Host "  Press Ctrl+C to stop monitoring (services keep running in other tabs)." -ForegroundColor DarkGray
  Write-Host ""
}

function Write-TbccHubFormattedLine {
  param([string]$Line)
  if (-not $Line) { return }
  if ($Line.StartsWith("====")) {
    Write-Host $Line -ForegroundColor DarkCyan
    return
  }
  if ($Line -match '\] \[ERROR\]') {
    Write-Host $Line -ForegroundColor Red
    return
  }
  if ($Line -match '\] \[WARN\]') {
    Write-Host $Line -ForegroundColor Yellow
    return
  }
  Write-Host $Line -ForegroundColor Gray
}

Write-TbccHubBanner

if (Test-Path -LiteralPath $paths.LogPath) {
  $tail = Get-Content -LiteralPath $paths.LogPath -Tail 40 -ErrorAction SilentlyContinue
  if ($tail) {
    Write-Host "  --- recent entries ---" -ForegroundColor DarkGray
    foreach ($ln in $tail) {
      Write-TbccHubFormattedLine -Line $ln
    }
    Write-Host "  --- live tail ---" -ForegroundColor DarkGray
    Write-Host ""
  }
}

try {
  Get-Content -LiteralPath $paths.LogPath -Wait -Tail 0 -Encoding UTF8 | ForEach-Object {
    Write-TbccHubFormattedLine -Line $_
  }
} catch {
  Write-Host $_ -ForegroundColor Red
}
