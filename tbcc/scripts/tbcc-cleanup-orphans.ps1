# Kill orphaned uvicorn multiprocessing workers and verify port 8000 is bindable.
#   powershell -File tbcc\scripts\tbcc-cleanup-orphans.ps1
#   powershell -File tbcc\scripts\tbcc-cleanup-orphans.ps1 -AlsoStopTbccStack

param(
  [switch]$AlsoStopTbccStack
)

$ErrorActionPreference = "Continue"
$tbccDir = Split-Path -Parent $PSScriptRoot
$controlScript = Join-Path $PSScriptRoot "tbcc-service-control.ps1"

if ($AlsoStopTbccStack -and (Test-Path -LiteralPath $controlScript)) {
  . $controlScript
  Write-Host "[stop] TBCC stack..." -ForegroundColor Yellow
  $null = Stop-TbccPriorStackWindows -TbccRoot $tbccDir -FullStack -Wait -MaxWaitSeconds 60
}

$killed = 0
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match 'multiprocessing\.spawn|multiprocessing-fork' } |
  ForEach-Object {
    Write-Host "Killing orphan worker PID $($_.ProcessId)" -ForegroundColor Yellow
    taskkill /PID $_.ProcessId /T /F 2>$null | Out-Null
    $script:killed++
  }

# Do not kill the main uvicorn listener on :8000 — only multiprocessing-fork children above.
Start-Sleep -Seconds 1
try {
  $client = New-Object System.Net.Sockets.TcpClient
  $client.Connect("127.0.0.1", 8000)
  $client.Close()
  Write-Host 'WARNING: Something still accepts connections on :8000' -ForegroundColor Red
} catch {
  Write-Host ('Port 8000 appears free (' + $killed + ' orphan process(es) cleaned).') -ForegroundColor Green
}
