#Requires -Version 5.1
<#
.SYNOPSIS
  OpenRouter Dolphin lab — list models, run probes, or open interactive REPL.

.DESCRIPTION
  Dolphin on OpenRouter is paid but cheap (~fractions of a cent per probe).
  The old cognitivecomputations/dolphin-mistral-24b-venice-edition:free slug 404s.

.EXAMPLE
  cd tbcc
  .\scripts\tbcc-dolphin-lab.ps1                 # list + probe (default)
  .\scripts\tbcc-dolphin-lab.ps1 -List
  .\scripts\tbcc-dolphin-lab.ps1 -Probe -CompareFree
  .\scripts\tbcc-dolphin-lab.ps1 -Repl
  .\scripts\tbcc-dolphin-lab.ps1 -CompanionEnv   # print env block for spicy bot test
#>
param(
  [switch]$List,
  [switch]$Probe,
  [switch]$Repl,
  [switch]$CompareFree,
  [switch]$CompanionEnv,
  [string]$Model = "",
  [switch]$Json
)

$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $tbccRoot "backend"
$script = Join-Path $backend "scripts\tbcc_openrouter_dolphin_lab.py"
$dolphinModel = "cognitivecomputations/dolphin-mistral-24b-venice-edition"

if ($CompanionEnv) {
  Write-Host @"
# Paste into tbcc/.env (or set for this PowerShell session) to test @aof_spicybot_bot on Dolphin:
TBCC_LLM_CHAT_PROVIDER=openrouter
TBCC_LLM_CHAT_OPENROUTER_MODEL=$dolphinModel
TBCC_OPENROUTER_MODEL=$dolphinModel
# Restart companion from tray Services, or locally:
#   cd tbcc\backend && py -3.13 -m bots.companion_bot
"@
  exit 0
}

$argsList = @()
if ($List) { $argsList += "--list" }
elseif ($Probe) { $argsList += "--probe" }
elseif ($Repl) { $argsList += "--repl" }
if ($Model) { $argsList += @("-m", $Model) }
if ($CompareFree) { $argsList += "--compare-free" }
if ($Json) { $argsList += "--json" }

Set-Location $backend
& py -3.13 $script @argsList
exit $LASTEXITCODE
