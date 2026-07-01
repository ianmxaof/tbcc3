# Configure OpenClaw cron jobs for TBCC ops + growth Telegram reports.
param(
  [string]$TbccRoot = "",
  [string]$TelegramUserId = "",
  [string]$CronModel = "openai-codex/gpt-5.2",
  [switch]$SkipSkillSync
)

$ErrorActionPreference = "Stop"
if (-not $TbccRoot) {
  $TbccRoot = Split-Path $PSScriptRoot -Parent
}

$control = Join-Path $TbccRoot "scripts\tbcc-service-control.ps1"
if (Test-Path -LiteralPath $control) {
  . $control
}

function Read-TbccEnvValue {
  param([string]$Path, [string]$Key)
  if (-not (Test-Path -LiteralPath $Path)) { return $null }
  foreach ($line in Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue) {
    $t = $line.Trim()
    if (-not $t -or $t.StartsWith("#")) { continue }
    if ($t -match "^\s*$([regex]::Escape($Key))\s*=") {
      return ($t -split "=", 2)[1].Trim()
    }
  }
  return $null
}

$envPath = Join-Path $TbccRoot ".env"
if (-not $TelegramUserId) {
  $TelegramUserId = Read-TbccEnvValue -Path $envPath -Key "ADMIN_TELEGRAM_ID"
}
if (-not $TelegramUserId) {
  Write-Host "Set ADMIN_TELEGRAM_ID in tbcc/.env or pass -TelegramUserId" -ForegroundColor Red
  exit 1
}

Write-Host "=== OpenClaw growth + ops cron ===" -ForegroundColor Cyan
Write-Host "Telegram deliver to: $TelegramUserId" -ForegroundColor Gray
Write-Host "Cron model: $CronModel" -ForegroundColor Gray

if (-not $SkipSkillSync) {
  $sync = Join-Path $TbccRoot "scripts\sync-openclaw-skills.ps1"
  if (Test-Path -LiteralPath $sync) {
    Write-Host "`nSyncing OpenClaw skills..." -ForegroundColor Yellow
    & powershell -NoProfile -ExecutionPolicy Bypass -File $sync
  }
}

$cronDir = Join-Path $env:USERPROFILE ".openclaw\cron"
$jobsPath = Join-Path $cronDir "jobs.json"
if (-not (Test-Path -LiteralPath $cronDir)) {
  New-Item -ItemType Directory -Force -Path $cronDir | Out-Null
}

$nowMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()

$opsMessage = @(
  "TBCC ops turn (skill: tbcc-aof-network): mcporter call tbcc.tbcc_health, tbcc.tbcc_flywheel_tick ops_limit=1, tbcc.flywheel_approval_bundle."
  "If pending_count>0, send ONE short summary only. Never flywheel_approve without my explicit OK."
  "If API or mcporter fails, report briefly and stop."
) -join " "

$growthMessage = @(
  "TBCC growth report (skill: tbcc-growth-signals): FIRST mcporter call tbcc.growth_signals_eligibility."
  "If eligible=false, reply ONE line with the reason and STOP (no tick, no proposals, save tokens)."
  "If eligible=true: mcporter call tbcc.analytics_content_performance run_tick=true days=14."
  "If digest_changed is true, also call tbcc.growth_signal_proposals days=14 and list each pending proposal id + action_kind."
  "Deliver full markdown + 2-sentence executive summary. Never create posts, schedules, deposit, or act on a proposal without my OK."
) -join " "

function New-CronJob {
  param(
    [string]$Id,
    [string]$Name,
    [string]$Description,
    [int]$EveryMinutes,
    [string]$Message
  )
  return [ordered]@{
    id             = $Id
    name           = $Name
    description    = $Description
    enabled        = $true
    deleteAfterRun = $false
    createdAtMs    = $nowMs
    updatedAtMs    = $nowMs
    schedule       = @{
      kind    = "every"
      everyMs = $EveryMinutes * 60 * 1000
    }
    sessionTarget = "isolated"
    wakeMode      = "next-heartbeat"
    payload       = @{
      kind               = "agentTurn"
      message            = $Message
      thinking           = "minimal"
      timeoutSeconds     = 180
      deliver            = $true
      channel            = "telegram"
      to                 = $TelegramUserId
      bestEffortDeliver  = $true
      model              = $CronModel
    }
    isolation     = @{
      postToMainPrefix  = "Cron"
      postToMainMode    = "summary"
      postToMainMaxChars = 8000
    }
    state         = @{
      nextRunAtMs = $nowMs + ($EveryMinutes * 60 * 1000)
    }
  }
}

$opsId = "f1d2e8fa-6590-4e1c-887a-f858515fdf9c"
$growthId = "a8c3b1e2-4f5d-6e7a-9b0c-1d2e3f4a5b6c"

$jobsDoc = @{
  version = 1
  jobs    = @(
    (New-CronJob -Id $opsId -Name "tbcc-ops-check" -Description "TBCC health + flywheel poll every 20m" -EveryMinutes 20 -Message $opsMessage),
    (New-CronJob -Id $growthId -Name "tbcc-growth-report" -Description "TBCC growth signals + recommendations every 30m" -EveryMinutes 30 -Message $growthMessage)
  )
}

if (Test-Path -LiteralPath $jobsPath) {
  Copy-Item -Force $jobsPath (Join-Path $cronDir "jobs.json.bak")
}

($jobsDoc | ConvertTo-Json -Depth 12) | Set-Content -LiteralPath $jobsPath -Encoding utf8
Write-Host "`nWrote cron jobs:" -ForegroundColor Green
Write-Host "  tbcc-ops-check     every 20m" -ForegroundColor Green
Write-Host "  tbcc-growth-report every 30m" -ForegroundColor Green

# Prefer Codex for cron if OpenRouter model was failing
$ocPath = Join-Path $env:USERPROFILE ".openclaw\openclaw.json"
if (Test-Path -LiteralPath $ocPath) {
  try {
    $oc = Get-Content -LiteralPath $ocPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($oc.agents.defaults.model.primary -match "openrouter/anthropic/claude-sonnet-4-5") {
      $oc.agents.defaults.model.primary = $CronModel
      if (-not $oc.agents.defaults.models.PSObject.Properties[$CronModel]) {
        $oc.agents.defaults.models | Add-Member -NotePropertyName $CronModel -NotePropertyValue @{} -Force
      }
      Copy-Item -Force $ocPath ($ocPath + ".bak")
      ($oc | ConvertTo-Json -Depth 20) | Set-Content -LiteralPath $ocPath -Encoding utf8
      Write-Host "  Updated OpenClaw default model -> $CronModel" -ForegroundColor Yellow
    }
  } catch {
    Write-Host "  (Could not patch openclaw.json model - edit manually if cron still errors)" -ForegroundColor DarkYellow
  }
}

Write-Host "`n=== Next ===" -ForegroundColor Cyan
Write-Host "1. Lean stack: TBCC_STACK_PROFILE=lean is set - restart via tray Start - lean or:"
Write-Host "   . tbcc\scripts\tbcc-service-control.ps1; Invoke-TbccLeanStackLaunch -TbccRoot `"$TbccRoot`""
Write-Host "2. Ensure OpenClaw gateway tab is up (TBCC_OPENCLAW_AUTO_START=1)"
Write-Host "3. Test growth MCP: mcporter call tbcc.analytics_content_performance run_tick=true"
Write-Host "4. Cron list: openclaw cron list (after gateway restart picks up jobs.json)"
