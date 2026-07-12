# WT tab monitor: poll GCP remote scrape worker logs on a tick (gcloud-safe; no docker -f follow).
param(
  [Parameter(Mandatory = $true)][string]$TbccRoot,
  [int]$TickSec = 0
)

$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "tbcc-error-hub.ps1")
Initialize-TbccServiceConsole -TbccRoot $TbccRoot -Title "TBCC-RemoteWorker"

$envFile = Join-Path $TbccRoot ".env"
$project = "tbcc-cloud-instance"
$zone = "us-west1-a"
$instance = "tbcc-remote-worker"
$remoteHost = ""
$tick = 5

function Get-EnvVal([string]$Name) {
  if (-not (Test-Path -LiteralPath $envFile)) { return "" }
  foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
    if ($line -match "^\s*$([regex]::Escape($Name))\s*=\s*(.*)$") {
      return $Matches[1].Trim().Trim('"').Trim("'")
    }
  }
  return ""
}

$remoteHost = Get-EnvVal "TBCC_REMOTE_STACK_HOST"
$p = Get-EnvVal "TBCC_GCP_PROJECT"; if ($p) { $project = $p }
$z = Get-EnvVal "TBCC_GCP_ZONE"; if ($z) { $zone = $z }
$n = Get-EnvVal "TBCC_GCP_INSTANCE"; if ($n) { $instance = $n }
$t = Get-EnvVal "TBCC_REMOTE_WORKER_LOG_TICK_S"; if ($t) { try { $tick = [int]$t } catch {} }
if ($TickSec -gt 0) { $tick = $TickSec }

if (-not $remoteHost) {
  Write-Host "TBCC_REMOTE_STACK_HOST unset — remote worker monitor idle." -ForegroundColor Yellow
  while ($true) { Start-Sleep -Seconds 30 }
}

$composeGhcr = "/opt/tbcc/infra/docker-compose.remote-worker.ghcr.yml"
$composeLegacy = "/opt/tbcc/infra/docker-compose.remote-worker.yml"
$logCmd = "docker compose -f $composeGhcr logs --tail=25 worker_scrape 2>/dev/null || docker compose -f $composeLegacy logs --tail=25 worker_scrape 2>&1"
$seen = [System.Collections.Generic.HashSet[string]]::new()

Clear-Host
Write-Host ""
Write-Host "  TBCC Remote Worker Monitor" -ForegroundColor Cyan
Write-Host "  VM: $instance ($remoteHost)  tick: ${tick}s  (Ctrl+C stops this tab only)" -ForegroundColor Gray
Write-Host ""

while ($true) {
  $stamp = Get-Date -Format "HH:mm:ss"
  try {
    $pingOk = $false
    & tailscale ping -c 1 --timeout 4s $remoteHost 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $pingOk = $true }

    $status = if ($pingOk) { "tailnet OK" } else { "tailnet DOWN" }
    Write-Host "[$stamp] --- status: $status ---" -ForegroundColor DarkCyan

    if ($pingOk -and (Get-Command gcloud -ErrorAction SilentlyContinue)) {
      $out = & gcloud compute ssh $instance --zone=$zone --project=$project --tunnel-through-iap --command=$logCmd 2>&1
      foreach ($line in @($out)) {
        $ln = [string]$line
        if (-not $ln.Trim()) { continue }
        if ($seen.Add($ln)) {
          if ($ln -match "ERROR|Traceback|Exception") {
            Write-Host $ln -ForegroundColor Red
          } elseif ($ln -match "WARN") {
            Write-Host $ln -ForegroundColor Yellow
          } else {
            Write-Host $ln -ForegroundColor Gray
          }
        }
      }
      if ($seen.Count -gt 400) { $seen.Clear() }
    }
  } catch {
    Write-Host "[$stamp] fetch error: $_" -ForegroundColor Red
  }
  Start-Sleep -Seconds $tick
}
