# One-shot: ngrok tunnel -> set TBCC_PROMO_PUBLIC_BASE_URL in tbcc/.env -> restart API (+ payment bot).
#
# Prerequisites: ngrok installed + `ngrok config add-authtoken ...` done once.
#
# Usage (from tbcc folder):
#   .\setup-promo-tunnel.ps1
#   .\setup-promo-tunnel.ps1 -SkipDocker          # skip postgres/redis compose
#   .\setup-promo-tunnel.ps1 -ApiOnly              # after .env update, only restart API (not payment bot)
#
# What it does:
#   1) Optional: docker compose up postgres + redis (same infra file as start.ps1)
#   2) Ensure ngrok http 8000 (shared tbcc-ngrok-tunnel.ps1)
#   3) Write TBCC_PROMO_PUBLIC_BASE_URL + TBCC_PUBLIC_API_BASE_URL to tbcc/.env
#   4) Run .\restart-api-payment.ps1 (or -ApiOnly)

$ErrorActionPreference = "Continue"
$tbccDir = $PSScriptRoot
$backendDir = Join-Path $tbccDir "backend"
$envFile = Join-Path $tbccDir ".env"

$skipDocker = $args -contains "-SkipDocker"
$apiOnlyRestart = ($args -contains "-ApiOnly") -or ($args -contains "-NoPaymentBot")

function Start-TbccCmdWindow {
  param([string]$Title, [string]$Command)
  $run = 'title "' + $Title + '" && ' + $Command
  Start-Process -FilePath $env:ComSpec -ArgumentList @("/k", $run) -WindowStyle Normal
}

function Read-TbccDotEnv {
  param([Parameter(Mandatory = $true)][string]$Path)
  $map = @{}
  if (-not (Test-Path -LiteralPath $Path)) { return $map }
  foreach ($line in Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue) {
    $t = $line.Trim()
    if (-not $t -or $t.StartsWith("#")) { continue }
    $eq = $t.IndexOf("=")
    if ($eq -lt 1) { continue }
    $k = $t.Substring(0, $eq).Trim()
    $v = $t.Substring($eq + 1).Trim()
    if ($v.StartsWith('"') -and $v.EndsWith('"') -and $v.Length -ge 2) { $v = $v.Substring(1, $v.Length - 2) }
    $map[$k] = $v
  }
  return $map
}

Write-Host ""
Write-Host 'TBCC setup-promo-tunnel (ngrok, TBCC_PROMO_PUBLIC_BASE_URL, restart)' -ForegroundColor Cyan
Write-Host ""

$ngrokScript = Join-Path $tbccDir "scripts\tbcc-ngrok-tunnel.ps1"
if (-not (Test-Path -LiteralPath $ngrokScript)) {
  Write-Host 'Missing scripts\tbcc-ngrok-tunnel.ps1' -ForegroundColor Red
  exit 1
}
. $ngrokScript

# 0. Docker (optional)
if (-not $skipDocker) {
  $infraCompose = Join-Path $tbccDir "infra\docker-compose.infra.yml"
  $legacyCompose = Join-Path $tbccDir "infra\docker-compose.yml"
  $composeFile = if (Test-Path $infraCompose) { $infraCompose } elseif (Test-Path $legacyCompose) { $legacyCompose } else { $null }
  if ($composeFile) {
    Write-Host ('[0] Docker: postgres + redis ' + [IO.Path]::GetFileName($composeFile) + ' ...') -ForegroundColor Yellow
    Push-Location (Join-Path $tbccDir "infra")
    try {
      $composeName = [IO.Path]::GetFileName($composeFile)
      if ($composeName -eq 'docker-compose.infra.yml') {
        cmd /c 'docker compose -f docker-compose.infra.yml up -d postgres redis' 2>$null
      } elseif (Test-Path $envFile) {
        $ef = (Resolve-Path $envFile).Path
        cmd /c ('docker compose --env-file "' + $ef + '" -f "' + $composeName + '" up -d postgres redis') 2>$null
      } else {
        cmd /c ('docker compose -f "' + $composeName + '" up -d postgres redis') 2>$null
      }
    } finally {
      Pop-Location
    }
    Start-Sleep -Seconds 2
  } else {
    Write-Host '[0] No infra compose file — skip Docker.' -ForegroundColor DarkYellow
  }
} else {
  Write-Host '[0] Skipping Docker (-SkipDocker).' -ForegroundColor DarkYellow
}

# 1–2. ngrok + .env
Write-Host '[1] Ensuring ngrok tunnel to http://localhost:8000 ...' -ForegroundColor Yellow
$dotEnv = Read-TbccDotEnv -Path $envFile
$ngrokStartCmd = {
  param([string]$Title, [string]$Command)
  Start-TbccCmdWindow -Title $Title -Command $Command
}
$ngrokResult = Ensure-TbccNgrokTunnel -TbccRoot $tbccDir -EnvMap $dotEnv -FullStack:$true -StartCmdWindow $ngrokStartCmd
foreach ($m in $ngrokResult.messages) {
  $color = if (-not $ngrokResult.ok) { 'Red' } elseif ($ngrokResult.started -or $ngrokResult.updatedEnv) { 'Green' } else { 'Gray' }
  Write-Host ('  ' + $m) -ForegroundColor $color
}
if (-not $ngrokResult.ok) {
  Write-Host 'Check the TBCC-ngrok window: authtoken, firewall, or port conflict.' -ForegroundColor Yellow
  exit 1
}
$publicUrl = $ngrokResult.publicUrl
Write-Host ('  Public HTTPS URL: ' + $publicUrl) -ForegroundColor Green

# 3. Restart API (+ optional payment bot) so process reloads env
Write-Host '[3] Restarting API (loads new env) ...' -ForegroundColor Yellow
$restartArgs = @()
if ($apiOnlyRestart) { $restartArgs += '-ApiOnly' }
$restartScript = Join-Path $tbccDir 'restart-api-payment.ps1'
& $restartScript @restartArgs
if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
  Write-Host ('restart-api-payment.ps1 exited with code ' + $LASTEXITCODE) -ForegroundColor Yellow
}

Write-Host ""
Write-Host 'Next steps (manual):' -ForegroundColor Cyan
Write-Host '  - Dashboard, Bots, Shop: use Upload again on promo images (old localhost URLs stay wrong until re-upload).' -ForegroundColor Gray
Write-Host ('  - Test in browser: ' + $publicUrl + '/static/promo/sample.jpg') -ForegroundColor Gray
Write-Host ""
