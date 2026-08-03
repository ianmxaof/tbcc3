# Test OpenRouter chat/completions (Venice free model).
# Usage:
#   cd path\to\tbcc\scripts
#   .\test-openrouter.ps1
# Or set key first:
#   $env:TBCC_OPENROUTER_API_KEY = "sk-or-v1-..."
#   .\test-openrouter.ps1

$ErrorActionPreference = "Stop"

function Read-DotEnvKey {
  param([string]$Path, [string]$Name)
  if (-not (Test-Path -LiteralPath $Path)) { return "" }
  foreach ($line in Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue) {
    $t = $line.Trim()
    if (-not $t -or $t.StartsWith("#")) { continue }
    if ($t -match "^\s*$([regex]::Escape($Name))\s*=\s*(.+)\s*$") {
      $v = $Matches[1].Trim()
      if ($v.StartsWith('"') -and $v.EndsWith('"') -and $v.Length -ge 2) {
        $v = $v.Substring(1, $v.Length - 2)
      }
      return $v
    }
  }
  return ""
}

$tbccRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $tbccRoot ".env"

$key = (
  $env:TBCC_OPENROUTER_API_KEY,
  $env:OPENROUTER_API_KEY,
  (Read-DotEnvKey -Path $envPath -Name "TBCC_OPENROUTER_API_KEY"),
  (Read-DotEnvKey -Path $envPath -Name "OPENROUTER_API_KEY")
) | Where-Object { $_ -and $_.Trim() } | Select-Object -First 1

if (-not $key -or $key.Length -lt 20 -or $key -eq "sk-or-v1-" -or $key -match "PASTE_YOUR") {
  Write-Host "No OpenRouter key found." -ForegroundColor Red
  if (Test-Path -LiteralPath $envPath) {
    $commented = Select-String -LiteralPath $envPath -Pattern '^\s*#\s*TBCC_OPENROUTER_API_KEY\s*=' -Quiet
    $active = Select-String -LiteralPath $envPath -Pattern '^\s*TBCC_OPENROUTER_API_KEY\s*=' -Quiet
    if ($commented -and -not $active) {
      Write-Host ""
      Write-Host "In $envPath the key line is still commented (# at the start)." -ForegroundColor Yellow
      Write-Host "Edit tbcc\.env: remove # before TBCC_OPENROUTER_API_KEY, paste your full sk-or-v1-... key, Save." -ForegroundColor Yellow
    }
  }
  Write-Host ""
  Write-Host "Or set for this PowerShell session only:"
  Write-Host '  $env:TBCC_OPENROUTER_API_KEY = "sk-or-v1-YOUR_FULL_KEY"'
  Write-Host "  .\test-openrouter.ps1"
  exit 1
}

$model = "cognitivecomputations/dolphin-mistral-24b-venice-edition"
$uri = "https://openrouter.ai/api/v1/chat/completions"

$headers = @{
  Authorization  = "Bearer $key"
  "Content-Type" = "application/json"
  "HTTP-Referer" = "https://obsidian.local"
  "X-Title"      = "Obsidian Test"
}

$body = @{
  model    = $model
  messages = @(
    @{ role = "user"; content = "Say hi in one word." }
  )
} | ConvertTo-Json -Depth 5 -Compress

Write-Host "POST $uri" -ForegroundColor Cyan
Write-Host "Model: $model" -ForegroundColor Gray

try {
  $resp = Invoke-RestMethod -Uri $uri -Method POST -Headers $headers -Body $body
  $text = $resp.choices[0].message.content
  Write-Host "OK - reply:" -ForegroundColor Green
  Write-Host $text
  exit 0
} catch {
  Write-Host "Request failed:" -ForegroundColor Red
  Write-Host $_.Exception.Message
  if ($_.ErrorDetails.Message) { Write-Host $_.ErrorDetails.Message }
  exit 1
}
