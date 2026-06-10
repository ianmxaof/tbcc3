# One-shot: start Beat + Celery workers (used by health remediate).
$ErrorActionPreference = "Continue"
$TbccRoot = Split-Path $PSScriptRoot -Parent
. (Join-Path $PSScriptRoot "tbcc-service-control.ps1")
foreach ($id in @("beat", "celery", "celery_post")) {
  $svc = Get-TbccStackServices -TbccRoot $TbccRoot -FullStack |
    Where-Object { $_.Id -eq $id } | Select-Object -First 1
  if ($svc) {
    Write-Host "Starting $($svc.Title)..."
    Start-TbccStackService -Service $svc -TbccRoot $TbccRoot -UseErrorHubWrapper
    Start-Sleep -Milliseconds 600
  }
}
