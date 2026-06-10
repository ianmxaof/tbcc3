# One-shot setup for TBCC enrichment sidecars (NSFW API + Lustpress).
# Run from tbcc/services:
#   .\setup-enrichment.ps1

$ErrorActionPreference = "Continue"
$here = $PSScriptRoot
$tbccDir = Split-Path $here -Parent

function Get-TbccPython {
  try {
    & py -3.13 -c "import sys" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { return "py -3.13" }
  } catch {}
  return "python"
}

function Get-BunPath {
  try {
    $c = Get-Command "bun" -ErrorAction Stop
    return $c.Source
  } catch {}
  $local = Join-Path $env:USERPROFILE ".bun\bin\bun.exe"
  if (Test-Path -LiteralPath $local) { return $local }
  return $null
}

Write-Host "TBCC enrichment setup" -ForegroundColor Cyan

$nsfwDir = Join-Path $here "NSFW_Detection_API"
if (-not (Test-Path (Join-Path $nsfwDir "requirements.txt"))) {
  Write-Host "Clone NSFW_Detection_API first:" -ForegroundColor Yellow
  Write-Host "  git clone https://github.com/TheHamkerCat/NSFW_Detection_API" -ForegroundColor Gray
} else {
  Write-Host "[1/3] NSFW Detection API - pip install..." -ForegroundColor Yellow
  Push-Location $nsfwDir
  $py = Get-TbccPython
  cmd /c ($py + " -m pip install -U -r requirements.txt")
  $pinFile = Join-Path $here "nsfw-detect-tbcc.txt"
  if (Test-Path -LiteralPath $pinFile) {
    cmd /c ($py + " -m pip install -U -r `"" + $pinFile + "`"")
  } else {
    cmd /c ($py + " -m pip install `"setuptools>=70,<81`"")
  }
  cmd /c ($py + " -c `"import os; os.environ['TF_USE_LEGACY_KERAS']='1'; from pkg_resources import parse_version; import tensorflow_hub; import tf_keras`"")
  if ($LASTEXITCODE -ne 0) {
    Write-Host "  NSFW deps check failed (setuptools/tensorflow-hub). See services/README.md" -ForegroundColor Red
  }
  Pop-Location
  Write-Host "  OK (launched via run_nsfw_detect.py on port 8001)" -ForegroundColor Green
}

$lustDir = Join-Path $here "lustpress"
if (-not (Test-Path (Join-Path $lustDir "package.json"))) {
  Write-Host "Clone lustpress first:" -ForegroundColor Yellow
  Write-Host "  git clone https://github.com/sinkaroid/lustpress" -ForegroundColor Gray
} else {
  $bun = Get-BunPath
  if (-not $bun) {
    Write-Host "[2/3] Bun not found - installing (official installer)..." -ForegroundColor Yellow
    Write-Host "  If this fails, run as Admin or install manually: https://bun.sh" -ForegroundColor Gray
    try {
      irm https://bun.sh/install.ps1 | iex
    } catch {
      Write-Host "  Bun install script failed: $_" -ForegroundColor Red
    }
    $bun = Get-BunPath
  }
  if ($bun) {
    Write-Host "[3/3] Lustpress - bun install..." -ForegroundColor Yellow
    Push-Location $lustDir
    & $bun install
    Pop-Location
    Write-Host "  OK (bun at $bun)" -ForegroundColor Green
  } else {
    Write-Host "[2/3] Install Bun, then re-run this script:" -ForegroundColor Red
    Write-Host "  powershell -c `"irm bun.sh/install.ps1 | iex`"" -ForegroundColor Yellow
    Write-Host "  Close and reopen PowerShell so bun is on PATH." -ForegroundColor Gray
  }
}

Write-Host ""
Write-Host "[CLIP] Local niche categorizer (OpenCLIP ViT-B/32)..." -ForegroundColor Yellow
$clipReq = Join-Path $here "clip-categorize-tbcc.txt"
if (Test-Path -LiteralPath $clipReq) {
  $py = Get-TbccPython
  cmd /c ($py + " -m pip install -U -r `"" + $clipReq + "`"")
  cmd /c ($py + " -c `"import open_clip; import torch; print('open_clip OK')`"")
  if ($LASTEXITCODE -eq 0) {
    Write-Host "  OK (run_clip_categorize.py on port 8002)" -ForegroundColor Green
    Write-Host "  Set TBCC_CLIP_CATEGORIES_FILE in tbcc/.env to your category catalog JSON/txt" -ForegroundColor Gray
  } else {
    Write-Host "  CLIP deps check failed (torch/open-clip). GPU optional; CPU works." -ForegroundColor Red
  }
} else {
  Write-Host "  clip-categorize-tbcc.txt not found — skip" -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host ('Next: cd ' + $tbccDir + '; .\start.ps1 -Full -WtTabs') -ForegroundColor Green
