# Add TBCC Supervisor to the current user's Windows logon Startup folder.
#   cd tbcc\tools
#   .\register-supervisor-autostart.ps1
#   .\register-supervisor-autostart.ps1 -Unregister

param([switch]$Unregister)

$toolsDir = $PSScriptRoot
$supervisor = Join-Path $toolsDir "tbcc-supervisor.ps1"
$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "TBCC Supervisor.lnk"

if (-not (Test-Path -LiteralPath $supervisor)) {
  Write-Host "Missing: $supervisor" -ForegroundColor Red
  exit 1
}

if ($Unregister) {
  if (Test-Path -LiteralPath $shortcutPath) {
    Remove-Item -LiteralPath $shortcutPath -Force
    Write-Host "Removed: $shortcutPath" -ForegroundColor Green
  } else {
    Write-Host "No shortcut at: $shortcutPath" -ForegroundColor Gray
  }
  exit 0
}

$iconPath = Join-Path (Split-Path $toolsDir -Parent) "extension\icons\favicon.ico"

$wsh = New-Object -ComObject WScript.Shell
$sc = $wsh.CreateShortcut($shortcutPath)
$launcherBat = Join-Path $toolsDir "Launch-TBCC-Supervisor.bat"
if (Test-Path -LiteralPath $launcherBat) {
  $sc.TargetPath = $launcherBat
  $sc.Arguments = ""
} else {
  $sc.TargetPath = "powershell.exe"
  $sc.Arguments = '-NoProfile -Sta -WindowStyle Hidden -ExecutionPolicy Bypass -Command "& { $env:TBCC_SUPERVISOR_TRAY=''1''; & ''' + $supervisor + ''' }"'
}
$sc.WindowStyle = 7
$sc.WorkingDirectory = $toolsDir
$sc.Description = "TBCC tray - cold start and service restarts"
if (Test-Path -LiteralPath $iconPath) {
  $sc.IconLocation = "$iconPath,0"
}
$sc.Save()

Write-Host "Created Startup shortcut:" -ForegroundColor Green
Write-Host "  $shortcutPath" -ForegroundColor Gray
Write-Host "Log off/on or reboot to auto-start. For extension cold launch, also run tbcc-launch-daemon.ps1 (or add it to Startup)." -ForegroundColor Gray
