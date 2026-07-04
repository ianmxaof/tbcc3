# TBCC-StackWatch - periodic process audit (60s) for tray + supervisor panel.
param(
  [string]$TbccRoot = "",
  [int]$IntervalSec = 60
)

$ErrorActionPreference = "Continue"
if (-not $TbccRoot) { $TbccRoot = Split-Path $PSScriptRoot -Parent }
if ($IntervalSec -lt 15) { $IntervalSec = 15 }

. (Join-Path $PSScriptRoot "tbcc-error-hub.ps1")
Initialize-TbccServiceConsole -TbccRoot $TbccRoot -Title "TBCC-StackWatch"
Register-TbccServiceTabShell -TbccRoot $TbccRoot -ServiceName "TBCC-StackWatch" -ShellPid $PID
. (Join-Path $PSScriptRoot "tbcc-process-audit.ps1")

Write-Host ""
Write-Host ("  TBCC StackWatch - process audit every {0}s" -f $IntervalSec) -ForegroundColor Cyan
Write-Host "  Snapshot: .tbcc-run\process-audit.json" -ForegroundColor DarkGray
Write-Host "  Log issues: error-hub.log [TBCC-ProcessAudit]" -ForegroundColor DarkGray
Write-Host ""

$lastLoggedSig = ""
$trimCooldownPath = Join-Path $TbccRoot ".tbcc-run\stackwatch-trim-cooldown.txt"
while ($true) {
  try {
    $report = Get-TbccProcessAuditReport -Root $TbccRoot -FullStack
    $prevToken = ""
    $tokenPath = Get-TbccProcessAuditAlertTokenPath -TbccRoot $TbccRoot
    if (Test-Path -LiteralPath $tokenPath) {
      $prevToken = [string](Get-Content -LiteralPath $tokenPath -Raw -ErrorAction SilentlyContinue).Trim()
    }
    $newToken = Write-TbccProcessAuditSnapshot -TbccRoot $TbccRoot -Report $report -PreviousAlertToken $prevToken

    $issueSig = if ($report.Issues.Count) {
      (($report.Issues | ForEach-Object { [string]$_ }) | Sort-Object) -join "`n"
    } else { "" }

    if ($report.IssueCount -gt 0 -and $issueSig -ne $lastLoggedSig) {
      foreach ($msg in $report.Issues) {
        Write-TbccErrorHubEntry -TbccRoot $TbccRoot -ServiceName "TBCC-ProcessAudit" -Level "WARN" -Message $msg
      }
      $lastLoggedSig = $issueSig
    }

    $hasDup = @($report.Issues | Where-Object { $_ -match 'duplicate processes' }).Count -gt 0
    $hasLean = $report.Lean -and $report.LeanCount -gt 0
    if ($hasLean -and (Get-Command Stop-TbccProcessesByCommandMatch -ErrorAction SilentlyContinue)) {
      $leanCooldownPath = Join-Path $TbccRoot ".tbcc-run\stackwatch-lean-cooldown.txt"
      $leanOk = $true
      if (Test-Path -LiteralPath $leanCooldownPath) {
        try {
          $last = [datetime](Get-Content -LiteralPath $leanCooldownPath -Raw -ErrorAction Stop).Trim()
          if (((Get-Date) - $last).TotalMinutes -lt 5) { $leanOk = $false }
        } catch {}
      }
      if ($leanOk) {
        . (Join-Path $PSScriptRoot "tbcc-service-control.ps1")
        foreach ($row in $script:TbccLeanForbiddenPatterns) {
          $null = @(Stop-TbccProcessesByCommandMatch -Pattern $row.Pattern)
        }
        (Get-Date).ToString("o") | Set-Content -LiteralPath $leanCooldownPath -Encoding UTF8
        $msg = "StackWatch stopped profile-forbidden process(es) (forum / macro / admin / enrichment)"
        Write-TbccErrorHubEntry -TbccRoot $TbccRoot -ServiceName "TBCC-StackWatch" -Level "WARN" -Message $msg
        Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg) -ForegroundColor Yellow
      }
    }
    if ($hasDup -and (Get-Command Ensure-TbccStackWorkersSingleton -ErrorAction SilentlyContinue)) {
      $cooldownOk = $true
      if (Test-Path -LiteralPath $trimCooldownPath) {
        try {
          $lastTrim = [datetime](Get-Content -LiteralPath $trimCooldownPath -Raw -ErrorAction Stop).Trim()
          if (((Get-Date) - $lastTrim).TotalMinutes -lt 3) { $cooldownOk = $false }
        } catch {}
      }
      if ($cooldownOk) {
        . (Join-Path $PSScriptRoot "tbcc-service-control.ps1")
        $trimReport = @(Ensure-TbccStackWorkersSingleton -TbccRoot $TbccRoot -FullStack -TrimOnly)
        $trimmedTotal = ($trimReport | ForEach-Object { [int]$_.Trimmed } | Measure-Object -Sum).Sum
        (Get-Date).ToString("o") | Set-Content -LiteralPath $trimCooldownPath -Encoding UTF8
        if ($trimmedTotal -gt 0) {
          $msg = "StackWatch auto-trimmed $trimmedTotal duplicate stack worker(s)"
        } else {
          $msg = "StackWatch ran stack singleton check (duplicates may need Stop all + Start)"
        }
        Write-TbccErrorHubEntry -TbccRoot $TbccRoot -ServiceName "TBCC-StackWatch" -Level "WARN" -Message $msg
        Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg) -ForegroundColor Yellow
      }
    }

    $color = if ($report.IssueCount -gt 0) { "Yellow" } else { "Green" }
    $alertNote = if ($newToken -and $newToken -ne $prevToken) { " NEW" } else { "" }
    $stamp = Get-Date -Format "HH:mm:ss"
    Write-Host ("[{0}] issues={1} {2}{3}" -f $stamp, $report.IssueCount, $report.SummaryMicro, $alertNote) -ForegroundColor $color
  } catch {
    $stamp = Get-Date -Format "HH:mm:ss"
    $err = $_.Exception.Message
    Write-Host ("[{0}] audit error: {1}" -f $stamp, $err) -ForegroundColor Red
  }
  Start-Sleep -Seconds $IntervalSec
}
