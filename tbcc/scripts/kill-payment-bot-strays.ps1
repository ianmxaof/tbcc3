# Kill duplicate TBCC-PaymentBot workers (Telegram 409 Conflict relief).
. (Join-Path $PSScriptRoot "tbcc-service-control.ps1")
$tbccRoot = Split-Path $PSScriptRoot -Parent
$svc = Get-TbccStackServices -TbccRoot $tbccRoot -FullStack |
  Where-Object { $_.Id -eq 'payment' } | Select-Object -First 1
$killed = @()
if ($svc) {
  $killed += @(Stop-TbccServiceWorkerDuplicates -Service $svc)
}
$killed += @(Stop-TbccProcessesByCommandMatch -Pattern 'py\.exe.*bots\.payment_bot')
$killed += @(Stop-TbccProcessesByCommandMatch -Pattern 'bots\.payment_bot')
$killed = @($killed | Select-Object -Unique)
Write-Host ("Killed PaymentBot workers={0}. Restart ONE TBCC-PaymentBot tab only." -f $killed.Count)
