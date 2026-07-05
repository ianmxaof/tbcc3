# Force restart Beat + Celery-Post + Celery-Post-Scheduler (clears stale session/queue state).
# Used by scheduler watchdog after ineffective hard-resume attempts.
$ErrorActionPreference = "Continue"
$TbccRoot = Split-Path $PSScriptRoot -Parent
. (Join-Path $PSScriptRoot "tbcc-service-control.ps1")

$order = @('beat', 'celery_post', 'celery_post_scheduler')
$results = @()
foreach ($id in $order) {
  try {
    $null = Restart-TbccStackService -ServiceId $id -TbccRoot $TbccRoot -FullStack -UseErrorHubWrapper
    $results += [pscustomobject]@{ id = $id; ok = $true }
    Start-Sleep -Seconds 2
  } catch {
    $results += [pscustomobject]@{ id = $id; ok = $false; error = ($_.Exception.Message).Substring(0, [Math]::Min(200, $_.Exception.Message.Length)) }
  }
}
$ok = @($results | Where-Object { $_.ok }).Count -eq $order.Count
@{
  ok = $ok
  results = $results
} | ConvertTo-Json -Depth 4 -Compress
if (-not $ok) { exit 1 }
