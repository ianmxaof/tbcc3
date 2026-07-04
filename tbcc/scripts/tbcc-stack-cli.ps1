# TBCC stack CLI — tray supervisor control for API / flywheel (JSON stdout).
param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("Start", "Stop", "Restart", "Status")]
  [string]$Action,
  [string]$Service = "",
  [string]$TbccRoot = ""
)

$ErrorActionPreference = "Stop"
if (-not $TbccRoot) { $TbccRoot = Split-Path $PSScriptRoot -Parent }
. (Join-Path $PSScriptRoot "tbcc-service-control.ps1")

function Write-StackJson {
  param($Obj)
  $Obj | ConvertTo-Json -Depth 6 -Compress
}

if ($Action -eq "Status" -and -not $Service) {
  $cache = Update-TbccServiceStatusCache -TbccRoot $TbccRoot -FullStack
  $rows = New-Object System.Collections.ArrayList
  foreach ($svc in $cache.Services) {
    $row = $cache.ById[$svc.Id]
    [void]$rows.Add(@{
        id           = $svc.Id
        title        = $svc.Title
        port         = $svc.Port
        status       = $row.Status
        user_enabled = [bool]$row.UserEnabled
        running      = ($row.Status -eq "up")
      })
  }
  Write-StackJson @{
    ok         = $true
    enabled_up = $cache.EnabledUp
    enabled    = $cache.Enabled
    total      = $cache.Total
    up         = $cache.Up
    profile    = (Get-TbccStackProfileLabel -TbccRoot $TbccRoot)
    services   = $rows.ToArray()
  }
  exit 0
}

if (-not $Service) {
  Write-StackJson @{ ok = $false; error = "Service id required for action $Action" }
  exit 1
}

$svc = @(Get-TbccStackServices -TbccRoot $TbccRoot -FullStack |
  Where-Object { $_.Id -eq $Service } | Select-Object -First 1)
if (-not $svc) {
  Write-StackJson @{ ok = $false; error = "Unknown service id: $Service" }
  exit 1
}

if ($Action -eq "Status") {
  $running = Test-TbccServiceProcessRunning -Service $svc
  Write-StackJson @{
    ok         = $true
    service_id = $Service
    title      = $svc.Title
    running    = [bool]$running
    status     = $(if ($running) { "up" } else { "down" })
  }
  exit 0
}

try {
  switch ($Action) {
    "Start" {
      Start-TbccStackService -Service $svc -TbccRoot $TbccRoot -UseErrorHubWrapper -Force
    }
    "Stop" {
      $null = Stop-TbccStackService -Service $svc -TbccRoot $TbccRoot -GracefulTabClose
    }
    "Restart" {
      $null = Restart-TbccStackService -ServiceId $Service -TbccRoot $TbccRoot -FullStack -UseErrorHubWrapper
    }
  }
  $running = Test-TbccServiceProcessRunning -Service $svc
  Write-StackJson @{
    ok         = $true
    action     = $Action
    service_id = $Service
    title      = $svc.Title
    running    = [bool]$running
    status     = $(if ($running) { "up" } else { "down" })
  }
  exit 0
} catch {
  Write-StackJson @{ ok = $false; error = $_.Exception.Message; service_id = $Service; action = $Action }
  exit 1
}
