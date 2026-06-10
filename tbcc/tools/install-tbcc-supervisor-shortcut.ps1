# Desktop / Start Menu shortcut for TBCC tray supervisor.
#   cd tbcc\tools
#   .\install-tbcc-supervisor-shortcut.ps1
#   .\install-tbcc-supervisor-shortcut.ps1 -AlsoDesktop

param([switch]$AlsoDesktop)

$ErrorActionPreference = "Stop"
$toolsDir = $PSScriptRoot
$launcherBat = Join-Path $toolsDir "Launch-TBCC-Supervisor.bat"
$supervisorPs1 = Join-Path $toolsDir "tbcc-supervisor.ps1"

if (-not (Test-Path -LiteralPath $supervisorPs1)) {
  Write-Host "Missing: $supervisorPs1" -ForegroundColor Red
  exit 1
}

$iconPath = Join-Path (Split-Path $toolsDir -Parent) "extension\icons\favicon.ico"

function New-TbccSupervisorShortcut {
  param([string]$ShortcutPath)
  $wsh = New-Object -ComObject WScript.Shell
  $sc = $wsh.CreateShortcut($ShortcutPath)
  if (Test-Path -LiteralPath $launcherBat) {
    $sc.TargetPath = $launcherBat
    $sc.Arguments = ""
    $sc.WindowStyle = 7
  } else {
    $sc.TargetPath = "powershell.exe"
    $sc.Arguments = '-NoProfile -Sta -WindowStyle Hidden -ExecutionPolicy Bypass -Command "& { $env:TBCC_SUPERVISOR_TRAY=''1''; & ''' + $supervisorPs1 + ''' }"'
    $sc.WindowStyle = 7
  }
  $sc.WorkingDirectory = $toolsDir
  $sc.Description = "TBCC tray - cold start, restarts, Telegram session tools"
  if (Test-Path -LiteralPath $iconPath) {
    $sc.IconLocation = "$iconPath,0"
  }
  $sc.Save()
  Write-Host "  $ShortcutPath" -ForegroundColor Gray
}

$programs = [Environment]::GetFolderPath("Programs")
$startMenuDir = Join-Path $programs "TBCC"
if (-not (Test-Path -LiteralPath $startMenuDir)) {
  New-Item -ItemType Directory -Path $startMenuDir -Force | Out-Null
}
Write-Host "Creating shortcuts:" -ForegroundColor Cyan
New-TbccSupervisorShortcut -ShortcutPath (Join-Path $startMenuDir "TBCC Supervisor.lnk")

if ($AlsoDesktop) {
  $desktop = [Environment]::GetFolderPath("Desktop")
  New-TbccSupervisorShortcut -ShortcutPath (Join-Path $desktop "TBCC Supervisor.lnk")
}

Write-Host "Done. Double-click TBCC Supervisor (Desktop or Start Menu -> TBCC)." -ForegroundColor Green
Write-Host "Tray icon may be under the ^ overflow in the taskbar notification area." -ForegroundColor Gray
Write-Host "Debug (visible console): double-click Launch-TBCC-Supervisor-Debug.bat in tbcc\tools" -ForegroundColor Gray
Write-Host "Optional logon autostart: .\register-supervisor-autostart.ps1" -ForegroundColor Gray
