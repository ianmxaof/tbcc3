# Show real shells (ignore conhost). Run:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\show-shell-owners.ps1

$ErrorActionPreference = 'SilentlyContinue'
$rows = @()

Get-Process powershell, pwsh, python, pythonw -ErrorAction SilentlyContinue | ForEach-Object {
  $age = 0
  try { $age = [math]::Round(((Get-Date) - $_.StartTime).TotalHours, 1) } catch {}
  $cmd = ''
  try {
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
  } catch {}
  if (-not $cmd) { $cmd = '' }
  if ($cmd.Length -gt 140) { $cmd = $cmd.Substring(0, 140) + '...' }

  $parName = '?'
  try { $parName = (Get-Process -Id $_.Parent.Id -ErrorAction Stop).ProcessName } catch {
    try {
      $ppid = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").ParentProcessId
      $parName = (Get-Process -Id $ppid -ErrorAction Stop).ProcessName
    } catch {}
  }

  $cl = $cmd.ToLowerInvariant()
  $tag = 'other'
  if ($cl -match 'tbcc-supervisor|tbcc-service-control|tbcc-launch-daemon|tbcc-stack-cli|start\.ps1') {
    $tag = 'KEEP-tray'
  } elseif ($cl -match 'celery|uvicorn|bots\.|vite') {
    $tag = 'KEEP-worker'
  } elseif ($cl -match 'ps-script-|agent-tools|sync-scraper-session') {
    $tag = 'KILL-agent'
  } elseif ($parName -match 'Cursor|Code') {
    $tag = 'check-Cursor'
  }

  $rows += [pscustomobject]@{
    Tag = $tag; AgeH = $age; PID = $_.Id; Name = $_.ProcessName; Parent = $parName; MB = [math]::Round($_.WorkingSet64 / 1MB, 0); Cmd = $cmd
  }
}

Write-Host ""
Write-Host ("conhost count (IGNORE these in Task Manager): " + @(Get-Process conhost -ErrorAction SilentlyContinue).Count) -ForegroundColor DarkGray
Write-Host "They are ~0.5MB wrappers. Killing them by eye does nothing useful." -ForegroundColor DarkGray
Write-Host ""
Write-Host "Look at these instead:" -ForegroundColor Cyan
$rows | Sort-Object Tag, AgeH -Descending | Format-Table Tag, AgeH, PID, Name, Parent, MB, Cmd -AutoSize
Write-Host "KEEP-* = leave alone. KILL-agent = trash Other Agents / run cleanup script. check-Cursor = end if AgeH>4 and unused."
