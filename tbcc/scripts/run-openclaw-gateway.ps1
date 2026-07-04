# Foreground OpenClaw gateway for TBCC stack WT tab / supervisor restart.
# Setup once: tbcc\scripts\setup-openclaw-tbcc.ps1
param(
  [string]$TbccRoot = ""
)

$ErrorActionPreference = "Continue"
if (-not $TbccRoot) {
  $TbccRoot = Split-Path $PSScriptRoot -Parent
}

$port = 18789
$control = Join-Path $TbccRoot "scripts\tbcc-service-control.ps1"
if (Test-Path -LiteralPath $control) {
  . $control
  $dotEnv = Read-TbccControlDotEnv -Path (Join-Path $TbccRoot ".env")
  $port = Get-TbccOpenClawGatewayPort -DotEnv $dotEnv
}

$gatewayCmd = Join-Path $env:USERPROFILE ".openclaw\gateway.cmd"
$openclawEntry = Join-Path $env:APPDATA "npm\node_modules\openclaw\dist\index.js"
$hasGateway = (Test-Path -LiteralPath $gatewayCmd) -or (Test-Path -LiteralPath $openclawEntry) -or (Get-Command openclaw -ErrorAction SilentlyContinue)

if (-not $hasGateway) {
  Write-Host "[openclaw] Not installed. Run: npm install -g openclaw@latest && tbcc\scripts\setup-openclaw-tbcc.ps1" -ForegroundColor Red
  exit 1
}

$portUp = $false
if (Get-Command Test-TbccPortListening -ErrorAction SilentlyContinue) {
  $portUp = Test-TbccPortListening -Port $port
}
if ($portUp) {
  Write-Host ("[openclaw] Gateway already listening on port {0} — nothing to start." -f $port) -ForegroundColor Green
  exit 0
}

Write-Host ("[openclaw] Starting gateway on port {0} (TBCC MCP via mcporter when backend :8000 is up)" -f $port) -ForegroundColor Cyan
if (-not (Test-Path -LiteralPath (Join-Path $env:USERPROFILE ".openclaw"))) {
  Write-Host "[openclaw] First run? Execute: tbcc\scripts\setup-openclaw-tbcc.ps1" -ForegroundColor DarkYellow
}

if (Test-Path -LiteralPath $gatewayCmd) {
  & cmd /c "`"$gatewayCmd`""
} elseif (Test-Path -LiteralPath $openclawEntry) {
  $node = (Get-Command node -ErrorAction SilentlyContinue).Source
  if (-not $node) { $node = "node" }
  & $node $openclawEntry gateway --port $port
} else {
  & openclaw gateway --port $port
}

$code = if ($null -ne $LASTEXITCODE) { $LASTEXITCODE } else { 1 }
if ($code -ne 0) {
  Write-Host ("[openclaw] Gateway exited with code {0}." -f $code) -ForegroundColor Red
}
exit $code
