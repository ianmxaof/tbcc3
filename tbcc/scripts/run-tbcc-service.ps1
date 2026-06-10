# Runs one TBCC service (cmd.exe chain) and forwards likely errors to the unified error hub log.
param(
  [Parameter(Mandatory = $true)][string]$TbccRoot,
  [Parameter(Mandatory = $true)][string]$ServiceName
)

$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "tbcc-error-hub.ps1")
Initialize-TbccServiceConsole -TbccRoot $TbccRoot -Title $ServiceName

$paths = Get-TbccErrorHubPaths -TbccRoot $TbccRoot
$safeName = ($ServiceName -replace '[^\w\-]', '_')
$launcherPath = Join-Path $paths.LaunchersDir ($safeName + ".json")

if (-not (Test-Path -LiteralPath $launcherPath)) {
  Write-Host ("Launcher missing: " + $launcherPath) -ForegroundColor Red
  Write-Host "Re-run .\start.ps1 (do not start this script directly)." -ForegroundColor Yellow
  exit 1
}

$meta = Get-Content -LiteralPath $launcherPath -Raw -Encoding UTF8 | ConvertFrom-Json
$cmdLine = [string]$meta.command
if (-not $cmdLine) {
  Write-Host "Empty command in launcher." -ForegroundColor Red
  exit 1
}

$script:TracebackBuf = New-Object System.Collections.Generic.List[string]
$script:InTraceback = $false
$script:TraceLineCount = 0

function Flush-TbccTraceback {
  if ($script:TracebackBuf.Count -eq 0) { return }
  $joined = ($script:TracebackBuf.ToArray() -join " | ")
  Write-TbccErrorHubEntry -TbccRoot $TbccRoot -ServiceName $ServiceName -Level "ERROR" -Message $joined -Hint "See this service tab for full traceback"
  $script:TracebackBuf.Clear()
  $script:InTraceback = $false
  $script:TraceLineCount = 0
}

function Process-TbccOutputLine {
  param([string]$Line)
  if ($null -eq $Line) { return }

  if ($script:InTraceback) {
    if ([string]::IsNullOrWhiteSpace($Line)) {
      Flush-TbccTraceback
      return
    }
    if ((Test-TbccTracebackLine -Line $Line) -or $script:TraceLineCount -lt $script:TbccErrorHubMaxTraceLines) {
      [void]$script:TracebackBuf.Add((Format-TbccHubLine -Text $Line -MaxLen 200))
      $script:TraceLineCount++
      if ($script:TraceLineCount -ge $script:TbccErrorHubMaxTraceLines) {
        Flush-TbccTraceback
      }
      return
    }
    Flush-TbccTraceback
  }

  if (Test-TbccTracebackLine -Line $Line) {
    $script:InTraceback = $true
    $script:TraceLineCount = 1
    [void]$script:TracebackBuf.Add((Format-TbccHubLine -Text $Line -MaxLen 200))
    return
  }

  if (Test-TbccErrorLine -Line $Line) {
    Write-TbccErrorHubEntry -TbccRoot $TbccRoot -ServiceName $ServiceName -Level "ERROR" -Message $Line
    return
  }

  if (Test-TbccWarningLine -Line $Line) {
    Write-TbccErrorHubEntry -TbccRoot $TbccRoot -ServiceName $ServiceName -Level "WARN" -Message $Line
  }
}

Write-Host ("[" + $ServiceName + "] " + $cmdLine) -ForegroundColor DarkGray
Write-Host ""

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $env:ComSpec
$psi.Arguments = "/c " + $cmdLine + " 2>&1"
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $false
$psi.CreateNoWindow = $true
$psi.WorkingDirectory = $TbccRoot

$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi

if (-not $proc.Start()) {
  Write-TbccErrorHubEntry -TbccRoot $TbccRoot -ServiceName $ServiceName -Level "ERROR" -Message "Failed to start process."
  exit 1
}

$reader = $proc.StandardOutput
while ($true) {
  $line = $reader.ReadLine()
  if ($null -eq $line) {
    if ($proc.HasExited) { break }
    Start-Sleep -Milliseconds 50
    continue
  }
  Write-Host $line
  Process-TbccOutputLine -Line $line
}

$proc.WaitForExit()
Flush-TbccTraceback

$code = $proc.ExitCode
if ($code -ne 0) {
  # -1 / 0xC000013A: tab closed, orchestrator stop, or kill — not necessarily a crash.
  $level = if ($code -eq -1 -or $code -eq -1073741510) { "WARN" } else { "ERROR" }
  Write-TbccErrorHubEntry -TbccRoot $TbccRoot -ServiceName $ServiceName -Level $level -Message ("Process exited with code " + $code)
  Write-Host ""
  $color = if ($level -eq "WARN") { "Yellow" } else { "Red" }
  Write-Host ("[" + $ServiceName + "] exited " + $code + " - see TBCC-Errors tab.") -ForegroundColor $color
  exit $code
}

exit 0
