# Open a local dashboard tunnel to the revenue-island API (island Postgres + scheduler).
# Home :8000 without this tunnel is a DIFFERENT database — not what the VM is posting.
#
#   .\scripts\revenue-island\dashboard-tunnel.ps1
#   .\scripts\revenue-island\dashboard-tunnel.ps1 -HostName root@5.161.53.91 -LocalPort 8000
#
# Leave this window open. Then:
#   npm run dev  (dashboard)  OR browse http://127.0.0.1:8000/health
# Stop: Ctrl+C in this window.

param(
  [string]$HostName = "root@5.161.53.91",
  [int]$LocalPort = 8000,
  [int]$RemotePort = 8000
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "Island dashboard tunnel" -ForegroundColor Cyan
Write-Host "  Local  http://127.0.0.1:$LocalPort  ->  $HostName :$RemotePort" -ForegroundColor DarkGray
Write-Host ""
Write-Host "This IS the VM API (scheduler / media / loot DB)." -ForegroundColor Green
Write-Host "Without this tunnel, home tray backend :8000 is a separate local DB." -ForegroundColor Yellow
Write-Host ""
Write-Host "If LocalPort $LocalPort is busy (home Docker API), stop home backend first or use -LocalPort 8001." -ForegroundColor Yellow
Write-Host "Ctrl+C to close the tunnel." -ForegroundColor DarkGray
Write-Host ""

# -N: no remote shell; -L: local forward
& ssh -N -L "${LocalPort}:127.0.0.1:${RemotePort}" $HostName
