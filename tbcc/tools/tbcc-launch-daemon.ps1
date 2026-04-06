# TBCC local launch helper for the browser extension.
# Listens on http://127.0.0.1:8765 and runs ..\start.ps1 -Full when POST /launch-full is received.
# Run once (leave window open) or register a scheduled task to start at logon.
#
#   cd tbcc\tools
#   .\tbcc-launch-daemon.ps1

$ErrorActionPreference = "Stop"
$toolsDir = $PSScriptRoot
$tbccDir = Split-Path -Parent $toolsDir
$startPs1 = Join-Path $tbccDir "start.ps1"
$prefix = "http://127.0.0.1:8765/"
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add($prefix)

if (-not (Test-Path -LiteralPath $startPs1)) {
  Write-Host "Cannot find start.ps1 at: $startPs1" -ForegroundColor Red
  exit 1
}

function Send-CorsJson {
  param(
    [Parameter(Mandatory = $true)] $Response,
    [int]$Status = 200,
    [string]$Body = '{"ok":true}'
  )
  $Response.StatusCode = $Status
  $Response.Headers.Add("Access-Control-Allow-Origin", "*")
  $Response.Headers.Add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
  $Response.Headers.Add("Access-Control-Allow-Headers", "Content-Type")
  $Response.ContentType = "application/json; charset=utf-8"
  $buf = [System.Text.Encoding]::UTF8.GetBytes($Body)
  $Response.ContentLength64 = $buf.Length
  $Response.OutputStream.Write($buf, 0, $buf.Length)
}

$script:lastLaunch = [DateTime]::MinValue
function Invoke-FullLaunch {
  $now = [DateTime]::UtcNow
  if (($now - $script:lastLaunch).TotalSeconds -lt 4) {
    return @{ ok = $false; error = "debounced"; detail = "Launch ignored (wait a few seconds between clicks)." }
  }
  $script:lastLaunch = $now
  Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $startPs1, "-Full"
  ) -WorkingDirectory $tbccDir -WindowStyle Normal
  return @{ ok = $true; via = "daemon"; path = $startPs1 }
}

try {
  $listener.Start()
} catch {
  Write-Host "Failed to bind $prefix — port 8765 may be in use or URL ACL missing." -ForegroundColor Red
  Write-Host $_
  exit 1
}

Write-Host "TBCC launch daemon on $prefix" -ForegroundColor Cyan
Write-Host "  POST /launch-full  -> start.ps1 -Full" -ForegroundColor Gray
Write-Host "  GET  /health       -> status JSON" -ForegroundColor Gray
Write-Host "Press Ctrl+C to stop." -ForegroundColor Gray
Write-Host ""

while ($listener.IsListening) {
  try {
    $ctx = $listener.GetContext()
  } catch {
    break
  }
  $req = $ctx.Request
  $res = $ctx.Response
  $path = ($req.Url.AbsolutePath.TrimEnd("/") -replace "^$", "/")
  if ($path -eq "") { $path = "/" }

  try {
    if ($req.HttpMethod -eq "OPTIONS") {
      $res.StatusCode = 204
      $res.Headers.Add("Access-Control-Allow-Origin", "*")
      $res.Headers.Add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
      $res.Headers.Add("Access-Control-Allow-Headers", "Content-Type")
      $res.ContentLength64 = 0
    }
    elseif ($req.HttpMethod -eq "GET" -and ($path -eq "/health" -or $path -eq "/")) {
      Send-CorsJson -Response $res -Body ('{"ok":true,"service":"tbcc-launch-daemon"}')
    }
    elseif ($req.HttpMethod -eq "POST" -and $path -eq "/launch-full") {
      $result = Invoke-FullLaunch
      $json = $result | ConvertTo-Json -Compress -Depth 5
      if ($result.ok) {
        Send-CorsJson -Response $res -Body $json
      } else {
        Send-CorsJson -Response $res -Status 429 -Body $json
      }
    }
    else {
      Send-CorsJson -Response $res -Status 404 -Body '{"ok":false,"error":"not_found"}'
    }
  } finally {
    $res.Close()
  }
}

$listener.Stop()
$listener.Close()
