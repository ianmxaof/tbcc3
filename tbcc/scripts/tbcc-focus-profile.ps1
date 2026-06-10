# Apply or restore TBCC focus profiles (stop/start optional services — never backend/celery).
param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("off", "import_burst", "telegram_relief", "watch_folder", "minimal")]
  [string]$Profile,
  [Parameter(Mandatory = $true)]
  [ValidateSet("apply", "restore")]
  [string]$Action,
  [string]$TbccRoot = ""
)

$ErrorActionPreference = "Continue"
if (-not $TbccRoot) {
  $TbccRoot = Split-Path $PSScriptRoot -Parent
}
$controlScript = Join-Path $TbccRoot "scripts\tbcc-service-control.ps1"
if (-not (Test-Path -LiteralPath $controlScript)) {
  @{ ok = $false; error = "missing tbcc-service-control.ps1" } | ConvertTo-Json -Compress
  exit 1
}
. $controlScript

# Beat is never stopped — Python scheduler_worker honors pause_beat via Redis focus flags.
$stopMap = @{
  import_burst     = @("nsfw", "clip", "lustpress", "payment", "secretary", "macro_search", "loot", "album_composer")
  telegram_relief  = @("nsfw", "clip", "lustpress")
  watch_folder     = @("payment", "secretary", "macro_search", "loot", "album_composer")
  minimal          = @("nsfw", "clip", "lustpress", "payment", "secretary", "macro_search", "loot", "album_composer", "forum")
  off              = @()
}

function Get-TbccFocusServiceById {
  param([string]$Id)
  @(Get-TbccStackServices -TbccRoot $TbccRoot -FullStack) | Where-Object { $_.Id -eq $Id } | Select-Object -First 1
}

$results = @()
if ($Action -eq "apply") {
  $ids = $stopMap[$Profile]
  if (-not $ids) {
    @{ ok = $false; error = "unknown profile" } | ConvertTo-Json -Compress
    exit 1
  }
  foreach ($id in $ids) {
    if ($id -in @("backend", "celery", "dashboard")) { continue }
    $svc = Get-TbccFocusServiceById -Id $id
    if (-not $svc) { continue }
    if (Test-TbccServiceProcessRunning -Service $svc) {
      $killed = @(Stop-TbccStackService -Service $svc -TbccRoot $TbccRoot)
      $results += @{ action = "stop"; id = $id; title = $svc.Title; killed = $killed.Count }
    } else {
      $results += @{ action = "skip"; id = $id; title = $svc.Title; note = "already down" }
    }
  }
} else {
  $restoreIds = @()
  if ($Profile -eq "off") {
    $restoreIds = @(
      "beat", "nsfw", "clip", "lustpress", "payment", "secretary",
      "macro_search", "loot", "album_composer", "forum"
    )
  }
  foreach ($id in $restoreIds) {
    $svc = Get-TbccFocusServiceById -Id $id
    if (-not $svc) { continue }
    if (-not (Test-TbccServiceProcessRunning -Service $svc)) {
      try {
        Start-TbccStackService -Service $svc -TbccRoot $TbccRoot -UseErrorHubWrapper
        $results += @{ action = "start"; id = $id; title = $svc.Title; ok = $true }
      } catch {
        $results += @{ action = "start"; id = $id; title = $svc.Title; ok = $false; error = $_.Exception.Message }
      }
    } else {
      $results += @{ action = "skip"; id = $id; title = $svc.Title; note = "already up" }
    }
  }
}

@{ ok = $true; profile = $Profile; action = $Action; results = $results } | ConvertTo-Json -Compress -Depth 5
