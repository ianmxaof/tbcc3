# TBCC unified error hub — shared by run-tbcc-service.ps1 and show-tbcc-error-hub.ps1
# Do not run directly; dot-source from sibling scripts.

$script:TbccErrorHubMutexName = "Global\TbccErrorHubLog"
$script:TbccErrorHubMaxLineLen = 480
$script:TbccErrorHubMaxTraceLines = 40

function Get-TbccErrorHubPaths {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $runDir = Join-Path $TbccRoot ".tbcc-run"
  $launchers = Join-Path $runDir "launchers"
  $log = Join-Path $runDir "error-hub.log"
  return @{ RunDir = $runDir; LaunchersDir = $launchers; LogPath = $log }
}

function Initialize-TbccErrorHub {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $paths = Get-TbccErrorHubPaths -TbccRoot $TbccRoot
  New-Item -ItemType Directory -Force -Path $paths.LaunchersDir | Out-Null
  $header = @(
    "================================================================================"
    ("TBCC Error Hub session started {0:yyyy-MM-dd HH:mm:ss}" -f (Get-Date))
    ("Log: {0}" -f $paths.LogPath)
    "Services pipe stderr/stdout here when started via .\start.ps1 -WtTabs (or -WtTabs -Full)."
    "================================================================================"
  ) -join [Environment]::NewLine
  Set-Content -LiteralPath $paths.LogPath -Value $header -Encoding UTF8
  return $paths
}

function Register-TbccServiceLauncher {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][string]$ServiceName,
    [Parameter(Mandatory = $true)][string]$Command
  )
  $paths = Get-TbccErrorHubPaths -TbccRoot $TbccRoot
  New-Item -ItemType Directory -Force -Path $paths.LaunchersDir | Out-Null
  $safeName = ($ServiceName -replace '[^\w\-]', '_')
  $file = Join-Path $paths.LaunchersDir ($safeName + ".json")
  $payload = @{ service = $ServiceName; command = $Command }
  ($payload | ConvertTo-Json -Compress) | Set-Content -LiteralPath $file -Encoding UTF8
  return $file
}

function Get-TbccServiceWrapperCmd {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][string]$ServiceName
  )
  $runner = Join-Path $TbccRoot "scripts\run-tbcc-service.ps1"
  $tbccQ = '"' + $TbccRoot + '"'
  $svcQ = '"' + $ServiceName + '"'
  $runQ = '"' + $runner + '"'
  return ('powershell -NoProfile -ExecutionPolicy Bypass -File ' + $runQ + ' -TbccRoot ' + $tbccQ + ' -ServiceName ' + $svcQ)
}

function Get-TbccErrorMonitorCmd {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $monitor = Join-Path $TbccRoot "scripts\show-tbcc-error-hub.ps1"
  $tbccQ = '"' + $TbccRoot + '"'
  $monQ = '"' + $monitor + '"'
  return ('powershell -NoProfile -ExecutionPolicy Bypass -File ' + $monQ + ' -TbccRoot ' + $tbccQ)
}

function Format-TbccHubLine {
  param([string]$Text, [int]$MaxLen = $script:TbccErrorHubMaxLineLen)
  if (-not $Text) { return "" }
  $one = ($Text -replace "[\r\n]+", " ").Trim()
  if ($one.Length -le $MaxLen) { return $one }
  return $one.Substring(0, $MaxLen) + " ...."
}

function Write-TbccErrorHubEntry {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][string]$ServiceName,
    [Parameter(Mandatory = $true)][string]$Level,
    [Parameter(Mandatory = $true)][string]$Message,
    [string]$Hint = ""
  )
  $paths = Get-TbccErrorHubPaths -TbccRoot $TbccRoot
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
  $body = Format-TbccHubLine -Text $Message
  if (-not $body) { return }
  $line = "[{0}] [{1}] [{2}] {3}" -f $ts, $ServiceName, $Level, $body
  if ($Hint) {
    $line += "  -> " + (Format-TbccHubLine -Text $Hint -MaxLen 120)
  }

  $mutex = New-Object System.Threading.Mutex($false, $script:TbccErrorHubMutexName)
  try {
    $null = $mutex.WaitOne(15000)
    Add-Content -LiteralPath $paths.LogPath -Value $line -Encoding UTF8
  } finally {
    if ($mutex) {
      try { $mutex.ReleaseMutex() } catch {}
      $mutex.Dispose()
    }
  }
}

function Test-TbccBenignHubLine {
  param([string]$Line)
  if (-not $Line) { return $true }
  $t = $Line.Trim()
  if (-not $t) { return $true }

  $benign = @(
    '^\[notice\]',
    'new release of pip is available',
    'To update, run:.*pip install --upgrade pip',
    'pkg_resources is deprecated',
    '\bUserWarning:\s*pkg_resources',
    'absl::InitializeLog\(\)',
    'All log messages before absl::InitializeLog',
    'WARNING:tensorflow:',
    'WARNING: All log messages before absl',
    'is deprecated\. Please use tf\.',
    'No training configuration found in the save file',
    'cpu_feature_guard\.cc',
    'performance-critical operations',
    '^\s*I\d{4}\s',  # TensorFlow / absl INFO written to stderr (e.g. I0000 ...)
    'actively refused it\),\s*retry\s+\d+/\d+',  # API not up yet; bots retry on startup
    'failed \(.*\),\s*retry\s+\d+/\d+\s+in\s+\d+s'
  )
  foreach ($p in $benign) {
    if ($t -imatch $p) { return $true }
  }
  return $false
}

function Test-TbccErrorLine {
  param([string]$Line)
  if (-not $Line -or $Line.Length -lt 4) { return $false }
  $t = $Line.Trim()
  if ($t.Length -lt 4) { return $false }
  if (Test-TbccBenignHubLine -Line $t) { return $false }

  # Benign noise
  if ($t -match '^(INFO|DEBUG)\s') { return $false }
  if ($t -match '0 errors?\b') { return $false }
  if ($t -match 'no errors?\b') { return $false }
  if ($t -imatch 'is not recognized as the name of a cmdlet') { return $false }
  # Python logging " - WARNING - " (not ERROR); real failures use ERROR level or exceptions below
  if ($t -imatch '\s-\sWARNING\s-') { return $false }

  $patterns = @(
    'Traceback \(most recent call last\)',
    '\s-\s(ERROR|CRITICAL|FATAL)\s-',
    ':\s*(ERROR|CRITICAL|FATAL)\b',
    '\[(ERROR|CRITICAL|FATAL)\]',
    '\b(FATAL|ERROR)\s*:',
    'npm ERR!',
    'Failed to compile',
    'UnhandledPromiseRejection',
    'Unhandled.+exception',
    'ECONNREFUSED|EADDRINUSE|ENOENT',
    'WinError \d+',
    'ModuleNotFoundError',
    'ImportError:',
    'SyntaxError:',
    'AttributeError:',
    'TypeError:',
    'ValueError:',
    'RuntimeError:',
    'AssertionError',
    'OperationalError',
    'IntegrityError',
    'sqlalchemy\.exc\.',
    'Process exited with code [1-9]\d*',
    'exit code [1-9]\d*',
    'exited with code [1-9]\d*',
    'Worker exited',
    'Cannot find module',
    'ELIFECYCLE',
    'panic:',
    'Killed process',
    'OOM',
    'OutOfMemory',
    '500 Internal Server Error',
    '502 Bad Gateway',
    '503 Service Unavailable',
    'Connection refused(?!.*retry\s+\d+/\d+)',
    'Redis.*not available',
    'Authentication failed',
    'Unauthorized',
    'Permission denied',
    'No such file or directory',
    'Address already in use'
  )
  foreach ($p in $patterns) {
    if ($t -imatch $p) { return $true }
  }
  if ($t -imatch '^\s*error[:\s]') { return $true }
  if ($t -imatch 'exception in') { return $true }
  return $false
}

function Test-TbccWarningLine {
  param([string]$Line)
  if (-not $Line) { return $false }
  $t = $Line.Trim()
  if (Test-TbccBenignHubLine -Line $t) { return $false }
  # Skip library deprecation spam; hub is for actionable TBCC issues
  if ($t -imatch 'WARNING:tensorflow:') { return $false }
  if ($t -imatch '^(WARNING|WARN)\b') { return $true }
  if ($t -imatch '\[WARNING\]') { return $true }
  if ($t -imatch '\bUserWarning:') { return $true }
  return $false
}

function Test-TbccTracebackLine {
  param([string]$Line)
  if (-not $Line) { return $false }
  $t = $Line.Trim()
  if ($t -match '^Traceback \(most recent call last\)') { return $true }
  if ($t -match '^\s+File "' ) { return $true }
  if ($t -match '^\s+\w+Error:' ) { return $true }
  if ($t -match '^\w+Error:' ) { return $true }
  if ($t -match '^\s+raise ' ) { return $true }
  if ($t -match '^During handling of the following exception' ) { return $true }
  if ($t -match '^\s+~+\^+' ) { return $true }
  return $false
}
