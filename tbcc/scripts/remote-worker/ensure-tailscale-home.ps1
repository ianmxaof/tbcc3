# Ensure Tailscale is up on the home PC for TBCC remote worker mesh (GCP VM scrape consumer).
# Dot-source from start.ps1 or run standalone:
#   . .\scripts\remote-worker\ensure-tailscale-home.ps1
#   Ensure-TbccTailscaleMesh -RemoteHost 100.x.y.z

function Ensure-TbccTailscaleMesh {
  param(
    [string]$RemoteHost = "",
    [int]$MaxWaitSeconds = 90
  )

  $ts = Get-Command tailscale -ErrorAction SilentlyContinue
  if (-not $ts) {
    Write-Host "  Tailscale CLI not found. Run: .\scripts\remote-worker\install-tailscale-home.ps1" -ForegroundColor Red
    return @{ ok = $false; homeIp = ""; remoteReachable = $false }
  }

  $svc = Get-Service -Name Tailscale -ErrorAction SilentlyContinue
  if ($svc -and $svc.Status -ne "Running") {
    Write-Host "  Starting Tailscale service..." -ForegroundColor Yellow
    try {
      Start-Service Tailscale
    } catch {
      Write-Host "  Could not start Tailscale service: $($_.Exception.Message)" -ForegroundColor Red
      return @{ ok = $false; homeIp = ""; remoteReachable = $false }
    }
  }

  $homeIp = (& tailscale ip -4 2>$null | Select-Object -First 1)
  if ($homeIp) { $homeIp = $homeIp.Trim() }

  if (-not $homeIp) {
    Write-Host "  Tailscale not connected - running tailscale up (same account as GCP VM)..." -ForegroundColor Yellow
    & tailscale up 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
      Write-Host "  tailscale up failed. Open Tailscale from the tray and sign in (ianm.powercore@gmail.com)." -ForegroundColor Red
      return @{ ok = $false; homeIp = ""; remoteReachable = $false }
    }
  }

  $deadline = (Get-Date).AddSeconds($MaxWaitSeconds)
  while ((Get-Date) -lt $deadline) {
    $homeIp = (& tailscale ip -4 2>$null | Select-Object -First 1)
    if ($homeIp) {
      $homeIp = $homeIp.Trim()
      if ($homeIp) { break }
    }
    Start-Sleep -Seconds 2
  }

  if (-not $homeIp) {
    Write-Host "  Timed out waiting for Tailscale IPv4. Open the Tailscale app and confirm Connected." -ForegroundColor Red
    return @{ ok = $false; homeIp = ""; remoteReachable = $false }
  }

  Write-Host "  Tailscale connected - home IPv4: $homeIp" -ForegroundColor Green

  $remoteReachable = $false
  if ($RemoteHost) {
    Write-Host "  Checking remote worker $RemoteHost ..." -ForegroundColor Gray
    & tailscale ping -c 1 --timeout 5s $RemoteHost 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
      $remoteReachable = $true
      Write-Host "  Remote worker reachable on tailnet." -ForegroundColor Green
    } else {
      Write-Host "  Remote worker not reachable yet (VM off, Tailscale down on VM, or wrong IP in .env)." -ForegroundColor Yellow
      Write-Host "  Scrape queue will backlog until VM is up: .\scripts\remote-worker\connect-gcp-vm.ps1 -Logs" -ForegroundColor DarkYellow
    }
  }

  return @{ ok = $true; homeIp = $homeIp; remoteReachable = $remoteReachable }
}
