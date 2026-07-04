# Explorer context-menu launcher — watermark (optional) + hardened Erome upload.
param(
  [ValidateSet("file", "folder")]
  [string]$Mode = "file",
  [string[]]$PathArgs = @()
)

$ErrorActionPreference = "Stop"
$toolsDir = $PSScriptRoot
$backendDir = Join-Path (Split-Path $toolsDir -Parent) "backend"
$uploadScript = Join-Path $backendDir "scripts\erome_upload_local.py"
$watermarkScript = Join-Path $backendDir "scripts\watermark_local.py"

function Show-Message {
  param([string]$Text, [string]$Title = "TBCC Erome Upload", [string]$Kind = "Warning")
  if (-not ("PresentationFramework" -as [type])) {
    Add-Type -AssemblyName PresentationFramework
  }
  $icon = switch ($Kind) {
    "Error" { "Error" }
    default { "Warning" }
  }
  [System.Windows.MessageBox]::Show($Text, $Title, "OK", $icon) | Out-Null
}

if (-not (Test-Path -LiteralPath $uploadScript)) {
  Show-Message "Missing upload script:`n$uploadScript" -Kind Error
  exit 1
}

$paths = @($PathArgs | Where-Object { $_ -and $_.Trim() })
if ($paths.Count -eq 0) {
  Show-Message "No files or folder selected."
  exit 1
}

function Resolve-Python {
  foreach ($name in @("py", "python")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
  }
  return "py"
}

$py = Resolve-Python
$pyPrefix = @()
if ($py -match "py(\.exe)?$") {
  $pyPrefix = @("-3.13")
}

$targetFolder = $null
if ($Mode -eq "folder") {
  $targetFolder = $paths[0]
} else {
  $targetFolder = Split-Path -Parent $paths[0]
}

if (-not (Test-Path -LiteralPath $targetFolder)) {
  Show-Message "Could not resolve staging folder." -Kind Error
  exit 1
}

$sidecar = Join-Path $targetFolder "erome.params.json"
if (-not (Test-Path -LiteralPath $sidecar)) {
  Show-Message @(
    "No erome.params.json in this folder.",
    "",
    "Create one beside your media (see tbcc/backend/app/data/erome.params.example.json):",
    "  title, tags, content_notes, network_key",
    "",
    "Folder:",
    $targetFolder
  ) -join "`n"
  exit 1
}

Push-Location $backendDir
try {
  if ($Mode -eq "file" -and (Test-Path -LiteralPath $watermarkScript)) {
    $wmArgs = @($pyPrefix + @($watermarkScript, "apply", "--files") + $paths)
    & $py @wmArgs
    if ($LASTEXITCODE -ne 0) {
      Show-Message "Watermark step failed (exit $LASTEXITCODE). Upload aborted." -Kind Error
      exit $LASTEXITCODE
    }
  }

  $upArgs = @(
    $pyPrefix + @(
      $uploadScript,
      "--execute",
      "--path", $targetFolder,
      "--source", "context_menu",
      "--save-archive"
    )
  )
  & $py @upArgs
  $code = $LASTEXITCODE
  if ($code -eq 3) {
    Show-Message "Upload blocked by Erome policy (rate limit / duplicate title / daily cap).`nCheck tbcc/run/erome-analytics/upload_ledger.jsonl" -Kind Warning
  } elseif ($code -ne 0) {
    Show-Message "Erome upload failed (exit $code). See terminal log if TBCC supervisor is open." -Kind Error
  }
  exit $code
} finally {
  Pop-Location
}
