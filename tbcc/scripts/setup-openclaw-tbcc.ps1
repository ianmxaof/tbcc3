# Wire github.com/openclaw/openclaw to TBCC MCP + copy operator skill
param(
  [string]$TbccRoot = "",
  [switch]$SkipMcpAdd
)

$ErrorActionPreference = "Stop"
if (-not $TbccRoot) {
  $TbccRoot = Split-Path $PSScriptRoot -Parent
}
$repoRoot = Split-Path $TbccRoot -Parent
$mcpScript = Join-Path $TbccRoot "mcp-server\server.py"
$skillSrc = Join-Path $TbccRoot "docs\openclaw-skill"
$skillNames = @("tbcc-aof-network", "tbcc-failure-modes")

Write-Host "=== OpenClaw + TBCC setup ===" -ForegroundColor Cyan
Write-Host "Repo: $repoRoot" -ForegroundColor Gray

# 1. OpenClaw CLI
try {
  $ver = openclaw --version 2>&1
  Write-Host "OpenClaw: $ver" -ForegroundColor Green
} catch {
  Write-Host "Install OpenClaw: npm install -g openclaw@latest && openclaw onboard --install-daemon" -ForegroundColor Red
  exit 1
}

# 2. MCP server
if (-not (Test-Path -LiteralPath $mcpScript)) {
  Write-Host "Missing MCP server: $mcpScript" -ForegroundColor Red
  exit 1
}

if (-not $SkipMcpAdd) {
  Write-Host "`nRegistering TBCC MCP via mcporter..." -ForegroundColor Yellow
  if (-not (Get-Command mcporter -ErrorAction SilentlyContinue)) {
    Write-Host "  Installing mcporter..." -ForegroundColor DarkYellow
    npm install -g mcporter | Out-Null
  }
  $mcpPath = $mcpScript -replace '\\', '/'
  $tbccCwd = ($TbccRoot -replace '\\', '/')
  $ocConfigDir = Join-Path $env:USERPROFILE ".openclaw\config"
  $mcporterCfg = Join-Path $ocConfigDir "mcporter.json"
  New-Item -ItemType Directory -Force -Path $ocConfigDir | Out-Null
  if (-not (Test-Path -LiteralPath $mcporterCfg)) {
    '{"mcpServers":{}}' | Set-Content -LiteralPath $mcporterCfg -Encoding utf8
  }
  mcporter config remove tbcc --persist $mcporterCfg 2>$null | Out-Null
  mcporter config add tbcc `
    --command py `
    --arg -3.13 `
    --arg $mcpPath `
    --env "TBCC_API_URL=http://127.0.0.1:8000" `
    --persist $mcporterCfg
  mcporter list tbcc --schema --config $mcporterCfg | Select-Object -First 5 | Out-Host
  # OpenClaw agent cwd defaults to ~/.openclaw workspace; mcporter reads ./config/mcporter.json
  $ws = $null
  try {
    $ws = openclaw config get agents.defaults.workspace 2>$null
  } catch { }
  if (-not $ws) { $ws = Join-Path $env:USERPROFILE "clawd" }
  $wsCfg = Join-Path $ws "config"
  New-Item -ItemType Directory -Force -Path $wsCfg | Out-Null
  Copy-Item -Force $mcporterCfg (Join-Path $wsCfg "mcporter.json")
  Write-Host "  OK tbcc MCP (23 tools)" -ForegroundColor Green
}

# 3. Skills
Write-Host "`nInstalling OpenClaw skills..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path (Join-Path $env:USERPROFILE ".openclaw\workspace\skills") | Out-Null
foreach ($name in $skillNames) {
  $src = Join-Path $skillSrc $name
  $dst = Join-Path $env:USERPROFILE ".openclaw\workspace\skills\$name"
  if (-not (Test-Path -LiteralPath $src)) {
    Write-Host "  SKIP missing $name" -ForegroundColor DarkYellow
    continue
  }
  Copy-Item -Recurse -Force $src $dst
  Write-Host "  OK $name" -ForegroundColor Green
}

# 4. TBCC health
Write-Host "`nProbing TBCC API..." -ForegroundColor Yellow
try {
  $h = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 8
  Write-Host "  TBCC backend up" -ForegroundColor Green
} catch {
  Write-Host "  Start TBCC backend first (tbcc/start.ps1 or supervisor)" -ForegroundColor DarkYellow
}

Write-Host "`n=== Next steps ===" -ForegroundColor Cyan
Write-Host "1. BotFather: create NEW bot for OpenClaw (not secretary)"
Write-Host "2. openclaw config set channels.telegram.botToken YOUR_NEW_TOKEN"
Write-Host "3. openclaw gateway restart  (or restart daemon from tray)"
Write-Host "4. DM the new bot, then: openclaw pairing approve telegram CODE"
Write-Host "5. Add OpenClaw cron - see tbcc/docs/OPENCLAW_TBCC_INTEGRATION.md"
Write-Host "6. Test: mcporter call tbcc.tbcc_health"
Write-Host "7. Test agent: openclaw agent --message 'Run tbcc_health via mcporter'"
