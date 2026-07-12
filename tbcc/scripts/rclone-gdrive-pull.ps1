#Requires -Version 5.1
<#
.SYNOPSIS
  One-shot: pull Google Drive (rclone remote) down to a local hard drive.

.DESCRIPTION
  Uses your existing rclone remote (default: gdrive:).
  First run may open a browser if the remote token is expired — sign in as
  ianm.powercore@gmail.com when prompted.

  IMPORTANT: 5 TB will NOT fit on C: (~20 GB free). Point -Dest at a drive
  with enough free space (external HDD / second internal disk).

.EXAMPLE
  # Dry run first (recommended)
  .\rclone-gdrive-pull.ps1 -Dest "E:\GoogleDrive" -DryRun

  # Real pull (copy = never deletes local files)
  .\rclone-gdrive-pull.ps1 -Dest "E:\GoogleDrive"

  # Mirror Drive → local (deletes local files removed from Drive)
  .\rclone-gdrive-pull.ps1 -Dest "E:\GoogleDrive" -Mirror

  # Resume after interrupt (same Dest; rclone is incremental)
  .\rclone-gdrive-pull.ps1 -Dest "E:\GoogleDrive"
#>
[CmdletBinding()]
param(
  # Local folder that will receive the Drive contents
  [Parameter(Mandatory = $true)]
  [string] $Dest,

  # rclone remote name (must already exist — see: rclone listremotes)
  [string] $Remote = "gdrive",

  # Optional path inside Drive, e.g. "Backups" → gdrive:Backups
  [string] $RemotePath = "",

  # Copy (safe) vs Sync/mirror (deletes local extras)
  [switch] $Mirror,

  # Print what would transfer; no writes
  [switch] $DryRun,

  # Skip free-space check (dangerous for 5 TB pulls)
  [switch] $Force,

  # Parallel file transfers (raise on fast LAN/USB3; lower if Drive rate-limits)
  [int] $Transfers = 8,

  # Parallel checkers
  [int] $Checkers = 16
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg) { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "    $msg" -ForegroundColor Yellow }
function Write-Fail([string]$msg) { Write-Host "    $msg" -ForegroundColor Red }

# --- resolve rclone ---
$rcloneCmd = Get-Command rclone -ErrorAction SilentlyContinue
if (-not $rcloneCmd) {
  $wingetRclone = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Filter "rclone.exe" -Recurse -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty FullName
  if ($wingetRclone) {
    $rcloneExe = $wingetRclone
  }
  else {
    throw "rclone not found. Install: winget install Rclone.Rclone"
  }
}
else {
  $rcloneExe = $rcloneCmd.Source
}

Write-Step "rclone"
Write-Ok $rcloneExe
& $rcloneExe version | Select-Object -First 3

# --- remote exists ---
$remoteColon = "${Remote}:"
$remotes = @(& $rcloneExe listremotes 2>$null)
if ($remotes -notcontains $remoteColon) {
  Write-Fail "Remote '$remoteColon' not configured."
  Write-Warn "Create it with:  rclone config"
  Write-Warn "  n) New remote → name: $Remote → storage: Google Drive → use auto config"
  Write-Warn "  Sign in as ianm.powercore@gmail.com when the browser opens."
  exit 2
}
Write-Ok "Remote: $remoteColon"

# --- source / dest ---
$source = if ($RemotePath) { "${Remote}:$($RemotePath.TrimStart('/\'))" } else { $remoteColon }
$Dest = $Dest.TrimEnd('\')
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

$logDir = Join-Path $Dest "_rclone-logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $logDir "gdrive-pull-$stamp.log"

Write-Step "Paths"
Write-Ok "Source: $source"
Write-Ok "Dest:   $Dest"
Write-Ok "Log:    $logFile"

# --- free space check ---
Write-Step "Space check"
try {
  $root = (Resolve-Path $Dest).Path.Substring(0, 2)  # e.g. E:
  $vol = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$root'"
  if ($vol) {
    $freeGB = [math]::Round($vol.FreeSpace / 1GB, 1)
    $sizeGB = [math]::Round($vol.Size / 1GB, 1)
    Write-Ok "$root free ${freeGB} GB / ${sizeGB} GB total"
    if (-not $Force -and $freeGB -lt 100) {
      Write-Fail "Only ${freeGB} GB free on $root — not enough for a multi-TB Drive pull."
      Write-Warn "Plug in / point -Dest at a drive with enough free space, e.g.:"
      Write-Warn "  .\rclone-gdrive-pull.ps1 -Dest `"D:\GoogleDrive`""
      Write-Warn "Or re-run with -Force to skip this guard (not recommended)."
      exit 3
    }
    if (-not $Force -and $freeGB -lt 5200) {
      Write-Warn "Free space (${freeGB} GB) may be less than ~5 TB Drive size."
      Write-Warn "rclone will fail mid-run when the disk fills. Prefer a larger drive."
      Write-Warn "Continue in 8s… (Ctrl+C to abort, or use -Force to silence)"
      Start-Sleep -Seconds 8
    }
  }
}
catch {
  Write-Warn "Could not measure free space: $_"
}

# --- confirm account (best-effort) ---
Write-Step "Remote about (account / size)"
try {
  & $rcloneExe about $source 2>&1 | ForEach-Object { Write-Host "    $_" }
}
catch {
  Write-Warn "about failed (token may need refresh). Continuing — rclone will prompt if needed."
}

# --- transfer ---
$mode = if ($Mirror) { "sync" } else { "copy" }
Write-Step "Starting rclone $mode"
if ($Mirror) {
  Write-Warn "MIRROR mode: files deleted on Drive will be deleted locally under Dest."
}
else {
  Write-Ok "COPY mode: local extras are kept; safe to re-run / resume."
}
if ($DryRun) { Write-Warn "DRY RUN — no files written." }

$args = @(
  $mode,
  $source,
  $Dest,
  "--progress",
  "--transfers", "$Transfers",
  "--checkers", "$Checkers",
  "--drive-chunk-size", "64M",
  "--buffer-size", "32M",
  "--retries", "5",
  "--low-level-retries", "10",
  "--stats", "30s",
  "--stats-one-line",
  "--log-file", $logFile,
  "--log-level", "INFO",
  # Skip Google Docs export noise unless you want them as Office files:
  "--drive-skip-gdocs",
  # Don't create empty dirs for shortcuts / shared-drive quirks:
  "--create-empty-src-dirs"
)

if ($DryRun) { $args += "--dry-run" }

Write-Ok ("Command: rclone " + ($args -join " "))
Write-Host ""

$sw = [System.Diagnostics.Stopwatch]::StartNew()
& $rcloneExe @args
$exit = $LASTEXITCODE
$sw.Stop()

Write-Step "Done"
if ($exit -eq 0) {
  Write-Ok "Exit 0 in $([math]::Round($sw.Elapsed.TotalHours, 2)) h"
  Write-Ok "Log: $logFile"
  exit 0
}
else {
  Write-Fail "rclone exited $exit after $([math]::Round($sw.Elapsed.TotalHours, 2)) h"
  Write-Warn "Re-run the same command to resume (already-copied files are skipped)."
  Write-Warn "Log: $logFile"
  exit $exit
}
