# TBCC everyday Playwright recorder — Record/Stop panel, saves a .py workflow.
# Usage (from anywhere):
#   powershell -NoProfile -ExecutionPolicy Bypass -File tbcc\scripts\tbcc-playwright-record.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File tbcc\scripts\tbcc-playwright-record.ps1 -Url https://www.erome.com/ -Name erome-private
#   powershell -NoProfile -ExecutionPolicy Bypass -File tbcc\scripts\tbcc-playwright-record.ps1 -Url https://www.erome.com/ -LoadAuth .erome-auth.json

param(
  [string]$Url = "about:blank",
  [string]$Name = "",
  [string]$LoadAuth = "",
  [string]$SaveAuth = "",
  [switch]$Chromium
)

$ErrorActionPreference = "Stop"
$backend = Join-Path $PSScriptRoot "..\backend" | Resolve-Path
$script = Join-Path $backend "scripts\playwright_record.py"

$argsList = @($script)
if ($Url) { $argsList += $Url }
if ($Name) { $argsList += @("--name", $Name) }
if ($LoadAuth) {
  $authPath = if ([System.IO.Path]::IsPathRooted($LoadAuth)) { $LoadAuth } else { Join-Path $backend $LoadAuth }
  $argsList += @("--load-auth", $authPath)
}
if ($SaveAuth) {
  $savePath = if ([System.IO.Path]::IsPathRooted($SaveAuth)) { $SaveAuth } else { Join-Path $backend $SaveAuth }
  $argsList += @("--save-auth", $savePath)
}
if ($Chromium) { $argsList += "--chromium" }

Set-Location $backend
& py -3.13 @argsList
exit $LASTEXITCODE
