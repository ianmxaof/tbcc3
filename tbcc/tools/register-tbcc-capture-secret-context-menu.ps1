# Register Explorer / Desktop right-click: TBCC capture API key from clipboard.
#
#   cd tbcc\tools
#   .\register-tbcc-capture-secret-context-menu.ps1
#   .\register-tbcc-capture-secret-context-menu.ps1 -Unregister
#
# Note: Do NOT register both DesktopBackground and Directory\Background — Windows 11
# desktop right-click shows both handlers and you get duplicate menu items.

param([switch]$Unregister)

$toolsDir = $PSScriptRoot
$launcherVbs = Join-Path $toolsDir "tbcc-capture-secret-context-menu.vbs"
$launcherBat = Join-Path $toolsDir "tbcc-capture-secret-context-menu.bat"
$iconPath = Join-Path (Split-Path $toolsDir -Parent) "extension\icons\favicon.ico"
$menuTitle = "TBCC: Save clipboard API key to .env"
# wscript = no console flash (cmd.exe /c bat always flashes a window)
$command = "wscript.exe `"$launcherVbs`""

if (-not (Test-Path -LiteralPath $launcherVbs)) {
  Write-Host "Missing: $launcherVbs" -ForegroundColor Red
  exit 1
}
if (-not (Test-Path -LiteralPath $launcherBat)) {
  Write-Host "Missing bat fallback: $launcherBat" -ForegroundColor Yellow
}

function Remove-ShellKey {
  param([string]$KeyPath)
  if (Test-Path -LiteralPath $KeyPath) {
    Remove-Item -LiteralPath $KeyPath -Recurse -Force
  }
}

function Set-ShellKey {
  param(
    [string]$KeyPath,
    [string]$Title,
    [string]$Command
  )
  New-Item -Path $KeyPath -Force | Out-Null
  Set-ItemProperty -LiteralPath $KeyPath -Name "(Default)" -Value $Title
  if (Test-Path -LiteralPath $iconPath) {
    Set-ItemProperty -LiteralPath $KeyPath -Name "Icon" -Value $iconPath
  }
  $commandKey = Join-Path $KeyPath "command"
  New-Item -Path $commandKey -Force | Out-Null
  Set-ItemProperty -LiteralPath $commandKey -Name "(Default)" -Value $Command
}

$menuKeyName = "TBCCCaptureSecret"
# Desktop wallpaper only — Directory\Background also appears on Win11 desktop (duplicates).
$targets = @(
  "HKCU:\Software\Classes\DesktopBackground\shell\$menuKeyName"
)

$legacyTargets = @(
  "HKCU:\Software\Classes\Directory\shell\$menuKeyName",
  "HKCU:\Software\Classes\Directory\Background\shell\$menuKeyName"
)

if ($Unregister) {
  foreach ($key in ($targets + $legacyTargets)) {
    Remove-ShellKey $key
  }
  Write-Host "Removed TBCC capture-secret context menus." -ForegroundColor Green
  exit 0
}

foreach ($key in $legacyTargets) {
  Remove-ShellKey $key
}

foreach ($key in $targets) {
  Set-ShellKey -KeyPath $key -Title $menuTitle -Command $command
  Write-Host "Registered: $key" -ForegroundColor Gray
}

Write-Host ""
Write-Host "TBCC capture-secret context menu registered (desktop wallpaper)." -ForegroundColor Green
Write-Host "  Right-click desktop wallpaper -> '$menuTitle'" -ForegroundColor Gray
Write-Host "Runs hidden. Unknown keys open a small picker (no Terminal window)." -ForegroundColor Gray
Write-Host "Uses same API as browser when TBCC backend is on :8000; else local .env write." -ForegroundColor Gray
Write-Host "Log: tbcc\.tbcc-run\capture-secret.log" -ForegroundColor Gray
Write-Host "Browser (same store): select key -> TBCC: Save selection as API key to .env" -ForegroundColor Gray
Write-Host "CLI paste-friendly: .\scripts\tbcc-secret.ps1 -Key TBCC_CF_API_TOKEN" -ForegroundColor Gray
Write-Host "Remove: .\register-tbcc-capture-secret-context-menu.ps1 -Unregister" -ForegroundColor Gray
Write-Host ""
Write-Host "NOTE: Primary store = tbcc\.env. Windows Credential Manager = local backup." -ForegroundColor DarkYellow
Write-Host "      GCP Secret Manager = cloud vault for VM auth keys (different tool)." -ForegroundColor DarkYellow
