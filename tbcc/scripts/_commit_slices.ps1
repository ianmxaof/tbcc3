# One-shot: slice uncommitted TBCC work into logical commits on current branch.
# Excludes secrets/runtime (.env, .tbcc-run, sessions) by never adding them.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent)
if (-not (Test-Path '.git')) { Set-Location (Join-Path (Get-Location) '..') }

function Commit-Slice {
  param([string]$Message, [string[]]$Paths)
  $existing = @($Paths | Where-Object { Test-Path $_ })
  if ($existing.Count -eq 0) { Write-Host "SKIP (no paths): $Message"; return }
  git add -- @existing
  $staged = git diff --cached --name-only
  if (-not $staged) { Write-Host "SKIP (nothing staged): $Message"; return }
  git commit -m $Message
  Write-Host "OK: $Message ($($staged.Count) files)"
}

Commit-Slice 'fix(ops): dedupe run_schedule backlog and prioritize imports over thumbnail warm' @(
  'tbcc/backend/app/services/celery_queue_ops.py',
  'tbcc/backend/app/services/system_health.py',
  'tbcc/backend/app/services/thumb_cache_service.py',
  'tbcc/backend/tests/test_celery_queue_purge.py',
  'tbcc/backend/tests/test_scheduler_stall.py',
  'tbcc/backend/tests/test_thumb_cache_service.py',
  'tbcc/.env.example'
)

Commit-Slice 'ux(tray): plain-English Services menu labels and tooltips' @(
  'tbcc/scripts/tbcc-service-control.ps1',
  'tbcc/tools/tbcc-supervisor.ps1',
  'tbcc/tools/tbcc-supervisor-panel.ps1',
  'tbcc/tools/README.md'
)

Commit-Slice 'feat(loot): operator key roll, zeus menu, tier cards, and loot services' @(
  'tbcc/backend/bots/loot_bot.py',
  'tbcc/backend/bots/zeus_menu.py',
  'tbcc/backend/app/services/loot_operator_access.py',
  'tbcc/backend/app/services/tbcc_operator_ids.py',
  'tbcc/backend/app/services/gemini_loot_card_prompt.py',
  'tbcc/backend/app/data/aof_loot_card_presets.json',
  'tbcc/backend/app/services/loot_buffer_mirror.py',
  'tbcc/backend/app/services/loot_daily_promo.py',
  'tbcc/backend/app/services/loot_free_pull.py',
  'tbcc/backend/app/services/loot_preview_delivery.py',
  'tbcc/backend/app/services/loot_roll_presentation.py',
  'tbcc/backend/app/services/loot_roll_preview.py',
  'tbcc/backend/app/services/loot_tier_banner.py',
  'tbcc/backend/app/services/loot_tier_catalog.py',
  'tbcc/backend/app/api/loot.py',
  'tbcc/backend/app/workers/loot_promo_worker.py',
  'tbcc/backend/tests/test_loot_daily_promo.py',
  'tbcc/backend/tests/test_loot_operator_access.py',
  'tbcc/backend/tests/test_loot_tier_cards.py',
  'tbcc/backend/tests/test_zeus_menu.py',
  'tbcc/backend/tests/test_tbcc_operator_ids.py',
  'tbcc/assets/botfather',
  'tbcc/docs/loot-room-pinned-instructions.md',
  'tbcc/docs/ZEUS_MENU.md',
  'tbcc/docs/samples/gemini_loot_card_layout_lock.txt',
  'tbcc/docs/samples/gemini_loot_card_manual_prompts.txt',
  'tbcc/scripts/restore-loot-bot.ps1'
)

Commit-Slice 'feat(scrape): transport UI, channel metrics, and tag pool mapping' @(
  'tbcc/backend/alembic/versions/092_scrape_channel_metrics.py',
  'tbcc/backend/app/models/scrape_channel_profile.py',
  'tbcc/backend/app/services/scrape_channel_intel.py',
  'tbcc/backend/app/services/scrape_run_service.py',
  'tbcc/backend/app/services/scrape_tag_pool_map.py',
  'tbcc/backend/app/workers/scraper_worker.py',
  'tbcc/backend/bots/scraper_bot.py',
  'tbcc/backend/tests/test_scrape_tag_pool_map.py',
  'tbcc/backend/tests/test_scrape_transport.py',
  'tbcc/dashboard/src/components/ScrapeRunBanner.tsx',
  'tbcc/dashboard/src/components/ScrapeTransportBar.tsx',
  'tbcc/dashboard/src/components/SchedulerOnTrackCounter.tsx',
  'tbcc/dashboard/src/panels/Sources.tsx',
  'tbcc/dashboard/src/utils/scrapeTransportStatus.ts',
  'tbcc/dashboard/src/utils/scrapeTransportStatus.test.ts',
  'tbcc/dashboard/src/utils/schedulerHealthChipColors.ts',
  'tbcc/dashboard/src/utils/schedulerHealthChipColors.test.ts',
  'tbcc/extension/erome-transport-overlay.js'
)

Commit-Slice 'feat(remote-worker): GCP GHCR offload scripts and CI workflow' @(
  '.github/workflows/tbcc-remote-worker-ghcr.yml',
  'tbcc/infra/docker-compose.remote-worker.ghcr.yml',
  'tbcc/scripts/remote-worker',
  'tbcc/scripts/show-tbcc-remote-worker.ps1',
  'tbcc/docs/REMOTE_WORKER.md'
)

Commit-Slice 'feat(extension): erome enhancer, capture secret, username search, and gallery modules' @(
  'tbcc/extension',
  'tbcc/backend/app/api/extension_capture_secret.py',
  'tbcc/tools/register-tbcc-capture-secret-context-menu.ps1',
  'tbcc/tools/tbcc-capture-secret-context-menu.bat',
  'tbcc/tools/tbcc-capture-secret-context-menu.vbs',
  'tbcc/scripts/tbcc-capture-secret.ps1',
  'tbcc/scripts/tbcc-secret.ps1',
  'tbcc/scripts/tbcc-list-secrets.ps1'
)

Commit-Slice 'feat(growth): gemini promo, R2 upload, market intel, and buffer link order' @(
  'tbcc/backend/app/services/gemini_promo_prompt.py',
  'tbcc/backend/app/services/r2_promo_upload.py',
  'tbcc/backend/app/services/market_intel_cycle.py',
  'tbcc/backend/app/services/market_intel_cycle_executor.py',
  'tbcc/backend/app/services/buffer_x_link_order.py',
  'tbcc/backend/app/services/aof_packs_vocabulary.py',
  'tbcc/backend/app/data/aof_promo_scene_presets.json',
  'tbcc/backend/app/workers/market_intel_worker.py',
  'tbcc/backend/scripts/generate_aof_promo_gemini.py',
  'tbcc/backend/scripts/upload_x_promo_pool.py',
  'tbcc/backend/scripts/playwright_record.py',
  'tbcc/backend/tests/test_gemini_promo_prompt.py',
  'tbcc/backend/tests/test_r2_promo_upload.py',
  'tbcc/backend/tests/test_market_intel_cycle.py',
  'tbcc/backend/tests/test_buffer_x_link_order.py',
  'tbcc/backend/tests/test_aof_packs_vocabulary.py',
  'tbcc/docs/samples/gemini_aof_promo_layout_lock.txt',
  'tbcc/docs/samples/gemini_aof_promo_template.txt',
  'tbcc/docs/erome-enhancer/MARKET_INTEL_ARCHITECTURE.md',
  'tbcc/scripts/tbcc-playwright-record.ps1'
)

Commit-Slice 'feat(ops): env secret store, bot funnel analytics, and dashboard health panels' @(
  'tbcc/backend/app/services/tbcc_env_secret_store.py',
  'tbcc/backend/app/services/bot_funnel_analytics.py',
  'tbcc/backend/app/data/tbcc_env_secret_registry.json',
  'tbcc/backend/app/api/analytics.py',
  'tbcc/backend/tests/test_tbcc_env_secret_store.py',
  'tbcc/backend/tests/test_bot_funnel_analytics.py',
  'tbcc/backend/tests/test_service_user_enabled.py',
  'tbcc/dashboard/src/panels/BotAnalyticsPanel.tsx',
  'tbcc/dashboard/src/panels/Analytics.tsx',
  'tbcc/dashboard/src/components/SystemHealthBanner.tsx',
  'tbcc/dashboard/src/utils/severityToastColors.ts',
  'tbcc/dashboard/src/utils/severityToastColors.test.ts',
  'tbcc/dashboard/src/utils/alertToast.ts',
  'tbcc/extension/severity-toast-colors.js'
)

Commit-Slice 'feat(erome): upload governance, ingest analytics, and provision hardening' @(
  'tbcc/backend/app/services/erome_upload_governance.py',
  'tbcc/backend/app/services/erome_telegram_ingest.py',
  'tbcc/backend/app/services/erome_upload_analytics.py',
  'tbcc/backend/app/services/erome_upload_provision.py',
  'tbcc/backend/app/data/erome_upload_flow.json',
  'tbcc/backend/scripts/erome_codegen.py',
  'tbcc/backend/scripts/erome_upload_local.py',
  'tbcc/backend/tests/test_erome_upload_governance.py',
  'tbcc/backend/tests/test_erome_telegram_ingest.py'
)

Commit-Slice 'feat(userscripts): FetLife suite CI and monorepo workflow' @(
  '.github/workflows/tbcc-userscripts.yml',
  'tbcc/tools/fetlife-feed-story-filter.user.js',
  'stripchat-potplayer-userscript.user.js'
)

# Remaining tracked + untracked under tbcc (excluding .env)
$remaining = git status --porcelain | ForEach-Object { $_.Substring(3).Trim('"') } |
  Where-Object { $_ -and $_ -notmatch '(^|/)\.env$' -and $_ -notmatch '\.tbcc-run' -and $_ -notmatch '\.session' -and $_ -notmatch '__pycache__' -and $_ -notmatch '\.pytest_cache' }
if ($remaining) {
  git add -- @remaining
  $staged = git diff --cached --name-only
  if ($staged) {
    git commit -m 'feat: AOF growth hub, bots, dashboard, and stack misc (feat/loot-key-roll batch)'
    Write-Host "OK: remainder ($($staged.Count) files)"
  }
}

Write-Host '--- REMAINING ---'
git status --short
