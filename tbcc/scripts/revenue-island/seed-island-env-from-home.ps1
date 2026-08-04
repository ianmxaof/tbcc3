# Copy revenue-island keys from tbcc/.env into infra/.env.revenue-island (never prints values).
#   .\scripts\revenue-island\seed-island-env-from-home.ps1
# Then: sync -IncludeFilledEnv and recreate bot containers.

param(
  [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$tbccRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$homeEnv = Join-Path $tbccRoot ".env"
$islandEnv = Join-Path $tbccRoot "infra\.env.revenue-island"
$example = Join-Path $tbccRoot "infra\env.revenue-island.example"

if (-not (Test-Path -LiteralPath $homeEnv)) { throw "Missing $homeEnv" }

# Guard: a failed scp can balloon this file to gigabytes and OOM the seed step.
if (Test-Path -LiteralPath $islandEnv) {
  $envBytes = (Get-Item -LiteralPath $islandEnv).Length
  if ($envBytes -gt 512000) {
    Write-Host "WARN island env is $([math]::Round($envBytes/1MB,1)) MB - recreating from example (likely scp corruption)." -ForegroundColor Red
    Remove-Item -LiteralPath $islandEnv -Force
  }
}

if (-not (Test-Path -LiteralPath $islandEnv)) {
  if (-not (Test-Path -LiteralPath $example)) { throw "Missing example and island env" }
  Copy-Item $example $islandEnv
  Write-Host "Created island env from example." -ForegroundColor Yellow
}

function Read-DotEnvMap([string]$path) {
  $map = @{}
  foreach ($line in Get-Content -LiteralPath $path) {
    $t = $line.Trim()
    if (-not $t -or $t.StartsWith("#")) { continue }
    $i = $t.IndexOf("=")
    if ($i -lt 1) { continue }
    $k = $t.Substring(0, $i).Trim()
    $v = $t.Substring($i + 1).Trim()
    if (($v.StartsWith('"') -and $v.EndsWith('"')) -or ($v.StartsWith("'") -and $v.EndsWith("'"))) {
      $v = $v.Substring(1, $v.Length - 2)
    }
    $map[$k] = $v
  }
  return $map
}

function Set-DotEnvKey([string[]]$lines, [string]$key, [string]$value) {
  $out = New-Object System.Collections.Generic.List[string]
  $found = $false
  $escaped = $value
  # Keep plain KEY=value; quote if spaces/hashes
  if ($escaped -match '[\s#]') { $escaped = '"' + ($escaped -replace '"', '\"') + '"' }
  foreach ($line in $lines) {
    if ($line -match ("^\s*" + [regex]::Escape($key) + "\s*=")) {
      $out.Add("$key=$escaped")
      $found = $true
    } else {
      $out.Add($line)
    }
  }
  if (-not $found) { $out.Add("$key=$escaped") }
  return $out.ToArray()
}

# Avoid $home — PowerShell treats HOME as a read-only automatic/drive variable.
$homeMap = Read-DotEnvMap $homeEnv
$lines = @(Get-Content -LiteralPath $islandEnv)
$existingIsland = Read-DotEnvMap $islandEnv
$preserveWorkerImage = ($existingIsland["TBCC_WORKER_IMAGE"] -as [string]).Trim()

# Keys: islandKey = homeKey (or same name)
$copies = [ordered]@{
  "BOT_TOKEN"                 = "BOT_TOKEN"
  "TBCC_PAYMENT_BOT_USERNAME" = "TBCC_PAYMENT_BOT_USERNAME"
  "TBCC_LOOT_BOT_TOKEN"       = "TBCC_LOOT_BOT_TOKEN"
  "TBCC_ALBUM_COMPOSER_BOT_TOKEN" = "TBCC_ALBUM_COMPOSER_BOT_TOKEN"
  "TBCC_SECRETARY_BOT_TOKEN"  = "TBCC_SECRETARY_BOT_TOKEN"
  "TBCC_SECRETARY_BOT_USERNAME" = "TBCC_SECRETARY_BOT_USERNAME"
  "TBCC_COMPANION_BOT_TOKEN"  = "TBCC_COMPANION_BOT_TOKEN"
  "TBCC_COMPANION_BOT_USERNAME" = "TBCC_COMPANION_BOT_USERNAME"
  "TBCC_UNDRESS_TOOL_API_KEY" = "TBCC_UNDRESS_TOOL_API_KEY"
  "TBCC_UNDRESS_TOOL_BASE_URL" = "TBCC_UNDRESS_TOOL_BASE_URL"
  "TBCC_COMPANION_IMAGE_PROVIDER" = "TBCC_COMPANION_IMAGE_PROVIDER"
  "TBCC_COMPANION_FREE_TRIAL_PHOTOS" = "TBCC_COMPANION_FREE_TRIAL_PHOTOS"
  "TBCC_COMPANION_STARS_ENABLED" = "TBCC_COMPANION_STARS_ENABLED"
  "TBCC_COMPANION_STARS_PER_PHOTO" = "TBCC_COMPANION_STARS_PER_PHOTO"
  "TBCC_COMPANION_UNDRESS_USD_PER_CREDIT" = "TBCC_COMPANION_UNDRESS_USD_PER_CREDIT"
  "TBCC_COMPANION_UNDRESS_CREDITS_PER_PHOTO" = "TBCC_COMPANION_UNDRESS_CREDITS_PER_PHOTO"
  "TBCC_BUFFER_X_SPICY_BIAS_EVERY" = "TBCC_BUFFER_X_SPICY_BIAS_EVERY"
  "TBCC_COMPANION_GATE_ENABLED" = "TBCC_COMPANION_GATE_ENABLED"
  "TBCC_COMPANION_AFFILIATE_UNDRESS_URL" = "TBCC_COMPANION_AFFILIATE_UNDRESS_URL"
  "TBCC_AFFILIATE_UNDRESS_URL" = "TBCC_AFFILIATE_UNDRESS_URL"
  "TBCC_TRAFFIC_PULSE_ENABLED" = "TBCC_TRAFFIC_PULSE_ENABLED"
  "TBCC_TRAFFIC_PULSE_INSTANT" = "TBCC_TRAFFIC_PULSE_INSTANT"
  "TBCC_TRAFFIC_PULSE_INSTANT_HOURLY_CAP" = "TBCC_TRAFFIC_PULSE_INSTANT_HOURLY_CAP"
  "TBCC_TRAFFIC_PULSE_DIGEST_MIN" = "TBCC_TRAFFIC_PULSE_DIGEST_MIN"
  "TBCC_AFFILIATE_BEACON_WRAP" = "TBCC_AFFILIATE_BEACON_WRAP"
  "TBCC_LLM_CHAT_PROVIDER"    = "TBCC_LLM_CHAT_PROVIDER"
  "TBCC_LLM_BASE_URL"         = "TBCC_LLM_BASE_URL"
  "TBCC_OPENAI_BASE_URL"      = "TBCC_OPENAI_BASE_URL"
  "TBCC_LLM_API_KEY"          = "TBCC_LLM_API_KEY"
  "TBCC_OPENAI_API_KEY"       = "TBCC_OPENAI_API_KEY"
  "TBCC_LLM_PROVIDER"         = "TBCC_LLM_PROVIDER"
  "TBCC_OPENROUTER_API_KEY"   = "TBCC_OPENROUTER_API_KEY"
  "OPENROUTER_API_KEY"        = "OPENROUTER_API_KEY"
  "TBCC_OPENROUTER_BASE_URL"  = "TBCC_OPENROUTER_BASE_URL"
  "TBCC_OPENROUTER_MODEL"     = "TBCC_OPENROUTER_MODEL"
  "TBCC_SECRETARY_LLM_MODEL"  = "TBCC_SECRETARY_LLM_MODEL"
  "TBCC_LLM_MODEL"            = "TBCC_LLM_MODEL"
  "TBCC_LLM_CHAT_OPENAI_MODEL" = "TBCC_LLM_CHAT_OPENAI_MODEL"
  "TBCC_LLM_CHAT_MAX_TOKENS"  = "TBCC_LLM_CHAT_MAX_TOKENS"
  "TBCC_LLM_CHAT_TEMPERATURE" = "TBCC_LLM_CHAT_TEMPERATURE"
  "TBCC_COMPANION_SYSTEM_PROMPT" = "TBCC_COMPANION_SYSTEM_PROMPT"
  "TBCC_PUBLIC_API_BASE_URL"  = "TBCC_PUBLIC_API_BASE_URL"
  "TBCC_INTERNAL_API_KEY"     = "TBCC_INTERNAL_API_KEY"
  "TBCC_BYPASS_API_KEY"       = "TBCC_BYPASS_API_KEY"
  "API_ID"                    = "API_ID"
  "API_HASH"                  = "API_HASH"
  "ADMIN_TELEGRAM_ID"         = "ADMIN_TELEGRAM_ID"
  "TBCC_R2_ACCOUNT_ID"        = "TBCC_R2_ACCOUNT_ID"
  "TBCC_R2_BUCKET"            = "TBCC_R2_BUCKET"
  "TBCC_R2_PUBLIC_BASE_URL"   = "TBCC_R2_PUBLIC_BASE_URL"
  "TBCC_R2_S3_ENDPOINT"       = "TBCC_R2_S3_ENDPOINT"
  "TBCC_R2_ACCESS_KEY_ID"     = "TBCC_R2_ACCESS_KEY_ID"
  "TBCC_R2_SECRET_ACCESS_KEY" = "TBCC_R2_SECRET_ACCESS_KEY"
  "TBCC_X_PROMO_R2_BUCKET"              = "TBCC_X_PROMO_R2_BUCKET"
  "TBCC_X_PROMO_R2_PUBLIC_BASE_URL"     = "TBCC_X_PROMO_R2_PUBLIC_BASE_URL"
  "TBCC_X_PROMO_R2_PREFIX"              = "TBCC_X_PROMO_R2_PREFIX"
  "TBCC_BUFFER_X_PROMO_IMAGES"          = "TBCC_BUFFER_X_PROMO_IMAGES"
  "TBCC_ADMAVEN_API_TOKEN"       = "TBCC_ADMAVEN_API_TOKEN"
  "TBCC_ADMAVEN_LINK_TITLE"      = "TBCC_ADMAVEN_LINK_TITLE"
  "TBCC_PIXELDRAIN_API_KEY"      = "TBCC_PIXELDRAIN_API_KEY"
  "TBCC_LINKVERTISE_PUBLISHER_ID" = "TBCC_LINKVERTISE_PUBLISHER_ID"
  "TBCC_LINKVERTISE_BASE_URL"    = "TBCC_LINKVERTISE_BASE_URL"
  "TBCC_WORKINK_BASE_LINK"       = "TBCC_WORKINK_BASE_LINK"
  "TBCC_WORKINK_API_KEY"         = "TBCC_WORKINK_API_KEY"
  "TBCC_LINK_GATE_PROVIDERS"     = "TBCC_LINK_GATE_PROVIDERS"
  "TBCC_LINK_GATE_ROTATION"      = "TBCC_LINK_GATE_ROTATION"
  "TBCC_GUMROAD_CHECKOUT_ENABLED"   = "TBCC_GUMROAD_CHECKOUT_ENABLED"
  "TBCC_GUMROAD_SELLER_ID"          = "TBCC_GUMROAD_SELLER_ID"
  "TBCC_GUMROAD_PING_SELLER_ID"     = "TBCC_GUMROAD_PING_SELLER_ID"
  "TBCC_GUMROAD_PRODUCT_URL"        = "TBCC_GUMROAD_PRODUCT_URL"
  "TBCC_GUMROAD_VIP_OPTION_NAME"    = "TBCC_GUMROAD_VIP_OPTION_NAME"
  "TBCC_GUMROAD_VIP_EMBED_ROTATION" = "TBCC_GUMROAD_VIP_EMBED_ROTATION"
  "TBCC_GUMROAD_PRODUCT_MAP"        = "TBCC_GUMROAD_PRODUCT_MAP"
  "TBCC_DONATION_URL"               = "TBCC_DONATION_URL"
  "TBCC_NOWPAYMENTS_API_KEY"        = "TBCC_NOWPAYMENTS_API_KEY"
  "TBCC_NOWPAYMENTS_IPN_SECRET"     = "TBCC_NOWPAYMENTS_IPN_SECRET"
  "TBCC_NOWPAYMENTS_PAY_CURRENCY"   = "TBCC_NOWPAYMENTS_PAY_CURRENCY"
  "TBCC_NOWPAYMENTS_MIN_CHECKOUT_USD" = "TBCC_NOWPAYMENTS_MIN_CHECKOUT_USD"
  "TBCC_NOWPAYMENTS_USE_INVOICE"    = "TBCC_NOWPAYMENTS_USE_INVOICE"
  "TBCC_STARS_USD_PER_STAR"         = "TBCC_STARS_USD_PER_STAR"
  "TBCC_AOF_VIP_CHANNEL_IDENT"              = "TBCC_AOF_VIP_CHANNEL_IDENT"
  "TBCC_AOF_VIP_INVITE_URL"                 = "TBCC_AOF_VIP_INVITE_URL"
  "TBCC_AOF_VIP_SUBSCRIPTION_INVITE_URL"    = "TBCC_AOF_VIP_SUBSCRIPTION_INVITE_URL"
  "TBCC_CHECKOUT_USE_VIP_STAR_SUBSCRIPTION" = "TBCC_CHECKOUT_USE_VIP_STAR_SUBSCRIPTION"
  "TBCC_AOF_VIP_EARLY_DROP_ENABLED"         = "TBCC_AOF_VIP_EARLY_DROP_ENABLED"
  "TBCC_AOF_VIP_MIRROR_ENABLED"             = "TBCC_AOF_VIP_MIRROR_ENABLED"
  "TBCC_REVENUE_ISLAND_ACTIVE"              = "TBCC_REVENUE_ISLAND_ACTIVE"
  "TBCC_EXPORT_FLYWHEEL_ENABLED"            = "TBCC_EXPORT_FLYWHEEL_ENABLED"
  "TBCC_EXPORT_FLYWHEEL_MODE"                 = "TBCC_EXPORT_FLYWHEEL_MODE"
  "TBCC_EXPORT_FLYWHEEL_RANK_PICKS"         = "TBCC_EXPORT_FLYWHEEL_RANK_PICKS"
  "TBCC_EXPORT_FLYWHEEL_TICK_MINUTES"       = "TBCC_EXPORT_FLYWHEEL_TICK_MINUTES"
  "TBCC_EXPORT_FLYWHEEL_DAILY_CAP_PER_LANE" = "TBCC_EXPORT_FLYWHEEL_DAILY_CAP_PER_LANE"
  "TBCC_EXPORT_FLYWHEEL_REQUIRE_MIN_VIEWS_SAMPLE" = "TBCC_EXPORT_FLYWHEEL_REQUIRE_MIN_VIEWS_SAMPLE"
  "TBCC_WATERMARK_TEXT"                     = "TBCC_WATERMARK_TEXT"
  "TBCC_WATERMARK_TEXT_SECONDARY"           = "TBCC_WATERMARK_TEXT_SECONDARY"
  "TBCC_WATERMARK_TEXT_TERTIARY"            = "TBCC_WATERMARK_TEXT_TERTIARY"
  "TBCC_BUFFER_API_KEY"                     = "TBCC_BUFFER_API_KEY"
  "TBCC_BUFFER_ORGANIZATION_ID"             = "TBCC_BUFFER_ORGANIZATION_ID"
  "TBCC_BUFFER_CHANNEL_ID_PRIMARY"          = "TBCC_BUFFER_CHANNEL_ID_PRIMARY"
  "TBCC_BUFFER_CHANNEL_ID_X_SECONDARY"      = "TBCC_BUFFER_CHANNEL_ID_X_SECONDARY"
  "TBCC_BUFFER_CHANNEL_IDS"                 = "TBCC_BUFFER_CHANNEL_IDS"
  "TBCC_BUFFER_X_AFFILIATE_FIRST"           = "TBCC_BUFFER_X_AFFILIATE_FIRST"
  "TBCC_BUFFER_X_LINK_CYCLE"                = "TBCC_BUFFER_X_LINK_CYCLE"
  "TBCC_LOOT_BUFFER_PUBLISH_NOW"            = "TBCC_LOOT_BUFFER_PUBLISH_NOW"
  "TBCC_BUFFER_ARMORY_STARTUP_REFILL"       = "TBCC_BUFFER_ARMORY_STARTUP_REFILL"
  "TBCC_BUFFER_ARMORY_REFILL_HOURS"         = "TBCC_BUFFER_ARMORY_REFILL_HOURS"
  "TBCC_BUFFER_NATIVE_MIN_DEPTH"            = "TBCC_BUFFER_NATIVE_MIN_DEPTH"
  "TBCC_BUFFER_NATIVE_MAX_SCHEDULED"        = "TBCC_BUFFER_NATIVE_MAX_SCHEDULED"
  "TBCC_BUFFER_ARMORY_MAX_DEPTH"            = "TBCC_BUFFER_ARMORY_MAX_DEPTH"
  "TBCC_BUFFER_X_COPY_ROTATION_CATEGORIES"  = "TBCC_BUFFER_X_COPY_ROTATION_CATEGORIES"
  "TBCC_CREATIVE_GEN_ENABLED"               = "TBCC_CREATIVE_GEN_ENABLED"
  "TBCC_CREATIVE_GEN_PROVIDER"              = "TBCC_CREATIVE_GEN_PROVIDER"
  "TBCC_GEMINI_API_KEY"                     = "TBCC_GEMINI_API_KEY"
  "GEMINI_API_KEY"                          = "GEMINI_API_KEY"
  "TBCC_GEMINI_IMAGE_MODEL"                 = "TBCC_GEMINI_IMAGE_MODEL"
  "TBCC_SALE_ANNOUNCE_ENABLED"              = "TBCC_SALE_ANNOUNCE_ENABLED"
  "TBCC_SALE_ANNOUNCE_TARGETS"              = "TBCC_SALE_ANNOUNCE_TARGETS"
  "TBCC_SALE_ANNOUNCE_BUFFER_MODE"          = "TBCC_SALE_ANNOUNCE_BUFFER_MODE"
  "TBCC_SALE_ANNOUNCE_MIN_INTERVAL_S"       = "TBCC_SALE_ANNOUNCE_MIN_INTERVAL_S"
  "TBCC_SALE_ANNOUNCE_STAGGER_S"            = "TBCC_SALE_ANNOUNCE_STAGGER_S"
  "TBCC_SALE_ANNOUNCE_SKIP_KEYS"            = "TBCC_SALE_ANNOUNCE_SKIP_KEYS"
  "TBCC_POOL_BUFFER_MIRROR"                 = "TBCC_POOL_BUFFER_MIRROR"
  "TBCC_STARS_BAIT_DM_ENABLED"              = "TBCC_STARS_BAIT_DM_ENABLED"
  "TBCC_STARS_BAIT_DM_BATCH"                = "TBCC_STARS_BAIT_DM_BATCH"
  "TBCC_STARS_BAIT_DM_INTERVAL_MIN"         = "TBCC_STARS_BAIT_DM_INTERVAL_MIN"
  "TBCC_STARS_BAIT_CHANNEL_INTERVAL_MIN"    = "TBCC_STARS_BAIT_CHANNEL_INTERVAL_MIN"
  "TBCC_FIAT_CHECKOUT_BUTTON_LABEL"         = "TBCC_FIAT_CHECKOUT_BUTTON_LABEL"
  "TBCC_FIAT_CHECKOUT_DISPLAY_NAME"         = "TBCC_FIAT_CHECKOUT_DISPLAY_NAME"
  "TBCC_FIAT_OPEN_PAY_BUTTON_LABEL"         = "TBCC_FIAT_OPEN_PAY_BUTTON_LABEL"
  "TBCC_KIT_CAPTURE_ENABLED"                = "TBCC_KIT_CAPTURE_ENABLED"
  "TBCC_KIT_API_SECRET"                     = "TBCC_KIT_API_SECRET"
  "TBCC_KIT_PURCHASE_TAG_ID"                = "TBCC_KIT_PURCHASE_TAG_ID"
  "TBCC_CLICK_BEACON_NOTIFY"                = "TBCC_CLICK_BEACON_NOTIFY"
  "TBCC_CLICK_BEACON_INSTANT"               = "TBCC_CLICK_BEACON_INSTANT"
  "TBCC_CLICK_BEACON_NOTIFY_BOTS"           = "TBCC_CLICK_BEACON_NOTIFY_BOTS"
}

# Companion LLM: default custom when a proxy base URL is set on home
if ([string]::IsNullOrWhiteSpace($homeMap["TBCC_LLM_CHAT_PROVIDER"])) {
  $proxyBase = ($homeMap["TBCC_LLM_BASE_URL"] -as [string]).Trim()
  if ([string]::IsNullOrWhiteSpace($proxyBase)) {
    $proxyBase = ($homeMap["TBCC_OPENAI_BASE_URL"] -as [string]).Trim()
  }
  if ($proxyBase) {
    $homeMap["TBCC_LLM_CHAT_PROVIDER"] = "custom"
    if ([string]::IsNullOrWhiteSpace($homeMap["TBCC_LLM_BASE_URL"])) {
      $homeMap["TBCC_LLM_BASE_URL"] = $proxyBase
    }
  }
}

# Prefer loot token aliases used at home
if (-not $homeMap["TBCC_LOOT_BOT_TOKEN"] -and $homeMap["LOOT_BOT_TOKEN"]) {
  $homeMap["TBCC_LOOT_BOT_TOKEN"] = $homeMap["LOOT_BOT_TOKEN"]
}

# Pixeldrain: dated capture-secret keys → canonical
if ([string]::IsNullOrWhiteSpace($homeMap["TBCC_PIXELDRAIN_API_KEY"])) {
  if (-not [string]::IsNullOrWhiteSpace($homeMap["TBCC_PD"])) {
    $homeMap["TBCC_PIXELDRAIN_API_KEY"] = $homeMap["TBCC_PD"]
  } elseif (-not [string]::IsNullOrWhiteSpace($homeMap["PIXELDRAIN_API_KEY_071726"])) {
    $homeMap["TBCC_PIXELDRAIN_API_KEY"] = $homeMap["PIXELDRAIN_API_KEY_071726"]
  } else {
    foreach ($k in @($homeMap.Keys)) {
      if ($k -match '^PIXELDRAIN_API_KEY' -and -not [string]::IsNullOrWhiteSpace($homeMap[$k])) {
        $homeMap["TBCC_PIXELDRAIN_API_KEY"] = $homeMap[$k]
        break
      }
    }
  }
}

# Gate order default for island flywheel (LV first)
if ([string]::IsNullOrWhiteSpace($homeMap["TBCC_LINK_GATE_PROVIDERS"])) {
  $homeMap["TBCC_LINK_GATE_PROVIDERS"] = "linkvertise,admaven,workink"
}
if ([string]::IsNullOrWhiteSpace($homeMap["TBCC_LINK_GATE_ROTATION"])) {
  $homeMap["TBCC_LINK_GATE_ROTATION"] = "first"
}

$copied = 0
$missing = @()
foreach ($islandKey in $copies.Keys) {
  $homeKey = $copies[$islandKey]
  $val = $homeMap[$homeKey]
  if ([string]::IsNullOrWhiteSpace($val)) {
    $missing += $homeKey
    continue
  }
  $lines = Set-DotEnvKey $lines $islandKey $val
  $copied++
  Write-Host ("OK  {0} ({1} chars from home {2})" -f $islandKey, $val.Length, $homeKey) -ForegroundColor Green
}

# Keep island-local compose URLs unless already customized
$forceKeep = @{
  "TBCC_API_URL"             = "http://api:8000"
  "REDIS_URL"                = "redis://redis:6379/0"
  "POSTGRES_DB"              = "tbcc"
  "POSTGRES_USER"            = "postgres"
  "TBCC_LINK_GATE_PROVIDERS" = "linkvertise,admaven,workink"
  "TBCC_LINK_GATE_ROTATION"  = "first"
  "TBCC_SCRAPE_HUB_FIRST"    = "1"
  "TBCC_SCRAPE_MICRO_PULL_ENABLED" = "1"
  "TBCC_SCRAPE_MICRO_PULL_MODE"    = "firehose"
  "TBCC_INTAKE_SCHEDULER_ENABLED"  = "1"
  "TBCC_INBOX_INTAKE_ENABLED"      = "1"
  "TBCC_PAYMENT_STORAGE_DEPOSIT"   = "0"
  "TBCC_PAYMENT_STORAGE_HUB"       = "0"
  "TBCC_ALBUM_COMPOSER_STORAGE_DEPOSIT" = "1"
  "TBCC_ALBUM_COMPOSER_STORAGE_HUB"    = "1"
  "TBCC_SCRAPE_MICRO_PULL_LIMIT"   = "10"
  "TBCC_SCRAPE_MICRO_PULL_DEDUPE"  = "1"
  "TBCC_GATEKEEPER_REVIEW_BOT"     = "album_composer"
  "TBCC_GATEKEEPER_REVIEW_COPY_MEDIA" = "1"
  "TBCC_GATEKEEPER_REVIEW_THREAD_ID" = "1"
  "TBCC_GATEKEEPER_LANE_PICKER"    = "1"
  "TBCC_STORAGE_AUTO_PIPE_ENABLED" = "1"
  "TBCC_STORAGE_AUTO_PIPE_DEBOUNCE_S" = "90"
  "TBCC_REVIEW_BATCH_SIZE"         = "10"
  "TBCC_GATEKEEPER_HUB_AUTO_APPROVE" = "1"
  "TBCC_GATEKEEPER_HUB_AUTO_APPROVE_MIN" = "70"
  "TBCC_GATEKEEPER_HUB_REQUIRE_LANE_DETECT" = "1"
  "TBCC_GATEKEEPER_APPROVE_MICRO_PULL" = "1"
  "TBCC_LOOT_DAILY_PULL_ENABLED"     = "1"
  "TBCC_LOOT_REVEAL_VIDEO"             = "1"
  "TBCC_LOOT_BORDER_REVEAL"            = "1"
  "TBCC_RELAY_USE_BOT_API"             = "1"
}
foreach ($k in $forceKeep.Keys) {
  $lines = Set-DotEnvKey $lines $k $forceKeep[$k]
}

# Public API URL: never copy home ngrok — island tunnel or explicit override only.
$islandPublic = ""
if ($homeMap.ContainsKey("TBCC_ISLAND_API_PUBLIC_URL") -and $homeMap["TBCC_ISLAND_API_PUBLIC_URL"]) {
  $islandPublic = $homeMap["TBCC_ISLAND_API_PUBLIC_URL"].Trim()
}
if (-not $islandPublic) {
  $cand = ""
  if ($homeMap.ContainsKey("TBCC_PUBLIC_API_BASE_URL") -and $homeMap["TBCC_PUBLIC_API_BASE_URL"]) {
    $cand = $homeMap["TBCC_PUBLIC_API_BASE_URL"].Trim().TrimEnd("/")
  }
  if ($cand -and $cand.StartsWith("https://") -and $cand -notmatch "ngrok") {
    $islandPublic = $cand
  }
}
if (-not $islandPublic) {
  $islandPublic = "https://api.powercore.app"
}
if ($islandPublic) {
  $lines = Set-DotEnvKey $lines "TBCC_PUBLIC_API_BASE_URL" $islandPublic
  $lines = Set-DotEnvKey $lines "TBCC_API_PUBLIC_URL" $islandPublic
  $lines = Set-DotEnvKey $lines "TBCC_PROMO_PUBLIC_BASE_URL" $islandPublic
  $lines = Set-DotEnvKey $lines "TBCC_CLICK_BEACON_PUBLIC_BASE" $islandPublic
  Write-Host ("OK  TBCC_PUBLIC_API_BASE_URL + TBCC_API_PUBLIC_URL + TBCC_PROMO_PUBLIC_BASE_URL + TBCC_CLICK_BEACON_PUBLIC_BASE ({0} chars)" -f $islandPublic.Length) -ForegroundColor Green
} else {
  Write-Host "SKIP TBCC_PUBLIC_API_BASE_URL - set TBCC_ISLAND_API_PUBLIC_URL on home or run install-island-api-tunnel.sh on VPS." -ForegroundColor Yellow
}

if ($preserveWorkerImage -and $preserveWorkerImage -notmatch ":latest$") {
  $lines = Set-DotEnvKey $lines "TBCC_WORKER_IMAGE" $preserveWorkerImage
  Write-Host ("OK  TBCC_WORKER_IMAGE (preserved {0})" -f $preserveWorkerImage) -ForegroundColor Green
}

# If POSTGRES_PASSWORD still placeholder, leave DB alone (restore already used change-me-strong).
# Optional: set a strong password later with a controlled rotate.

if ($WhatIf) {
  Write-Host "WhatIf: not writing file." -ForegroundColor Yellow
  exit 0
}

$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($islandEnv, $lines, $utf8)

Write-Host ""
Write-Host ('Wrote {0} ({1} keys from home).' -f $islandEnv, $copied) -ForegroundColor Cyan
if ($missing.Count) {
  Write-Host ("Missing on home .env (skipped): {0}" -f ($missing -join ", ")) -ForegroundColor Yellow
}
Write-Host "Next:" -ForegroundColor Cyan
Write-Host "  .\scripts\revenue-island\sync-island-files.ps1 -HostName root@5.161.53.91 -IncludeFilledEnv"
Write-Host '  ssh root@5.161.53.91 "cd /opt/tbcc/infra; docker compose ... up -d --force-recreate payment_bot loot_bot"'
