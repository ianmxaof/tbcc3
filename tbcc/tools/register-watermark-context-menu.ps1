# Register Explorer right-click menus for TBCC AOF promo watermark burn-in.
#   cd tbcc\tools
#   .\register-watermark-context-menu.ps1
#   .\register-watermark-context-menu.ps1 -Unregister

param([switch]$Unregister)

$toolsDir = $PSScriptRoot
$fileLauncher = Join-Path $toolsDir "watermark-context-menu.bat"
$folderLauncher = Join-Path $toolsDir "watermark-context-menu-folder.bat"
$iconPath = Join-Path (Split-Path $toolsDir -Parent) "extension\icons\favicon.ico"

if (-not (Test-Path -LiteralPath $fileLauncher)) {
  Write-Host "Missing: $fileLauncher" -ForegroundColor Red
  exit 1
}

$menuTitle = "TBCC: Watermark with AOF promo"
$folderTitle = "TBCC: Watermark all media in folder"
# Use .bat wrappers — cmd forwards %%1 with correct quoting for paths with spaces/special chars.
$fileCommand = "`"$fileLauncher`" `"%1`""
$folderCommand = "`"$folderLauncher`" `"%1`""

$mediaExtensions = @(
  ".mp4", ".mov", ".webm", ".avi", ".mkv",
  ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"
)

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
    [string]$Command,
    [switch]$MultiSelect
  )
  New-Item -Path $KeyPath -Force | Out-Null
  Set-ItemProperty -LiteralPath $KeyPath -Name "(Default)" -Value $Title
  if (Test-Path -LiteralPath $iconPath) {
    Set-ItemProperty -LiteralPath $KeyPath -Name "Icon" -Value $iconPath
  }
  if ($MultiSelect) {
    Set-ItemProperty -LiteralPath $KeyPath -Name "MultiSelectModel" -Value "Player"
  }
  $commandKey = Join-Path $KeyPath "command"
  New-Item -Path $commandKey -Force | Out-Null
  Set-ItemProperty -LiteralPath $commandKey -Name "(Default)" -Value $Command
}

if ($Unregister) {
  foreach ($ext in $mediaExtensions) {
    Remove-ShellKey "HKCU:\Software\Classes\SystemFileAssociations\$ext\shell\TBCCAOFWatermark"
  }
  Remove-ShellKey "HKCU:\Software\Classes\Directory\shell\TBCCAOFWatermarkFolder"
  Remove-ShellKey "HKCU:\Software\Classes\Directory\Background\shell\TBCCAOFWatermarkFolder"
  Write-Host "Removed TBCC watermark Explorer menus." -ForegroundColor Green
  exit 0
}

foreach ($ext in $mediaExtensions) {
  $key = "HKCU:\Software\Classes\SystemFileAssociations\$ext\shell\TBCCAOFWatermark"
  Set-ShellKey -KeyPath $key -Title $menuTitle -Command $fileCommand
  Write-Host "Registered: *$ext" -ForegroundColor Gray
}

Set-ShellKey `
  -KeyPath "HKCU:\Software\Classes\Directory\shell\TBCCAOFWatermarkFolder" `
  -Title $folderTitle `
  -Command $folderCommand
Set-ShellKey `
  -KeyPath "HKCU:\Software\Classes\Directory\Background\shell\TBCCAOFWatermarkFolder" `
  -Title $folderTitle `
  -Command $folderCommand

Write-Host ""
Write-Host "TBCC watermark context menus registered for current user." -ForegroundColor Green
Write-Host "  Files: right-click image/video -> '$menuTitle'" -ForegroundColor Gray
Write-Host "  Folder: right-click folder or empty space -> '$folderTitle'" -ForegroundColor Gray
Write-Host "On Windows 11, use 'Show more options' if the item is not in the compact menu." -ForegroundColor Gray
Write-Host "Remove with: .\register-watermark-context-menu.ps1 -Unregister" -ForegroundColor Gray
