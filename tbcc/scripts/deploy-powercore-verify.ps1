# Deploy minimal powercore.app static site (BonusArrive verify + landing).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy-powercore-verify.ps1

$ErrorActionPreference = "Stop"
$tbccRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$siteDir = Join-Path $tbccRoot "static\powercore-verify"

if (-not (Test-Path (Join-Path $siteDir "bonusarrive-verify-a3048e.txt"))) {
  Write-Error "Missing verify file in $siteDir"
}

Write-Host "=== Deploy powercore.app verify site ===" -ForegroundColor Cyan
Write-Host "Directory: $siteDir" -ForegroundColor DarkGray

Push-Location $siteDir
try {
  if (-not (Test-Path "node_modules\wrangler")) {
    Write-Host "Installing wrangler..." -ForegroundColor Yellow
    npm install --no-fund --no-audit
  }

  Write-Host "Checking Cloudflare auth..." -ForegroundColor Yellow
  $whoami = npx wrangler whoami 2>&1 | Out-String
  if ($whoami -match "not authenticated|Please run `wrangler login`") {
    Write-Host $whoami -ForegroundColor Yellow
    Write-Host "Wrangler not logged in. Use Cloudflare Worker route (already deployed via API) or run: npx wrangler login" -ForegroundColor Yellow
    exit 1
  }
  Write-Host $whoami

  Write-Host "Deploying to Cloudflare Pages (project: powercore-app)..." -ForegroundColor Yellow
  npx wrangler pages deploy . --project-name=powercore-app --branch=main

  Write-Host ""
  Write-Host "Next steps:" -ForegroundColor Green
  Write-Host "  1. Cloudflare Dashboard -> Workers & Pages -> powercore-app -> Custom domains -> add powercore.app"
  Write-Host "  2. curl https://powercore.app/bonusarrive-verify-a3048e.txt"
  Write-Host "  3. BonusArrive -> Verify"
} finally {
  Pop-Location
}
