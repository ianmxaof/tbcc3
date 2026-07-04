# Register Explorer right-click menus for TBCC hardened Erome upload.
# Requires erome.params.json in the target folder (see erome.params.example.json).
#   cd tbcc\tools
#   .\register-erome-context-menu.ps1
#   .\register-erome-context-menu.ps1 -Unregister

param([switch]$Unregister)

$toolsDir = $PSScriptRoot
$fileLauncher = Join-Path $toolsDir "erome-context-menu.bat"
$folderLauncher = Join-Path $toolsDir "erome-context-menu-folder.bat"
$iconPath = Join-Path (Split-Path $toolsDir -Parent) "extension\icons\favicon.ico"

if (-not (Test-Path -LiteralPath $fileLauncher)) {
  Write-Host "Missing: $fileLauncher" -ForegroundColor Red
  exit 1
}

$fileTitle = "TBCC: Watermark + upload to Erome"
$folderTitle = "TBCC: Upload folder to Erome"
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
    Remove-ShellKey "HKCU:\Software\Classes\SystemFileAssociations\$ext\shell\TBCCAOFUploadErome"
  }
  Remove-ShellKey "HKCU:\Software\Classes\Directory\shell\TBCCAOFUploadErome"
  Remove-ShellKey "HKCU:\Software\Classes\Directory\Background\shell\TBCCAOFUploadErome"
  Write-Host "Removed TBCC Erome Explorer menus." -ForegroundColor Green
  exit 0
}

foreach ($ext in $mediaExtensions) {
  $key = "HKCU:\Software\Classes\SystemFileAssociations\$ext\shell\TBCCAOFUploadErome"
  Set-ShellKey -KeyPath $key -Title $fileTitle -Command $fileCommand
  Write-Host "Registered: *$ext" -ForegroundColor Gray
}

Set-ShellKey `
  -KeyPath "HKCU:\Software\Classes\Directory\shell\TBCCAOFUploadErome" `
  -Title $folderTitle `
  -Command $folderCommand
Set-ShellKey `
  -KeyPath "HKCU:\Software\Classes\Directory\Background\shell\TBCCAOFUploadErome" `
  -Title $folderTitle `
  -Command $folderCommand

Write-Host ""
Write-Host "TBCC Erome context menus registered for current user." -ForegroundColor Green
Write-Host "  Place erome.params.json beside media before upload." -ForegroundColor Gray
Write-Host "  Example: tbcc/backend/app/data/erome.params.example.json" -ForegroundColor Gray
Write-Host "  Files: watermark + upload selected media's folder" -ForegroundColor Gray
Write-Host "  Folder: upload entire folder (media should already be watermarked)" -ForegroundColor Gray
Write-Host "Remove with: .\register-erome-context-menu.ps1 -Unregister" -ForegroundColor Gray
