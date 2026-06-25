# TBCC flywheel tick (ops + growth) — NOT github.com/openclaw/openclaw
$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $tbccRoot "backend"
Set-Location $backend
$py = if ($env:TBCC_PYTHON) { $env:TBCC_PYTHON } else { "py" }
& $py -3.13 scripts/run_tbcc_flywheel_tick.py @args
