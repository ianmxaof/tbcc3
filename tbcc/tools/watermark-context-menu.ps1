# Explorer context-menu launcher for TBCC local watermark burn-in.
param(
  [ValidateSet("file", "folder")]
  [string]$Mode = "file",
  [string[]]$PathArgs = @()
)

$ErrorActionPreference = "Stop"
$toolsDir = $PSScriptRoot
$backendDir = Join-Path (Split-Path $toolsDir -Parent) "backend"
$script = Join-Path $backendDir "scripts\watermark_local.py"

function Show-Message {
  param([string]$Text, [string]$Title = "TBCC Watermark", [string]$Kind = "Warning")
  if (-not ("PresentationFramework" -as [type])) {
    Add-Type -AssemblyName PresentationFramework
  }
  $icon = switch ($Kind) {
    "Error" { "Error" }
    default { "Warning" }
  }
  [System.Windows.MessageBox]::Show($Text, $Title, "OK", $icon) | Out-Null
}

if (-not (Test-Path -LiteralPath $script)) {
  Show-Message "Missing watermark script:`n$script" -Kind Error
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

Push-Location $backendDir
try {
  if ($Mode -eq "folder") {
    $invokeArgs = @($pyPrefix + @($script, "apply", $paths[0], "--notify"))
  } else {
    $invokeArgs = @($pyPrefix + @($script, "apply", "--files") + $paths + @("--notify"))
  }
  & $py @invokeArgs
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
