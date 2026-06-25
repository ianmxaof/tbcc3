# Cursor ops automation tick (local runner — mirrors CURSOR_OPS_AUTOMATION.md)
$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $tbccRoot "backend"
Set-Location $backend
$py = if ($env:TBCC_PYTHON) { $env:TBCC_PYTHON } else { "py" }
& $py -3.13 scripts/run_cursor_ops_automation_tick.py @args
