# Full stack shutdown — opens TBCC-Orchestrator tab in the TBCC Windows Terminal window.
$ErrorActionPreference = "Continue"
$tbccDir = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "tbcc-service-control.ps1")
Invoke-TbccOrchestrateInWt -TbccRoot $tbccDir -Action Stop
