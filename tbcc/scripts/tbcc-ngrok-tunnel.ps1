# Ensure ngrok is running and .env public URLs match the live tunnel (companion webhooks, promo static, NOWPayments IPN).
#   . .\scripts\tbcc-ngrok-tunnel.ps1
#   Ensure-TbccNgrokTunnel -TbccRoot $tbccDir -EnvMap $dotEnv -FullStack:$fullStack

function Get-TbccConfiguredPublicBases {
  param([hashtable]$EnvMap)
  $bases = New-Object System.Collections.Generic.List[string]
  foreach ($key in @('TBCC_PUBLIC_API_BASE_URL', 'TBCC_PROMO_PUBLIC_BASE_URL')) {
    $raw = ($EnvMap[$key] -as [string])
    if (-not $raw) { continue }
    $u = $raw.Trim().TrimEnd('/')
    if ($u) { [void]$bases.Add($u) }
  }
  return [string[]]($bases | Select-Object -Unique)
}

function Test-TbccPublicBaseIsLocalhost {
  param([string]$Url)
  if (-not $Url) { return $true }
  try {
    $h = ([Uri]$Url).Host.ToLower()
    return ($h -eq '127.0.0.1' -or $h -eq 'localhost')
  } catch {
    return $true
  }
}

function Test-TbccNgrokHostname {
  param([string]$Url)
  if (-not $Url) { return $false }
  try {
    $h = ([Uri]$Url).Host.ToLower()
    return ($h -like '*.ngrok-free.app' -or $h -like '*.ngrok.app' -or $h -like '*.ngrok.io' -or $h -like '*.ngrok.dev')
  } catch {
    return $false
  }
}

function Test-TbccNgrokTunnelRequired {
  param(
    [hashtable]$EnvMap,
    [bool]$FullStack = $false
  )
  if (($EnvMap['TBCC_SKIP_NGROK'] -as [string]).Trim() -eq '1') { return $false }
  foreach ($base in (Get-TbccConfiguredPublicBases -EnvMap $EnvMap)) {
    if (-not (Test-TbccPublicBaseIsLocalhost -Url $base)) { return $true }
  }
  if ($FullStack) { return $true }
  return $false
}

function Get-TbccNgrokLocalHttpsUrl {
  param([int]$MaxWaitSec = 0)
  $deadline = (Get-Date).AddSeconds($MaxWaitSec)
  do {
    try {
      $resp = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 3 -ErrorAction Stop
      foreach ($t in $resp.tunnels) {
        if ($t.public_url -and $t.public_url -like 'https://*') {
          return $t.public_url.TrimEnd('/')
        }
      }
    } catch {}
    if ($MaxWaitSec -le 0) { return $null }
    Start-Sleep -Seconds 1
  } while ((Get-Date) -lt $deadline)
  return $null
}

function Test-TbccNgrokLocalApiUp {
  return $null -ne (Get-TbccNgrokLocalHttpsUrl -MaxWaitSec 0)
}

function Test-TbccPublicBaseReachable {
  param(
    [Parameter(Mandatory = $true)][string]$BaseUrl,
    [double]$TimeoutSec = 10
  )
  $base = $BaseUrl.Trim().TrimEnd('/')
  if (-not $base) { return @{ ok = $false; detail = 'empty URL' } }
  $probe = $base + '/webhooks/companion/undress'
  $headers = @{
    'ngrok-skip-browser-warning' = '1'
    'Content-Type'               = 'application/json'
  }
  $body = '{"id_gen":"healthcheck","status":"ping"}'
  try {
    $resp = Invoke-WebRequest -Uri $probe -Method POST -Headers $headers -Body $body -UseBasicParsing -TimeoutSec $TimeoutSec -ErrorAction Stop
    $ct = ($resp.Headers['Content-Type'] -as [string]).ToLower()
    if ($resp.Content -match 'ERR_NGROK|endpoint .+ is offline') {
      return @{ ok = $false; detail = 'ngrok endpoint offline' }
    }
    if ($ct -like '*text/html*' -and $resp.StatusCode -ge 400) {
      return @{ ok = $false; detail = 'public URL returned HTML error (tunnel down?)' }
    }
    return @{ ok = $true; detail = 'reachable' }
  } catch {
    $detail = $_.Exception.Message
    try {
      if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $text = $reader.ReadToEnd()
        $reader.Close()
        if ($text -match 'ERR_NGROK|endpoint .+ is offline') {
          return @{ ok = $false; detail = 'ngrok endpoint offline' }
        }
        if ($text -match 'text/html|<html') {
          return @{ ok = $false; detail = 'public URL returned HTML error (tunnel down?)' }
        }
        if ($text) { $detail = $text.Substring(0, [Math]::Min(120, $text.Length)) }
      }
    } catch {}
    return @{ ok = $false; detail = $detail }
  }
}

function Set-TbccDotEnvKey {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Key,
    [Parameter(Mandatory = $true)][string]$Value
  )
  if (-not (Test-Path -LiteralPath $Path)) {
    throw "Missing file: $Path"
  }
  $raw = [System.IO.File]::ReadAllText($Path)
  $pattern = '(?m)^\s*#?\s*' + [regex]::Escape($Key) + '=.*$'
  if ($raw -match $pattern) {
    $raw = $raw -replace $pattern, ($Key + '=' + $Value)
  } else {
    $nl = "`r`n"
    if (-not $raw.EndsWith("`n")) { $raw += $nl }
    $raw += $Key + '=' + $Value + $nl
  }
  [System.IO.File]::WriteAllText($Path, $raw)
}

function Start-TbccNgrokProcess {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [int]$Port = 8000,
    [scriptblock]$StartCmdWindow = $null
  )
  if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
    return @{ ok = $false; detail = 'ngrok not found in PATH (https://ngrok.com/download)' }
  }
  $cmd = 'ngrok http ' + $Port
  if ($StartCmdWindow) {
    $null = $StartCmdWindow.Invoke('TBCC-ngrok', $cmd)
  } else {
    $run = 'title "TBCC-ngrok" && ' + $cmd
    Start-Process -FilePath $env:ComSpec -ArgumentList @('/k', $run) -WindowStyle Normal
  }
  Start-Sleep -Seconds 2
  return @{ ok = $true; detail = 'started' }
}

function Ensure-TbccNgrokTunnel {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][hashtable]$EnvMap,
    [bool]$FullStack = $false,
    [int]$Port = 8000,
    [scriptblock]$StartCmdWindow = $null
  )

  $result = @{
    ok          = $true
    skipped     = $false
    started     = $false
    updatedEnv  = $false
    publicUrl   = $null
    messages    = (New-Object System.Collections.ArrayList)
  }

  if (-not (Test-TbccNgrokTunnelRequired -EnvMap $EnvMap -FullStack:$FullStack)) {
    $result.skipped = $true
    [void]$result.messages.Add('No public tunnel required (localhost URLs and not -Full).')
    return $result
  }

  if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
    $result.ok = $false
    [void]$result.messages.Add('ngrok not in PATH — install it and run: ngrok config add-authtoken YOUR_TOKEN')
    return $result
  }

  $envFile = Join-Path $TbccRoot '.env'
  $configured = Get-TbccConfiguredPublicBases -EnvMap $EnvMap
  $configuredNgrok = @($configured | Where-Object { Test-TbccNgrokHostname -Url $_ })
  $liveUrl = Get-TbccNgrokLocalHttpsUrl -MaxWaitSec 0
  $needNgrokUrl = $false
  $allCustomReachable = $true

  if ($configured.Count -eq 0) {
    $needNgrokUrl = $true
    [void]$result.messages.Add('No TBCC_PUBLIC_* URL in .env — will ensure ngrok and write .env.')
  } else {
    foreach ($base in $configured) {
      if (Test-TbccPublicBaseIsLocalhost -Url $base) { continue }
      $reach = Test-TbccPublicBaseReachable -BaseUrl $base
      if ($reach.ok) { continue }
      if (Test-TbccNgrokHostname -Url $base) {
        $needNgrokUrl = $true
        [void]$result.messages.Add(('Stale/offline ngrok URL in .env: ' + $base + ' (' + $reach.detail + ')'))
      } else {
        $allCustomReachable = $false
        [void]$result.messages.Add(('Public URL not reachable (not ngrok — fix manually): ' + $base))
      }
    }
  }

  if (-not $needNgrokUrl -and $liveUrl) {
    foreach ($base in $configuredNgrok) {
      if ($base -ne $liveUrl) {
        $needNgrokUrl = $true
        [void]$result.messages.Add(('Local ngrok ' + $liveUrl + ' differs from .env — will sync .env.'))
        break
      }
    }
  }

  if (-not $needNgrokUrl) {
    if ($liveUrl) {
      [void]$result.messages.Add(('Public tunnel OK: ' + $liveUrl))
    } elseif ($allCustomReachable -and $configured.Count -gt 0) {
      [void]$result.messages.Add('Public URLs reachable; no local ngrok on :4040 (remote/custom host).')
    }
    return $result
  }

  if (-not $liveUrl) {
    [void]$result.messages.Add('Starting ngrok http ' + $Port + ' (new window)...')
    $start = Start-TbccNgrokProcess -TbccRoot $TbccRoot -Port $Port -StartCmdWindow $StartCmdWindow
    if (-not $start.ok) {
      $result.ok = $false
      [void]$result.messages.Add($start.detail)
      return $result
    }
    $result.started = $true
    $liveUrl = Get-TbccNgrokLocalHttpsUrl -MaxWaitSec 90
  }

  if (-not $liveUrl) {
    $result.ok = $false
    [void]$result.messages.Add('Could not read https URL from http://127.0.0.1:4040/api/tunnels — check TBCC-ngrok window.')
    return $result
  }

  $result.publicUrl = $liveUrl
  $apiBase = ($EnvMap['TBCC_PUBLIC_API_BASE_URL'] -as [string]).Trim().TrimEnd('/')
  $promoBase = ($EnvMap['TBCC_PROMO_PUBLIC_BASE_URL'] -as [string]).Trim().TrimEnd('/')
  if ($apiBase -ne $liveUrl -or $promoBase -ne $liveUrl) {
    Set-TbccDotEnvKey -Path $envFile -Key 'TBCC_PUBLIC_API_BASE_URL' -Value $liveUrl
    Set-TbccDotEnvKey -Path $envFile -Key 'TBCC_PROMO_PUBLIC_BASE_URL' -Value $liveUrl
    $result.updatedEnv = $true
    [void]$result.messages.Add('Updated TBCC_PUBLIC_API_BASE_URL and TBCC_PROMO_PUBLIC_BASE_URL in .env.')
  } else {
    [void]$result.messages.Add(('ngrok OK: ' + $liveUrl))
  }

  return $result
}
