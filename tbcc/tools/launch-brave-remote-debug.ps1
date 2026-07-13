# Launch Brave with remote debugging for userscript / MCP inspection.
# Remote debugging is per browser PROCESS, not per tab — enable once at launch.
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\tbcc\tools\launch-brave-remote-debug.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\tbcc\tools\launch-brave-remote-debug.ps1 -Url "https://fetlife.com/settings/activity_feed"
#
# Then point chrome-devtools MCP at:
#   --browser-url=http://127.0.0.1:9222
# (or keep --autoConnect if it attaches to this instance)

[CmdletBinding()]
param(
    [int] $Port = 9222,
    [string] $Url = "https://fetlife.com/settings/activity_feed",
    [string] $UserDataDir = "",
    [switch] $UseDefaultProfile
)

$ErrorActionPreference = "Stop"

$braveCandidates = @(
    "$env:PROGRAMFILES\BraveSoftware\Brave-Browser\Application\brave.exe",
    "${env:PROGRAMFILES(X86)}\BraveSoftware\Brave-Browser\Application\brave.exe",
    "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\Application\brave.exe"
)
$brave = $braveCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $brave) {
    throw "Brave not found. Install Brave or edit braveCandidates in this script."
}

# Separate profile avoids locking your everyday Brave window and is what Chromium expects for --remote-debugging-port.
if (-not $UserDataDir) {
    $UserDataDir = Join-Path $env:TEMP "brave-remote-debug-profile"
}
New-Item -ItemType Directory -Force -Path $UserDataDir | Out-Null

# Probe if something already answers on the port
try {
    $existing = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/json/version" -UseBasicParsing -TimeoutSec 1
    Write-Host "Remote debugging already live on port $Port"
    Write-Host $existing.Content
    if ($Url) {
        Start-Process $brave $Url
    }
    exit 0
} catch {
    # nothing listening — launch below
}

$args = @(
    "--remote-debugging-port=$Port",
    "--remote-allow-origins=*",
    "--no-first-run",
    "--no-default-browser-check"
)

if (-not $UseDefaultProfile) {
    $args += "--user-data-dir=$UserDataDir"
} else {
    Write-Warning "Using default profile. Close all Brave windows first or the debug port may fail to bind."
}

if ($Url) {
    $args += $Url
}

Write-Host "Starting Brave with remote debugging..."
Write-Host "  exe:  $brave"
Write-Host "  port: $Port"
Write-Host "  data: $(if ($UseDefaultProfile) { '(default profile)' } else { $UserDataDir })"
Write-Host "  mcp:  --browser-url=http://127.0.0.1:$Port"

Start-Process -FilePath $brave -ArgumentList $args

Start-Sleep -Seconds 2
try {
    $ver = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/json/version" -UseBasicParsing -TimeoutSec 3
    Write-Host "OK — debugger ready:"
    Write-Host $ver.Content
} catch {
    Write-Warning "Brave started but port $Port is not answering yet. Wait a second and open http://127.0.0.1:$Port/json/list"
}
