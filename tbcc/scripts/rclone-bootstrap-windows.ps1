#Requires -Version 5.1
<#
.SYNOPSIS
  Mount Mega, Google Drive, and Dropbox via rclone on Windows (WinFsp required).

.EXAMPLE
  Set-ExecutionPolicy -Scope Process Bypass
  cd C:\Powercore-repo-main\telegram_bot2\tbcc\scripts
  .\rclone-bootstrap-windows.ps1 -Remotes mega,gdrive,dropbox
  # (comma without quotes is OK — PowerShell passes three strings)
#>
[CmdletBinding()]
param(
  [string] $MountRoot = "C:\CloudMounts",
  [switch] $Install,
  [switch] $SkipMount,
  [string[]] $Remotes = @("mega", "gdrive", "dropbox")
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg) { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "    $msg" -ForegroundColor Yellow }

$CacheDir = Join-Path $env:LOCALAPPDATA "rclone-vfs-cache"
$VfsCacheMode = "writes"

Write-Step "Prerequisites"
Write-Ok "rclone: Intel/AMD 64-bit Windows build"
Write-Ok "WinFsp: winget install WinFsp.WinFsp (you installed this)"

if ($Install) {
  Write-Step "Installing via winget"
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    & winget install --id Rclone.Rclone -e --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
    & winget install --id WinFsp.WinFsp -e --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
  }
  else {
    Write-Warn "winget not found"
  }
}

$rclone = Get-Command rclone -ErrorAction SilentlyContinue
if (-not $rclone) {
  $fallback = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\rclone.exe"
  if (Test-Path $fallback) { $rclone = Get-Command $fallback }
}
if (-not $rclone) {
  throw "rclone not on PATH. Reopen PowerShell after install."
}

Write-Step "rclone version"
& rclone version

$winfsp = (Test-Path (Join-Path ${env:ProgramFiles} "WinFsp")) -or (Test-Path (Join-Path ${env:ProgramFiles(x86)} "WinFsp"))
if (-not $winfsp) {
  Write-Warn "WinFsp not detected - rclone mount will fail"
}

New-Item -ItemType Directory -Force -Path $MountRoot | Out-Null
New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
$LogDir = Join-Path $MountRoot "_logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-Step "Configured remotes"
$configList = @( & rclone listremotes )
if (-not $configList -or $configList.Count -eq 0) {
  Write-Warn "No remotes - run: rclone config"
  if (-not $SkipMount) { exit 2 }
}
else {
  $configList | ForEach-Object { Write-Ok $_ }
}

$remoteNames = @(
  $Remotes | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ }
)
$missing = @()
foreach ($name in $remoteNames) {
  $needle = "${name}:"
  if ($configList -notcontains $needle) { $missing += $name }
}
if ($missing.Count -gt 0) {
  Write-Warn "Not configured (skipped): $($missing -join ', ')"
}

if ($SkipMount) {
  Write-Ok "SkipMount - done."
  exit 0
}

Write-Step "Starting mounts under $MountRoot"
Write-Warn "Keep TBCC_WATCH_INBOX on local disk (C:\tbcc\inbox), not on mounts."
Write-Warn "Each mount runs minimized; close that window to unmount."

$rcloneExe = $rclone.Source
foreach ($name in $remoteNames) {
  $remote = "${name}:"
  if ($configList -notcontains $remote) { continue }

  $mountPath = Join-Path $MountRoot $name
  New-Item -ItemType Directory -Force -Path $mountPath | Out-Null
  $logFile = Join-Path $LogDir "$name-mount.log"

  $mountArgs = @(
    "mount", $remote, $mountPath,
    "--vfs-cache-mode", $VfsCacheMode,
    "--cache-dir", $CacheDir,
    "--dir-cache-time", "72h",
    "--poll-interval", "15s",
    "--transfers", "4",
    "--buffer-size", "32M",
    "--volname", "rclone-$name",
    "--log-file", $logFile,
    "--log-level", "INFO"
  )

  Write-Ok "$remote -> $mountPath (log: $logFile)"
  Start-Process -FilePath $rcloneExe -ArgumentList $mountArgs -WindowStyle Minimized
  Start-Sleep -Seconds 2
}

Write-Step "Open in File Explorer"
Get-ChildItem $MountRoot -Directory | Where-Object { $_.Name -ne "_logs" } | ForEach-Object { Write-Ok $_.FullName }

Write-Step "TBCC .env suggestion"
Write-Ok "TBCC_WATCH_INBOX=C:\tbcc\inbox"
Write-Ok "TBCC_WATCH_LIBRARY=C:\tbcc\library"

Write-Host ""
Write-Host "Done." -ForegroundColor Green
