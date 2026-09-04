# Deploy local TBCC changes to the live revenue island immediately.
# Builds on island when local Docker is unavailable; seeds DB; recycles services.
#
#   .\scripts\revenue-island\deploy-island-live.ps1
#   .\scripts\revenue-island\deploy-island-live.ps1 -SkipTunnel -SkipSeeds   # fast test deploy
#   .\scripts\revenue-island\deploy-island-live.ps1 -UseGhcrPull   # skip rsync build; pull :latest only

param(
  [string]$HostName = "root@5.161.53.91",
  [string]$RemoteDir = "/opt/tbcc",
  [switch]$SkipBuild,
  [switch]$UseGhcrPull,
  [switch]$SkipTunnel,
  [switch]$SkipSeeds,
  [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$tbccRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$backend = Join-Path $tbccRoot "backend"
$composeFile = "docker-compose.revenue-island.yml"
$envFile = ".env.revenue-island"
$localTag = "ghcr.io/ianmxaof/tbcc-worker:local-$(Get-Date -Format 'yyyyMMdd-HHmm')"

function Invoke-Remote([string]$cmd) {
  if ($WhatIf) { Write-Host "WHATIF ssh $HostName $cmd" -ForegroundColor DarkGray; return "" }
  $prev = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $out = (& ssh $HostName $cmd 2>&1 | Out-String).TrimEnd()
  $ErrorActionPreference = $prev
  if ($LASTEXITCODE -ne 0) { throw "Remote command failed (exit $LASTEXITCODE): $cmd`n$out" }
  return $out
}

function Invoke-Compose([string]$composeArgs) {
  $inner = "cd $RemoteDir/infra && docker compose -f $composeFile --env-file $envFile $composeArgs"
  Invoke-Remote $inner
}

Write-Host "=== TBCC revenue island live deploy -> $HostName ===" -ForegroundColor Cyan

# 1) Seed island env from home (never commits secrets)
Write-Host "`n[1/7] Seed island env from home .env" -ForegroundColor Yellow
& (Join-Path $PSScriptRoot "seed-island-env-from-home.ps1")
if ($WhatIf) { Write-Host "WhatIf: skipping sync/build" -ForegroundColor Yellow; exit 0 }

# 2) Sync compose + scripts (+ filled env)
Write-Host "`n[2/7] Sync compose/scripts/env to island" -ForegroundColor Yellow
& (Join-Path $PSScriptRoot "sync-island-files.ps1") -HostName $HostName -IncludeFilledEnv
$installTunnel = Join-Path $PSScriptRoot "install-island-api-tunnel.sh"
& scp $installTunnel "${HostName}:$RemoteDir/scripts/revenue-island/"
Invoke-Remote "sed -i 's/\r`$//' $RemoteDir/scripts/revenue-island/install-island-api-tunnel.sh && chmod +x $RemoteDir/scripts/revenue-island/install-island-api-tunnel.sh"

# 3) HTTPS tunnel for webhooks (skip if TBCC_ISLAND_API_PUBLIC_URL already set on home)
if (-not $SkipTunnel) {
  $islandEnv = Join-Path $tbccRoot "infra\.env.revenue-island"
  $hasPublic = Select-String -Path $islandEnv -Pattern "^TBCC_PUBLIC_API_BASE_URL=https://" -Quiet
  if (-not $hasPublic) {
    Write-Host "`n[3/7] Install Cloudflare quick tunnel (public HTTPS for webhooks)" -ForegroundColor Yellow
    Invoke-Remote "bash $RemoteDir/scripts/revenue-island/install-island-api-tunnel.sh"
    # Re-sync env after tunnel patches island file locally on VPS — pull back not needed; patch happened on VPS
    & scp "${HostName}:$RemoteDir/infra/.env.revenue-island" (Join-Path $tbccRoot "infra\.env.revenue-island")
  } else {
    Write-Host "`n[3/7] Public API URL already set - skip tunnel" -ForegroundColor DarkGray
  }
} else {
  Write-Host "`n[3/7] Skip tunnel (-SkipTunnel)" -ForegroundColor DarkGray
}

# 4) Code deploy — rsync backend + build on island OR pull GHCR
if ($UseGhcrPull) {
  Write-Host "`n[4/7] Pull GHCR :latest on island" -ForegroundColor Yellow
  Invoke-Remote "cd $RemoteDir/infra && docker compose -f $composeFile --env-file $envFile pull api worker worker_telegram worker_post beat payment_bot loot_bot companion_bot secretary_bot || true"
} elseif (-not $SkipBuild) {
  Write-Host "`n[4/7] Rsync backend + docker build on island ($localTag)" -ForegroundColor Yellow
  # Staging dir: the compose bind-mounts $RemoteDir/backend-src/{app,bots} into every running
  # container, so writing the new tree straight into backend-src would pull the code out from
  # under live containers for the whole docker-build. Unpack + build from staging instead, then
  # sync into backend-src at the last moment, immediately before the recreate in step 5.
  $stageDir = "$RemoteDir/backend-src.staging"
  Invoke-Remote "mkdir -p $RemoteDir/backend-src $stageDir"
  $tgz = Join-Path $env:TEMP "tbcc-backend-deploy.tgz"
  # GNU tar (MSYS2/Git for Windows) — put its dir first so `tar` AND its `gzip`
  # dependency resolve together; --force-local keeps GNU tar from reading the
  # "C:" drive letter in $tgz as a remote host (user@host:file). Windows bsdtar
  # (C:\Windows\System32) lacks --force-local, so always prefer the Git build.
  $gitUsrBin = @("$env:ProgramFiles\Git\usr\bin", "$env:LOCALAPPDATA\hermes\git\usr\bin") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
  if ($gitUsrBin) { $env:PATH = "$gitUsrBin;$env:PATH" }
  if (Get-Command tar -ErrorAction SilentlyContinue) {
    Push-Location $backend
    # Ship-log cache + improvement notes for weekly build log (island container has no git).
    $dataDir = Join-Path $backend "app\data"
    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
    & py -3.13 scripts/ship_log_sources.py --since "7 days ago" --max-commits 40 --write-cache | Out-Null
    $notesSrc = Join-Path $tbccRoot "docs\TBCC_IMPROVEMENT_NOTES.md"
    if (Test-Path $notesSrc) {
      Copy-Item $notesSrc (Join-Path $dataDir "TBCC_IMPROVEMENT_NOTES_SNAPSHOT.md") -Force
    }
    # Raw frame-*.png (~100MB+) are never selected at runtime (clean/ pool only).
    # Omit them so scp + island docker build stay fast and SSH-stable.
    # --force-local: GNU tar (MSYS2, Git for Windows) otherwise parses the "C:" drive letter in
    # $tgz as a remote host spec (user@host:file) and tries to rsh/ssh into a host named "C".
    if (Test-Path $tgz) { Remove-Item $tgz -Force }
    & tar -czf $tgz --force-local `
      --exclude=__pycache__ `
      --exclude=.pytest_cache `
      --exclude=.tbcc-run `
      --exclude="*.session" `
      --exclude="*.session-wal" `
      --exclude="celerybeat-schedule*" `
      --exclude="app/data/loot_tier_cards/frames/frame-*.png" `
      --exclude="app/data/loot_tier_cards/frames/_source" `
      --exclude="app/data/loot_tier_cards/frames/_rembg" `
      --exclude="app/data/loot_tier_cards/_import_bgclean" `
      --exclude="app/data/loot_tier_cards/_preview" `
      .
    $tarExit = $LASTEXITCODE
    Pop-Location
    if ($tarExit -ne 0 -or -not (Test-Path $tgz)) { throw "local tar packaging failed (exit $tarExit) - nothing valid to ship" }
    & scp $tgz "${HostName}:/tmp/tbcc-backend-deploy.tgz"
    if ($LASTEXITCODE -ne 0) { throw "scp backend tarball failed" }
    # Unpack into staging, NOT into the live bind-mount source.
    Invoke-Remote "rm -rf $stageDir && mkdir -p $stageDir && tar xzf /tmp/tbcc-backend-deploy.tgz -C $stageDir && rm -f /tmp/tbcc-backend-deploy.tgz"
  } else {
    Invoke-Remote "rm -rf $stageDir && mkdir -p $stageDir"
    & scp -r "$backend\*" "${HostName}:$stageDir/"
    if ($LASTEXITCODE -ne 0) { throw "scp backend failed" }
  }
  # Sanity-gate the staged tree before it is allowed anywhere near the live one. A truncated
  # scp or a half-written tar must fail the deploy, not silently ship an empty app/.
  Invoke-Remote @"
test -f $stageDir/app/main.py || { echo 'STAGING INVALID: app/main.py missing'; exit 1; }
test -d $stageDir/bots || { echo 'STAGING INVALID: bots/ missing'; exit 1; }
n=`$(find $stageDir -name '*.py' | wc -l); test "`$n" -ge 800 || { echo "STAGING INVALID: only `$n .py files"; exit 1; }
echo "staging ok (`$n .py files)"
"@
  # Build from staging — containers keep running the current code for the whole build.
  Invoke-Remote "docker build -t $localTag $stageDir"
  # Now swap the live tree. rsync updates in place, so the bind-mount inode never changes and
  # containers are never left without code; only changed files are touched. Step 5 recreates
  # immediately after, which is what makes the new modules actually load.
  Invoke-Remote @"
command -v rsync >/dev/null || { echo 'rsync missing on island - refusing unsafe rm -rf swap'; exit 1; }
rsync -a --delete --exclude='__pycache__' $stageDir/ $RemoteDir/backend-src/
rm -rf $stageDir
"@
  # Point compose at local tag
  Invoke-Remote @"
grep -q '^TBCC_WORKER_IMAGE=' $RemoteDir/infra/$envFile && sed -i 's|^TBCC_WORKER_IMAGE=.*|TBCC_WORKER_IMAGE=$localTag|' $RemoteDir/infra/$envFile || echo 'TBCC_WORKER_IMAGE=$localTag' >> $RemoteDir/infra/$envFile
"@
} else {
  Write-Host "`n[4/7] Skip build (-SkipBuild)" -ForegroundColor DarkGray
}

# 5) Recreate stack
Write-Host "`n[5/7] Recreate api + workers + bots" -ForegroundColor Yellow
Invoke-Compose "up -d --pull never --force-recreate api worker worker_telegram worker_post beat"
Invoke-Compose "--profile bots up -d --pull never --force-recreate payment_bot loot_bot companion_bot secretary_bot album_composer_bot macro_search_bot"

# 6) Migrations + seeds
if (-not $SkipSeeds) {
  Write-Host "`n[6/7] Alembic + VIP/Gumroad seeds" -ForegroundColor Yellow
  Invoke-Compose "exec -T api alembic upgrade head"
  Invoke-Compose "exec -T api python scripts/seed_aof_shop_and_loot.py --execute"
  Invoke-Compose "exec -T api python scripts/seed_promo_affiliate_links.py"
  Invoke-Compose "exec -T api python scripts/repair_content_lanes.py --execute --min-approved 12 --batch 12"
  Invoke-Compose "exec -T api python scripts/apply_network_album_checkout.py --execute --sync-schedulers"
  Invoke-Compose "exec -T api python scripts/stock_buffer_armory.py --relay --scheduled"
  Invoke-Remote "mkdir -p /opt/tbcc/uploads/bundles /opt/tbcc/uploads/promo"
  Write-Host "Bootstrap Storage Hub panels (remixer on island)" -ForegroundColor Yellow
  $bootstrapAttempt = 0
  $bootstrapMaxAttempts = 4
  $bootstrapOk = $false
  while (-not $bootstrapOk -and $bootstrapAttempt -lt $bootstrapMaxAttempts) {
      $bootstrapAttempt++
      try {
          Invoke-Compose "exec -T api python scripts/bootstrap_storage_hub_panels.py"
          $bootstrapOk = $true
      } catch {
          $errOut = $_.Exception.Message
          Write-Host "WARN: Storage Hub panel bootstrap attempt $bootstrapAttempt failed: $errOut" -ForegroundColor Yellow
          if ($bootstrapAttempt -ge $bootstrapMaxAttempts) { break }
          $retrySeconds = 15
          if ($errOut -match 'Retry in (\d+)') {
              $retrySeconds = [int]$Matches[1]
          } elseif ($errOut -match 'Flood control exceeded') {
              $retrySeconds = 15
          }
          $sleepSeconds = $retrySeconds + 2
          Write-Host "Flood-control backoff: sleeping $sleepSeconds seconds before retry..." -ForegroundColor Yellow
          Start-Sleep -Seconds $sleepSeconds
      }
  }
  if (-not $bootstrapOk) {
      Write-Host 'WARN: Storage Hub panel bootstrap failed after 3 retries - run bootstrap_storage_hub_panels.py manually on island' -ForegroundColor Yellow
      exit 0
  }
} else {
  Write-Host "`n[6/7] Skip seeds (-SkipSeeds)" -ForegroundColor DarkGray
}
Write-Host "Refresh @aofmainhub VIP pin (CTA comparison)" -ForegroundColor Yellow
try {
  Invoke-Compose "exec -T api python scripts/apply_mainhub_growth.py --execute --post-now"
} catch {
  Write-Host 'WARN: apply_mainhub_growth failed - run manually on island' -ForegroundColor Yellow
}

# 7) Verify + ensure databases + tunnel/API reachable
Write-Host "`n[7/7] DB watchdog + health + tunnel ensure" -ForegroundColor Yellow
$ensureDbScript = Join-Path $PSScriptRoot "ensure-island-databases.sh"
$installWatchdog = Join-Path $PSScriptRoot "install-island-database-watchdog.sh"
$ensureScript = Join-Path $PSScriptRoot "ensure-island-api-reachable.sh"
& scp $ensureDbScript $installWatchdog $ensureScript "${HostName}:$RemoteDir/scripts/revenue-island/"
$normalizeScripts = "sed -i 's/\r`$//' $RemoteDir/scripts/revenue-island/ensure-island-databases.sh $RemoteDir/scripts/revenue-island/install-island-database-watchdog.sh $RemoteDir/scripts/revenue-island/ensure-island-api-reachable.sh; chmod +x $RemoteDir/scripts/revenue-island/ensure-island-databases.sh $RemoteDir/scripts/revenue-island/install-island-database-watchdog.sh $RemoteDir/scripts/revenue-island/ensure-island-api-reachable.sh"
Invoke-Remote $normalizeScripts
try {
  Invoke-Remote "bash $RemoteDir/scripts/revenue-island/install-island-database-watchdog.sh"
} catch {
  Write-Host 'WARN: database watchdog install failed - run install-island-database-watchdog.sh on VPS' -ForegroundColor Yellow
}
try {
  $health = Invoke-Remote "bash $RemoteDir/scripts/revenue-island/ensure-island-api-reachable.sh --public-check"
  Write-Host $health -ForegroundColor Green
} catch {
  Write-Host 'WARN: ensure-island-api-reachable failed - check tunnel + api on VPS' -ForegroundColor Yellow
  $health = Invoke-Remote 'curl -fsS --max-time 8 http://127.0.0.1:8000/health || true'
  Write-Host $health
}
$plansSql = 'SELECT id, name, price_stars, is_active FROM subscription_plans WHERE bot_section=''main'' ORDER BY id;'
$plansCmd = "cd $RemoteDir/infra; docker compose -f $composeFile --env-file $envFile exec -T postgres psql -U postgres -d tbcc -t -c `"$plansSql`""
$plans = Invoke-Remote $plansCmd
Write-Host $plans

Write-Host "`nCompanion ops:" -ForegroundColor Yellow
try {
  $companion = Invoke-Remote "curl -fsS http://127.0.0.1:8000/companion/ops"
  Write-Host $companion -ForegroundColor Green
} catch {
  Write-Host "WARN: /companion/ops failed (token/LLM may be unset on island)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Deploy complete ===" -ForegroundColor Green
Write-Host 'Update Gumroad Ping + NOWPayments IPN to the URL in infra/.api-public-url on the VPS if tunnel was restarted.'
Write-Host 'Smoke: payment /subscribe - loot /roll - @aof_spicybot_bot /start - GET /companion/ops'
