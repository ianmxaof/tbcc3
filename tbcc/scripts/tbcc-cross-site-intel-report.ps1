#Requires -Version 5.1
<#
.SYNOPSIS
  Cross-site browse-intel revenue report (Erome / ThisVid / Motherless).

.EXAMPLE
  cd tbcc
  .\scripts\tbcc-cross-site-intel-report.ps1
  .\scripts\tbcc-cross-site-intel-report.ps1 -Days 45 -Top 20
  .\scripts\tbcc-cross-site-intel-report.ps1 -Json
#>
param(
  [int]$Days = 30,
  [int]$Top = 15,
  [switch]$Json,
  [string]$Out = "",
  [switch]$NoWrite,
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Passthrough
)

$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $tbccRoot "backend"
$script = Join-Path $backend "scripts\tbcc_cross_site_intel_report.py"

$argsList = @("--days", "$Days", "--top", "$Top")
if ($Json) { $argsList += "--json" }
if ($Out) { $argsList += @("--out", $Out) }
if ($NoWrite) { $argsList += "--no-write" }
if ($Passthrough) { $argsList += $Passthrough }

Set-Location $backend
& py -3.13 $script @argsList
exit $LASTEXITCODE
