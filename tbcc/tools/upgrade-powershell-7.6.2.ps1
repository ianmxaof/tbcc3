#Requires -Version 5.1
<#
.SYNOPSIS
  Upgrade PowerShell 7 to 7.6.2 (win-x64 MSI from GitHub release).

.DESCRIPTION
  TBCC tray/cold-start still uses Windows PowerShell 5.1 (powershell.exe).
  This script only updates pwsh used by Cursor terminals and the PowerShell extension.

  Run from an elevated prompt, or allow the UAC prompt when this script re-launches itself:
    powershell -ExecutionPolicy Bypass -File tbcc\tools\upgrade-powershell-7.6.2.ps1
#>
param(
  [string]$TargetVersion = "7.6.2",
  [string]$MsiUrl = "https://github.com/PowerShell/PowerShell/releases/download/v7.6.2/PowerShell-7.6.2-win-x64.msi",
  [string]$ExpectedSha256 = "096A6DBB5BB330C5E14559FF1A7081BD274C07C07E2545755B93A93417E32629"
)

$ErrorActionPreference = "Stop"
$pwshDir = Join-Path ${env:ProgramFiles} "PowerShell\7"
$pwshExe = Join-Path $pwshDir "pwsh.exe"

function Test-IsAdmin {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $p = New-Object Security.Principal.WindowsPrincipal($id)
  return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-InstalledPwshVersion {
  if (-not (Test-Path $pwshExe)) { return $null }
  return (& $pwshExe -NoProfile -Command '$PSVersionTable.PSVersion.ToString()')
}

$installed = Get-InstalledPwshVersion
if ($installed -eq $TargetVersion) {
  Write-Host "PowerShell $TargetVersion already installed at $pwshExe" -ForegroundColor Green
  exit 0
}

if (-not (Test-IsAdmin)) {
  Write-Host "Re-launching elevated (approve UAC)..." -ForegroundColor Yellow
  $argList = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`""
  )
  Start-Process -FilePath "powershell.exe" -ArgumentList $argList -Verb RunAs -Wait
  $after = Get-InstalledPwshVersion
  if ($after -eq $TargetVersion) { exit 0 }
  Write-Error "Upgrade did not complete. Run this script again from an Administrator PowerShell window."
  exit 1
}

$msi = Join-Path $env:TEMP "PowerShell-$TargetVersion-win-x64.msi"
Write-Host "Downloading $MsiUrl ..." -ForegroundColor Cyan
Invoke-WebRequest -Uri $MsiUrl -OutFile $msi -UseBasicParsing

$hash = (Get-FileHash -Path $msi -Algorithm SHA256).Hash
if ($hash -ne $ExpectedSha256) {
  Remove-Item -Force $msi -ErrorAction SilentlyContinue
  throw "MSI hash mismatch (got $hash, expected $ExpectedSha256)"
}

Write-Host "Installing PowerShell $TargetVersion (quiet)..." -ForegroundColor Cyan
$msiArgs = @(
  "/i", "`"$msi`"", "/quiet", "/norestart",
  "ADD_EXPLORER_CONTEXT_MENU_OPENPOWERSHELL=1",
  "ENABLE_PSREMOTING=1", "REGISTER_MANIFEST=1", "USE_MU=1", "ENABLE_MU=1"
)
$p = Start-Process -FilePath "msiexec.exe" -ArgumentList $msiArgs -Wait -PassThru
Remove-Item -Force $msi -ErrorAction SilentlyContinue

if ($p.ExitCode -ne 0) {
  throw "msiexec exited with $($p.ExitCode)"
}

$final = Get-InstalledPwshVersion
Write-Host "Installed: $final at $pwshExe" -ForegroundColor Green
Write-Host "In Cursor: Developer Reload Window, or click Yes on PowerShell extension restart." -ForegroundColor DarkGray
