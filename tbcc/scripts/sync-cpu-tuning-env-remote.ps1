# Push CPU/scheduling tuning keys from local tbcc/.env to a remote TBCC stack .env (VPS).
# Requires: OpenSSH, TBCC_REMOTE_STACK_HOST (+ optional TBCC_REMOTE_STACK_USER) in tbcc/.env
param(
  [string]$TbccRoot = "",
  [string]$RemoteHost = "",
  [string]$RemoteUser = "ubuntu",
  [string]$RemoteTbccPath = "/opt/tbcc"
)

$ErrorActionPreference = "Stop"
if (-not $TbccRoot) { $TbccRoot = Split-Path $PSScriptRoot -Parent }
$envPath = Join-Path $TbccRoot ".env"
if (-not (Test-Path -LiteralPath $envPath)) { throw "Missing $envPath" }

function Read-DotEnvMap {
  param([string]$Path)
  $map = @{}
  foreach ($line in Get-Content -LiteralPath $Path -ErrorAction Stop) {
    $t = $line.Trim()
    if (-not $t -or $t.StartsWith("#")) { continue }
    if ($t -match '^\s*([^=]+?)\s*=\s*(.*)$') {
      $map[$Matches[1].Trim()] = $Matches[2].Trim()
    }
  }
  return $map
}

$local = Read-DotEnvMap -Path $envPath
if (-not $RemoteHost) { $RemoteHost = ($local['TBCC_REMOTE_STACK_HOST'] -as [string]).Trim() }
if ($local['TBCC_REMOTE_STACK_USER']) { $RemoteUser = $local['TBCC_REMOTE_STACK_USER'].Trim() }
if ($local['TBCC_REMOTE_STACK_PATH']) { $RemoteTbccPath = $local['TBCC_REMOTE_STACK_PATH'].Trim() }

if (-not $RemoteHost) {
  Write-Error "Set TBCC_REMOTE_STACK_HOST in tbcc/.env or pass -RemoteHost (Tailscale/VPS IP)."
}

$keys = @(
  'TBCC_BEAT_SCHEDULE_MINUTES',
  'TBCC_UVICORN_RELOAD',
  'TBCC_WT_MONOLITH',
  'TBCC_BACKGROUND_SERVICE_START',
  'TBCC_EMOJI_FACTORY_ORPHAN_GRACE_MINUTES',
  'TBCC_WATCHDOG_FORCE_RESTART_STREAK',
  'TBCC_WATCHDOG_DRAIN_EMPTY_OVERDUE_MIN'
)

$lines = New-Object System.Collections.ArrayList
foreach ($k in $keys) {
  if ($local.ContainsKey($k) -and $local[$k]) {
    [void]$lines.Add("$k=$($local[$k])")
  }
}
if ($lines.Count -eq 0) { throw "No tuning keys found in local .env" }

$remoteEnv = "$RemoteTbccPath/.env"
# $remoteEnv is "$RemoteTbccPath/.env"; its parent is the remote path itself. Do NOT
# use Split-Path here -- on Windows it rewrites the Unix path with backslashes.
$remoteParent = $RemoteTbccPath
Write-Host "Patching $RemoteUser@${RemoteHost}:$remoteEnv with $($lines.Count) key(s)..."

# Build the space-separated, single-quoted key=value list bash will iterate.
$quotedList = (($lines | ForEach-Object { "'" + ($_ -replace "'", "'\''") + "'" }) -join ' ')

# Backtick-escape EVERY bash variable so PowerShell does not interpolate it. (The prior
# version wrote \${key}, which PowerShell expanded as an empty PS variable, leaving
# grep/sed patterns of "^=".) Only $remoteEnv / $remoteParent / $quotedList are meant
# to be substituted locally.
$remoteScript = @"
set -e
ENV='$remoteEnv'
mkdir -p '$remoteParent'
touch "`$ENV"
for line in $quotedList; do
  key="`${line%%=*}"
  if grep -q "^`${key}=" "`$ENV" 2>/dev/null; then
    sed -i "s|^`${key}=.*|`$line|" "`$ENV"
  else
    echo "`$line" >> "`$ENV"
  fi
done
echo 'Remote .env patched:'
grep -E '^(TBCC_BEAT|TBCC_UVICORN|TBCC_WT|TBCC_BACKGROUND|TBCC_EMOJI|TBCC_WATCHDOG)' "`$ENV" || true
"@

$remoteScript | ssh "${RemoteUser}@${RemoteHost}" "bash -s"
Write-Host "Done. Restart Beat + scheduling workers on the VPS (systemd/tray equivalent)."
