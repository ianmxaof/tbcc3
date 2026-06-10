# Core stop/start logic for TBCC-Orchestrator tab (run via run-tbcc-orchestrator.ps1).

param(

  [Parameter(Mandatory = $true)][string]$TbccRoot,

  [Parameter(Mandatory = $true)][ValidateSet("Stop", "Restart", "ColdStart")][string]$Action,

  [switch]$NoOpen

)



$ErrorActionPreference = "Continue"

$controlScript = Join-Path $PSScriptRoot "tbcc-service-control.ps1"

$startPs1 = Join-Path $TbccRoot "start.ps1"

$logPath = Join-Path $TbccRoot ".tbcc-run\orchestrate.log"



function Write-OrchestratorLog {

  param([string]$Message)

  try {

    $runDir = Split-Path -Parent $logPath

    if (-not (Test-Path -LiteralPath $runDir)) {

      New-Item -ItemType Directory -Path $runDir -Force | Out-Null

    }

    $line = ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message)

    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8

  } catch {}

}



function Wait-OrchestratorOnFailure {

  param([int]$ExitCode, [string]$Hint)

  if ($ExitCode -eq 0) { return }

  Write-Host ""

  Write-Host $Hint -ForegroundColor Red

  Write-Host ("Log: " + $logPath) -ForegroundColor Yellow

  Write-Host "Press Enter to close this tab..." -ForegroundColor DarkGray

  try { [void][System.Console]::ReadLine() } catch {}

}



function Complete-Orchestrator {

  param(

    [bool]$Success,

    [string]$Message,

    [int]$ExitCode = 0

  )

  Write-OrchestratorLog ("result success=$Success msg=" + $Message)

  Write-TbccOrchestratorResult -TbccRoot $TbccRoot -Action $Action -Success:$Success -Message $Message

  if ($ExitCode -ne 0) {

    Wait-OrchestratorOnFailure -ExitCode $ExitCode -Hint $Message

  }

  exit $ExitCode

}



if (-not (Test-Path -LiteralPath $controlScript)) {

  Write-Host "Missing tbcc-service-control.ps1" -ForegroundColor Red

  Write-OrchestratorLog "Missing tbcc-service-control.ps1"

  Wait-OrchestratorOnFailure -ExitCode 1 -Hint "Orchestrator failed: missing tbcc-service-control.ps1"

  exit 1

}



try {

  . $controlScript

} catch {

  $msg = "Failed to load tbcc-service-control.ps1: " + $_.Exception.Message

  Write-Host $msg -ForegroundColor Red

  Write-OrchestratorLog $msg

  Wait-OrchestratorOnFailure -ExitCode 1 -Hint $msg

  exit 1

}



function Write-OrchestratorPhase {

  param([string]$Text)

  Write-Host $Text -ForegroundColor Cyan

  Write-OrchestratorLog $Text

}



if ($Action -eq "Stop") {

  Write-OrchestratorPhase "TBCC shutdown - stopping services (tabs will close)..."

  $gone = Stop-TbccStackGracefully -TbccRoot $TbccRoot -FullStack -ExcludeProcessIds @($PID) -Wait -MaxWaitSeconds 60

  $msg = Build-TbccOrchestratorStopMessage -TbccRoot $TbccRoot -FullyStopped:$gone

  if ($gone) {

    Write-Host "  TBCC fully stopped." -ForegroundColor Green

  } else {

    Write-Host "  WARNING: Some services or ports may still be active." -ForegroundColor Red

  }

  Write-Host "Orchestrator closing." -ForegroundColor DarkGray

  Complete-Orchestrator -Success:$gone -Message $msg -ExitCode $(if ($gone) { 0 } else { 1 })

}



if ($Action -eq "ColdStart") {

  Write-OrchestratorPhase "TBCC cold start - stopping prior stack..."

} else {

  Write-OrchestratorPhase "TBCC restart - stopping services (tabs will close)..."

}



$priorGone = Stop-TbccStackGracefully -TbccRoot $TbccRoot -FullStack -ExcludeProcessIds @($PID) -Wait -MaxWaitSeconds 60

if ($priorGone) {

  Write-Host "  Prior stack stopped." -ForegroundColor Green

} else {

  Write-Host "  WARNING: Prior stack may still be running." -ForegroundColor Yellow

}



if (-not (Test-Path -LiteralPath $startPs1)) {

  Write-Host "Missing start.ps1" -ForegroundColor Red

  Write-OrchestratorLog "Missing start.ps1"

  $failMsg = Build-TbccOrchestratorStartMessage -Action $Action -TbccRoot $TbccRoot -PriorStackStopped:$priorGone -StartFailure "missing start.ps1"

  Complete-Orchestrator -Success $false -Message $failMsg -ExitCode 1

}



$wtHost = Get-TbccCurrentWindowsTerminalPid

if (-not $wtHost) {

  $wtHost = Get-TbccWtHostPid -TbccRoot $TbccRoot

}

if ($wtHost) {

  Write-Host ("  Reusing Windows Terminal window (pid {0})..." -f $wtHost) -ForegroundColor Gray

}



Write-OrchestratorPhase "Starting TBCC services in the same window..."

$startArgs = @("-Full", "-WtTabs", "-CompactConsole", "-SkipPriorStackStop", "-CloseAfterWtTabs")

if ($NoOpen) { $startArgs += "-NoOpen" }

if ($wtHost -gt 0) { $startArgs += @("-WtHostPid", "$wtHost") }



try {

  & $startPs1 @startArgs

  $code = if ($null -ne $LASTEXITCODE) { [int]$LASTEXITCODE } else { 0 }

  if ($code -ne 0) {

    Write-OrchestratorLog ("start.ps1 exited " + $code)

    $failMsg = Build-TbccOrchestratorStartMessage -Action $Action -TbccRoot $TbccRoot -PriorStackStopped:$priorGone -StartFailure ("start.ps1 exit code " + $code)

    Complete-Orchestrator -Success $false -Message $failMsg -ExitCode $code

  }

  Refresh-TbccWtHostPid -TbccRoot $TbccRoot -PreferredPid $wtHost

  Write-Host "  Waiting for services to come up..." -ForegroundColor Gray

  Start-Sleep -Seconds 6

  $down = @(Get-TbccEnabledServicesDownSummary -TbccRoot $TbccRoot -FullStack)

  $ok = ($down.Count -eq 0)

  $msg = Build-TbccOrchestratorStartMessage -Action $Action -TbccRoot $TbccRoot -PriorStackStopped:$priorGone

  if ($ok) {

    Write-Host "  TBCC stack is up." -ForegroundColor Green

  } else {

    Write-Host "  WARNING: Some enabled services are not up yet." -ForegroundColor Yellow

  }

  Write-Host "Orchestrator closing (service tabs are running)." -ForegroundColor DarkGray

  Complete-Orchestrator -Success:$ok -Message $msg -ExitCode $(if ($ok) { 0 } else { 1 })

} catch {

  $msg = "start.ps1 failed: " + $_.Exception.Message

  Write-Host $msg -ForegroundColor Red

  Write-OrchestratorLog $msg

  $failMsg = Build-TbccOrchestratorStartMessage -Action $Action -TbccRoot $TbccRoot -PriorStackStopped:$priorGone -StartFailure $_.Exception.Message

  Complete-Orchestrator -Success $false -Message $failMsg -ExitCode 1

}

