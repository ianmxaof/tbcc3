# Cold start — orchestrator tab in Windows Terminal (no separate launcher window).
param([switch]$NoOpen)

$ErrorActionPreference = "Continue"
$tbccDir = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "tbcc-service-control.ps1")
Invoke-TbccOrchestrateInWt -TbccRoot $tbccDir -Action ColdStart -NoOpen:$NoOpen
