# Kill TBCC stray one-shot processes (OCI bootstrap, orphan emoji-factory httpx clients, etc.).
param(
  [string]$TbccRoot = "",
  [switch]$DryRun
)

$ErrorActionPreference = "Continue"
if (-not $TbccRoot) { $TbccRoot = Split-Path $PSScriptRoot -Parent }

function Read-TbccStrayDotEnv {
  param([string]$Path)
  $out = @{}
  if (-not (Test-Path -LiteralPath $Path)) { return $out }
  foreach ($line in Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue) {
    $t = $line.Trim()
    if (-not $t -or $t.StartsWith("#")) { continue }
    if ($t -match '^\s*([^=]+?)\s*=\s*(.*)$') {
      $out[$Matches[1].Trim()] = $Matches[2].Trim().Trim('"').Trim("'")
    }
  }
  return $out
}

function Get-TbccStrayGraceMinutes {
  param([hashtable]$DotEnv)
  $raw = ($DotEnv['TBCC_EMOJI_FACTORY_ORPHAN_GRACE_MINUTES'] -as [string]).Trim()
  if (-not $raw) { return 15 }
  try { return [Math]::Max(1, [Math]::Min(120, [int]$raw)) } catch { return 15 }
}

function Test-TbccProtectedStrayProcess {
  param($Process, $TbccRoot)
  $cmd = [string]$Process.CommandLine
  if (-not $cmd) { return $true }
  if ($cmd -match 'tbcc-supervisor\.ps1|run-tbcc-stackwatch\.ps1|run-tbcc-orchestrator\.ps1|tbcc-kill-stray-processes\.ps1') {
    return $true
  }
  if ($cmd -match 'emoji_factory_worker|process_emoji_factory_job|/emoji-factory/create-from-upload') {
    return $true
  }
  if ($cmd -match 'run-tbcc-service\.ps1|tbcc-service-control\.ps1') { return $true }
  return $false
}

function Test-TbccStrayProcessMatch {
  param([string]$CommandLine)
  if (-not $CommandLine) { return $false }
  if ($CommandLine -match 'bootstrap-oci-instance|tbcc-bootstrap-oci-launch') { return $true }
  if ($CommandLine -match 'python\.exe\s+-c\s+.*httpx.*emoji-factory') { return $true }
  if ($CommandLine -match 'python\.exe\s+-c\s+.*127\.0\.0\.1:8000/emoji-factory') { return $true }
  if ($CommandLine -match 'Python314\\python\.exe\s+-c\s+.*httpx') { return $true }
  return $false
}

$dotEnv = Read-TbccStrayDotEnv -Path (Join-Path $TbccRoot ".env")
$graceMin = Get-TbccStrayGraceMinutes -DotEnv $dotEnv
$cutoff = (Get-Date).AddMinutes(-1 * $graceMin)

$killed = @()
$skipped = @()
$all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)

foreach ($proc in $all) {
  $cmd = [string]$proc.CommandLine
  if (-not (Test-TbccStrayProcessMatch -CommandLine $cmd)) { continue }
  if (Test-TbccProtectedStrayProcess -Process $proc -TbccRoot $TbccRoot) { continue }
  $created = $null
  try { $created = $proc.CreationDate } catch {}
  if ($created -and $created -gt $cutoff) {
    $skipped += [pscustomobject]@{ Pid = [int]$proc.ProcessId; Reason = "younger_than_${graceMin}m"; Cmd = $cmd.Substring(0, [Math]::Min(100, $cmd.Length)) }
    continue
  }
  if ($DryRun) {
    $killed += [pscustomobject]@{ Pid = [int]$proc.ProcessId; DryRun = $true; Cmd = $cmd.Substring(0, [Math]::Min(100, $cmd.Length)) }
    continue
  }
  try {
    Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
    $killed += [pscustomobject]@{ Pid = [int]$proc.ProcessId; Cmd = $cmd.Substring(0, [Math]::Min(100, $cmd.Length)) }
  } catch {
    $skipped += [pscustomobject]@{ Pid = [int]$proc.ProcessId; Reason = $_.Exception.Message; Cmd = $cmd.Substring(0, [Math]::Min(100, $cmd.Length)) }
  }
}

@{
  ok = $true
  graceMinutes = $graceMin
  killed = @($killed)
  skipped = @($skipped)
  killedCount = $killed.Count
} | ConvertTo-Json -Depth 4 -Compress
