# Full stack restart — orchestrator tab stops services then reopens them in the same WT window.
$ErrorActionPreference = "Continue"
$tbccDir = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "tbcc-service-control.ps1")
Invoke-TbccOrchestrateInWt -TbccRoot $tbccDir -Action Restart -NoOpen
