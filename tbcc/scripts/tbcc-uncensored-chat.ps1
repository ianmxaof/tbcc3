#Requires -Version 5.1
<#
.SYNOPSIS
  Free-only OpenRouter chat CLI (Dolphin/Hermes :free). Featherless is paid — not default.

.EXAMPLE
  cd tbcc
  .\scripts\tbcc-uncensored-chat.ps1
  .\scripts\tbcc-uncensored-chat.ps1 -ListFree
  .\scripts\tbcc-uncensored-chat.ps1 -Model nousresearch/hermes-3-llama-3.1-405b:free
  .\scripts\tbcc-dolphin-lab.ps1 -Probe    # paid Dolphin (cheap)
  .\scripts\tbcc-uncensored-chat.ps1 -Verify
#>
param(
  [ValidateSet("openrouter", "featherless", "venice", "openai", "custom")]
  [string]$Provider = "",
  [string]$Model = "",
  [string]$Once = "",
  [switch]$Verify,
  [switch]$ListFree,
  [switch]$AllowPaid,
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Passthrough
)

$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $tbccRoot "backend"
$script = Join-Path $backend "scripts\tbcc_uncensored_chat.py"

$argsList = @()
if ($Provider) { $argsList += @("-p", $Provider) }
if ($Model) { $argsList += @("-m", $Model) }
if ($Once) { $argsList += @("--once", $Once) }
if ($Verify) { $argsList += "--verify" }
if ($ListFree) { $argsList += "--list-free" }
if ($AllowPaid) { $argsList += "--allow-paid" }
if ($Passthrough) { $argsList += $Passthrough }

Set-Location $backend
& py -3.13 $script @argsList
exit $LASTEXITCODE
