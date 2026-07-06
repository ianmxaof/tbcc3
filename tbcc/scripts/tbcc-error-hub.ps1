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

function Set-TbccConsoleTabTitle {
  <# Short tab/window title so Windows Terminal does not widen to fit "TBCC-Backend - powershell -File ...". #>
  param([Parameter(Mandatory = $true)][string]$Title)
  $t = $Title.Trim()
  if (-not $t) { return }
  try {
    if ($Host.UI -and $Host.UI.RawUI) {
      $Host.UI.RawUI.WindowTitle = $t
    }
  } catch {}
  try {
    $esc = [char]27
    $bel = [char]7
    [Console]::Out.Write("${esc}]0;${t}${bel}")
    [Console]::Out.Flush()
  } catch {}
}

function Get-TbccConsoleLayoutFromRoot {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $cols = 84
  $lines = 24
  $dotEnv = Join-Path $TbccRoot ".env"
  if (Test-Path -LiteralPath $dotEnv) {
    foreach ($line in Get-Content -LiteralPath $dotEnv -ErrorAction SilentlyContinue) {
      $raw = $line.Trim()
      if (-not $raw -or $raw.StartsWith("#")) { continue }
      $eq = $raw.IndexOf("=")
      if ($eq -lt 1) { continue }
      $k = $raw.Substring(0, $eq).Trim()
      $v = $raw.Substring($eq + 1).Trim()
      if ($v.StartsWith('"') -and $v.EndsWith('"') -and $v.Length -ge 2) { $v = $v.Substring(1, $v.Length - 2) }
      if ($k -eq "TBCC_CONSOLE_COLS") { try { $cols = [int]$v } catch {} }
      if ($k -eq "TBCC_CONSOLE_LINES") { try { $lines = [int]$v } catch {} }
    }
  }
  $cols = [Math]::Max(40, [Math]::Min(200, $cols))
  $lines = [Math]::Max(12, [Math]::Min(60, $lines))
  return @{ Cols = $cols; Lines = $lines }
}

function Initialize-TbccServiceConsole {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][string]$Title
  )
  Set-TbccConsoleTabTitle -Title $Title
  $layout = Get-TbccConsoleLayoutFromRoot -TbccRoot $TbccRoot
  $null = cmd /c ("mode con: cols={0} lines={1} >nul 2>&1" -f $layout.Cols, $layout.Lines)
}

function Test-TbccWtPowershellHubCommand {
  param([Parameter(Mandatory = $true)][string]$Command)
  return ($Command -match 'run-tbcc-service\.ps1|show-tbcc-error-hub\.ps1|run-tbcc-orchestrator\.ps1|run-tbcc-stackwatch\.ps1|run-openclaw-gateway\.ps1')
}

function Register-TbccSelfClosingServiceTab {
  <# Register launcher + return run-tbcc-service wrapper so every WT tab exits when its worker stops. #>
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][string]$ServiceName,
    [Parameter(Mandatory = $true)][string]$Command
  )
  $null = Register-TbccServiceLauncher -TbccRoot $TbccRoot -ServiceName $ServiceName -Command $Command
  return (Get-TbccServiceWrapperCmd -TbccRoot $TbccRoot -ServiceName $ServiceName)
}

function Get-TbccServiceTabDir {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  return Join-Path $TbccRoot ".tbcc-run\tabs"
}

function Get-TbccServiceTabSafeName {
  param([Parameter(Mandatory = $true)][string]$ServiceName)
  return ($ServiceName -replace '[^\w\-]', '_')
}

function Get-TbccServiceTabSessionPath {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][string]$ServiceName
  )
  $tabDir = Get-TbccServiceTabDir -TbccRoot $TbccRoot
  return Join-Path $tabDir ((Get-TbccServiceTabSafeName -ServiceName $ServiceName) + ".wt-session")
}

function Get-TbccServiceTabShellPidPath {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][string]$ServiceName
  )
  $tabDir = Get-TbccServiceTabDir -TbccRoot $TbccRoot
  return Join-Path $tabDir ((Get-TbccServiceTabSafeName -ServiceName $ServiceName) + ".shell.pid")
}

function Register-TbccServiceTabSession {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][string]$ServiceName
  )
  $tabDir = Get-TbccServiceTabDir -TbccRoot $TbccRoot
  New-Item -ItemType Directory -Force -Path $tabDir | Out-Null
  if ($env:WT_SESSION) {
    Set-Content -LiteralPath (Get-TbccServiceTabSessionPath -TbccRoot $TbccRoot -ServiceName $ServiceName) -Value $env:WT_SESSION.Trim() -Encoding ASCII -NoNewline
  }
}

function Register-TbccServiceTabShell {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][string]$ServiceName,
    [Parameter(Mandatory = $true)][int]$ShellPid
  )
  if ($ShellPid -le 4) { return }
  $tabDir = Get-TbccServiceTabDir -TbccRoot $TbccRoot
  New-Item -ItemType Directory -Force -Path $tabDir | Out-Null
  Set-Content -LiteralPath (Get-TbccServiceTabShellPidPath -TbccRoot $TbccRoot -ServiceName $ServiceName) -Value $ShellPid -Encoding ASCII -NoNewline
}

function Clear-TbccServiceTabSession {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][string]$ServiceName
  )
  $path = Get-TbccServiceTabSessionPath -TbccRoot $TbccRoot -ServiceName $ServiceName
  if (Test-Path -LiteralPath $path) {
    Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
  }
}

function Clear-TbccServiceTabShell {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][string]$ServiceName
  )
  $path = Get-TbccServiceTabShellPidPath -TbccRoot $TbccRoot -ServiceName $ServiceName
  if (Test-Path -LiteralPath $path) {
    Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
  }
}

function Get-TbccWtExePath {
  <# Resolve wt.exe for opening tabs. Falls back to WindowsApps alias when no direct binary exists. #>
  $candidates = @(
    (Join-Path ${env:ProgramFiles} "Windows Terminal\wt.exe"),
    (Join-Path $env:LOCALAPPDATA "Microsoft\Windows Terminal\wt.exe")
  )
  try {
    $pkg = Get-AppxPackage -Name Microsoft.WindowsTerminal -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pkg -and $pkg.InstallLocation) {
      $candidates += (Join-Path $pkg.InstallLocation "wt.exe")
    }
  } catch {}
  foreach ($p in $candidates) {
    if ($p -and (Test-Path -LiteralPath $p)) { return $p }
  }
  try {
    $c = Get-Command "wt.exe" -ErrorAction Stop
    if ($c.Source -and (Test-Path -LiteralPath $c.Source)) { return $c.Source }
  } catch {}
  return $null
}

function Test-TbccWtExeSupportsCloseTab {
  <# App Execution Alias wt.exe can spawn bogus "close-tab" error tabs — only use real binaries for close-tab. #>
  param([string]$WtExe)
  if (-not $WtExe) { return $false }
  if ($WtExe -match '\\WindowsApps\\') { return $false }
  return (Test-Path -LiteralPath $WtExe)
}

function Test-TbccClosingOwnServiceTab {
  param([Parameter(Mandatory = $true)][string]$ServiceName)
  try {
    $me = Get-CimInstance Win32_Process -Filter "ProcessId=$PID" -ErrorAction SilentlyContinue
    if (-not $me -or -not $me.CommandLine) { return $false }
    $cmd = [string]$me.CommandLine
    if ($ServiceName -eq 'TBCC-Orchestrator' -and $cmd -match 'run-tbcc-orchestrator\.ps1') { return $true }
    if ($ServiceName -eq 'TBCC-Errors' -and $cmd -match 'show-tbcc-error-hub') { return $true }
    if ($ServiceName -eq 'TBCC-StackWatch' -and $cmd -match 'run-tbcc-stackwatch\.ps1') { return $true }
    $pat = 'run-tbcc-service\.ps1.*-ServiceName\s+("?' + [regex]::Escape($ServiceName) + '"?)'
    return ($cmd -match $pat)
  } catch {
    return $false
  }
}

function Test-TbccLiveWindowsTerminalPid {
  param([int]$ProcessId)
  if ($ProcessId -le 4) { return $false }
  try {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    return ($proc -and ([string]$proc.Name -ieq 'WindowsTerminal.exe'))
  } catch {
    return $false
  }
}

function Get-TbccShellHostWindowsTerminalPid {
  try {
    $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    if ($all.Count -eq 0) { return $null }
    $byId = @{}
    foreach ($p in $all) { $byId[[int]$p.ProcessId] = $p }
    $cur = [int]$PID
    $seen = @{}
    while ($cur -gt 4 -and -not $seen.ContainsKey($cur)) {
      $seen[$cur] = $true
      if (-not $byId.ContainsKey($cur)) { break }
      $proc = $byId[$cur]
      if ([string]$proc.Name -ieq 'WindowsTerminal.exe') { return $cur }
      $cur = [int]$proc.ParentProcessId
    }
  } catch {}
  return $null
}

function Resolve-TbccWtHostPidForCloseTab {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $runDir = Join-Path $TbccRoot ".tbcc-run"
  $hostFile = Join-Path $runDir "windows-terminal-host.pid"
  if (Test-Path -LiteralPath $hostFile) {
    try {
      $pidVal = [int]((Get-Content -LiteralPath $hostFile -Raw -ErrorAction Stop).Trim())
      if (Test-TbccLiveWindowsTerminalPid -ProcessId $pidVal) { return $pidVal }
    } catch {}
  }
  $fromShell = Get-TbccShellHostWindowsTerminalPid
  if ($fromShell) { return $fromShell }
  if ($env:WT_WINDOW -and $env:WT_WINDOW -match '^\d+$') {
    $wp = [int]$env:WT_WINDOW
    if (Test-TbccLiveWindowsTerminalPid -ProcessId $wp) { return $wp }
  }
  return $null
}

function Get-TbccWtHostPidFromRunDir {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  return Resolve-TbccWtHostPidForCloseTab -TbccRoot $TbccRoot
}

function Invoke-TbccWtCommandSilent {
  param(
    [Parameter(Mandatory = $true)][string]$WtExe,
    [Parameter(Mandatory = $true)][string[]]$WtArgs,
    [int]$TimeoutMs = 5000
  )
  try {
    # Single argument string — array form can make wt treat "close-tab" as a shell command (error tabs).
    $argLine = ($WtArgs | ForEach-Object { [string]$_ }) -join ' '
    $p = Start-Process -FilePath $WtExe -ArgumentList $argLine -PassThru -WindowStyle Hidden
    if (-not $p.WaitForExit($TimeoutMs)) {
      try { $p.Kill() } catch {}
      return -1
    }
    return $p.ExitCode
  } catch {
    return -1
  }
}

function Test-TbccWtNewTabBackground {
  <#
  Default ON: after dispatching a new tab into an EXISTING TBCC WT window, keep that window
  in the background instead of letting Windows Terminal foreground it (focus steal on restart).
  Demotion is skipped only when WT was the foreground window before dispatch (user is actively
  in it), so it never yanks a window you are using. Set TBCC_WT_NEW_TAB_BACKGROUND=0 to disable.
  #>
  param([string]$TbccRoot = "")
  $raw = ($env:TBCC_WT_NEW_TAB_BACKGROUND -as [string])
  if (-not $raw -and $TbccRoot) {
    $envPath = Join-Path $TbccRoot ".env"
    if (Test-Path -LiteralPath $envPath) {
      foreach ($line in Get-Content -LiteralPath $envPath -ErrorAction SilentlyContinue) {
        $t = $line.Trim()
        if (-not $t -or $t.StartsWith("#")) { continue }
        if ($t -match '^\s*TBCC_WT_NEW_TAB_BACKGROUND\s*=\s*(.+)$') {
          $raw = $Matches[1].Trim().Trim('"')
          break
        }
      }
    }
  }
  if (-not $raw) { return $true }
  return $raw.Trim().ToLower() -notin @('0', 'false', 'no', 'off')
}

function Initialize-TbccWinInterop {
  <# Load the tiny user32 P/Invoke shim once (idempotent). Returns $true when available. #>
  if (([System.Management.Automation.PSTypeName]'Tbcc.WinInterop').Type) { return $true }
  try {
    Add-Type -Namespace 'Tbcc' -Name 'WinInterop' -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern bool ShowWindowAsync(System.IntPtr hWnd, int nCmdShow);
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern bool IsIconic(System.IntPtr hWnd);
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern System.IntPtr GetForegroundWindow();
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern bool SetWindowPos(System.IntPtr hWnd, System.IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
'@ -ErrorAction Stop
    return $true
  } catch {
    return $false
  }
}

function Get-TbccWtHostForeground {
  <#
  True when the reused WT host window is CURRENTLY the foreground window — i.e. the user is
  actively in it, so a background tab add must not demote it. Captured before dispatch.
  #>
  param([int]$WtHostPid)
  if ($WtHostPid -le 4) { return $false }
  if (-not (Initialize-TbccWinInterop)) { return $false }
  try {
    $proc = Get-Process -Id $WtHostPid -ErrorAction Stop
    $hWnd = $proc.MainWindowHandle
    if ($hWnd -eq [System.IntPtr]::Zero) { return $false }
    return ([Tbcc.WinInterop]::GetForegroundWindow() -eq $hWnd)
  } catch {
    return $false
  }
}

# Push the reused WT host to the bottom of the Z-order without activating it (no minimize jump),
# or keep it minimized if it already was. Re-applied on a loop across WT's async activation window.
$script:TbccWtDemoteScriptBlock = {
  param([int]$WtHostPid, [int]$DurationMs, [int]$IntervalMs)
  $HWND_BOTTOM = [System.IntPtr]1
  $SWP = [uint32](0x0010 -bor 0x0002 -bor 0x0001)  # NOACTIVATE | NOMOVE | NOSIZE
  $SW_SHOWMINNOACTIVE = 7
  $deadline = [DateTime]::UtcNow.AddMilliseconds($DurationMs)
  while ([DateTime]::UtcNow -lt $deadline) {
    try {
      $proc = Get-Process -Id $WtHostPid -ErrorAction Stop
      $hWnd = $proc.MainWindowHandle
      if ($hWnd -ne [System.IntPtr]::Zero) {
        if ([Tbcc.WinInterop]::IsIconic($hWnd)) {
          [void][Tbcc.WinInterop]::ShowWindowAsync($hWnd, $SW_SHOWMINNOACTIVE)
        } else {
          [void][Tbcc.WinInterop]::SetWindowPos($hWnd, $HWND_BOTTOM, 0, 0, 0, 0, $SWP)
        }
      }
    } catch {}
    Start-Sleep -Milliseconds $IntervalMs
  }
}

function Start-TbccWtHostDemotionAsync {
  <#
  Begin demoting the WT host window in a background runspace so it overlaps WT's async tab
  activation (which fires after the silent dispatcher exits). Returns a handle for reaping,
  or $null when interop/runspace is unavailable. Pair with Stop-TbccWtHostDemotionAsync.
  #>
  param([int]$WtHostPid, [int]$DurationMs = 1600, [int]$IntervalMs = 100)
  if ($WtHostPid -le 4) { return $null }
  if (-not (Initialize-TbccWinInterop)) { return $null }
  try {
    $ps = [PowerShell]::Create()
    [void]$ps.AddScript($script:TbccWtDemoteScriptBlock).AddArgument($WtHostPid).AddArgument($DurationMs).AddArgument($IntervalMs)
    $handle = $ps.BeginInvoke()
    return [pscustomobject]@{ PS = $ps; Handle = $handle }
  } catch {
    return $null
  }
}

function Stop-TbccWtHostDemotionAsync {
  <# Wait for (or stop) the demotion runspace and dispose it. Safe on $null. #>
  param($Job, [int]$TimeoutMs = 4000)
  if (-not $Job) { return }
  try {
    if ($Job.Handle -and -not $Job.Handle.AsyncWaitHandle.WaitOne($TimeoutMs)) {
      [void]$Job.PS.Stop()
    } elseif ($Job.Handle) {
      [void]$Job.PS.EndInvoke($Job.Handle)
    }
  } catch {}
  finally { try { $Job.PS.Dispose() } catch {} }
}

function Set-TbccWtHostWindowBackground {
  <#
  Synchronous fallback demotion (used only when the background runspace is unavailable):
  push the host to the bottom of the Z-order, or keep it minimized, across a short settle window.
  #>
  param([int]$WtHostPid, [int]$Retries = 8, [int]$DelayMs = 120)
  if ($WtHostPid -le 4) { return $false }
  if (-not (Initialize-TbccWinInterop)) { return $false }
  $HWND_BOTTOM = [System.IntPtr]1
  $SWP = [uint32](0x0010 -bor 0x0002 -bor 0x0001)  # NOACTIVATE | NOMOVE | NOSIZE
  $SW_SHOWMINNOACTIVE = 7
  $applied = $false
  for ($i = 0; $i -lt $Retries; $i++) {
    try {
      $proc = Get-Process -Id $WtHostPid -ErrorAction Stop
      $hWnd = $proc.MainWindowHandle
      if ($hWnd -ne [System.IntPtr]::Zero) {
        if ([Tbcc.WinInterop]::IsIconic($hWnd)) {
          [void][Tbcc.WinInterop]::ShowWindowAsync($hWnd, $SW_SHOWMINNOACTIVE)
        } else {
          [void][Tbcc.WinInterop]::SetWindowPos($hWnd, $HWND_BOTTOM, 0, 0, 0, 0, $SWP)
        }
        $applied = $true
      }
    } catch {}
    Start-Sleep -Milliseconds $DelayMs
  }
  return $applied
}

function Get-TbccServiceTabWrapperProcesses {
  param(
    [Parameter(Mandatory = $true)][string]$ServiceName,
    $AllProcesses = $null
  )
  if (-not $AllProcesses) {
    $AllProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
  }
  $pat = 'run-tbcc-service\.ps1.*-ServiceName\s+("?' + [regex]::Escape($ServiceName) + '"?)'
  return @($AllProcesses | Where-Object { $_.CommandLine -and ($_.CommandLine -match $pat) })
}

function Stop-TbccServiceTabShell {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][string]$ServiceName
  )
  $killed = @()
  $shellPid = 0
  $shellPath = Get-TbccServiceTabShellPidPath -TbccRoot $TbccRoot -ServiceName $ServiceName
  if (Test-Path -LiteralPath $shellPath) {
    try { $shellPid = [int]((Get-Content -LiteralPath $shellPath -Raw -ErrorAction Stop).Trim()) } catch {}
  }
  if ($shellPid -gt 4) {
    try {
      $proc = Get-Process -Id $shellPid -ErrorAction Stop
      if ($proc) {
        Stop-Process -Id $shellPid -Force -ErrorAction Stop
        $killed += $shellPid
      }
    } catch {}
  }
  foreach ($pr in (Get-TbccServiceTabWrapperProcesses -ServiceName $ServiceName)) {
    if ($killed -contains $pr.ProcessId) { continue }
    try {
      Stop-Process -Id $pr.ProcessId -Force -ErrorAction Stop
      $killed += [int]$pr.ProcessId
    } catch {}
  }
  return @($killed | Select-Object -Unique)
}

function Test-TbccWtCloseTabEnabled {
  param([string]$TbccRoot = "")
  $raw = ($env:TBCC_WT_CLOSE_TAB -as [string])
  if (-not $raw -and $TbccRoot) {
    $envPath = Join-Path $TbccRoot ".env"
    if (Test-Path -LiteralPath $envPath) {
      foreach ($line in Get-Content -LiteralPath $envPath -ErrorAction SilentlyContinue) {
        $t = $line.Trim()
        if (-not $t -or $t.StartsWith("#")) { continue }
        if ($t -match '^\s*TBCC_WT_CLOSE_TAB\s*=\s*(.+)$') {
          $raw = $Matches[1].Trim().Trim('"')
          break
        }
      }
    }
  }
  # Default OFF — wt close-tab via WindowsApps alias spawns "close-tab" error tabs (0x80070002).
  if (-not $raw) { return $false }
  return $raw.Trim().ToLower() -in @('1', 'true', 'yes', 'on')
}

function Invoke-TbccCloseServiceTab {
  <#
  Close the Windows Terminal tab for a TBCC service (after worker exit or orchestrated stop).
  Skips persistent hub/orchestrator tabs.
  Default: shell exit / kill tab shell PID — never spawns wt "close-tab" error tabs unless TBCC_WT_CLOSE_TAB=1.
  #>
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][string]$ServiceName
  )
  if ($ServiceName -in @('TBCC-Orchestrator')) {
    if (-not (Test-TbccClosingOwnServiceTab -ServiceName $ServiceName)) { return $false }
  }

  $closingSelf = Test-TbccClosingOwnServiceTab -ServiceName $ServiceName
  if ($closingSelf) {
    # run-tbcc-service.ps1 ending: clear registry only; PowerShell exit closes the WT tab.
    Clear-TbccServiceTabSession -TbccRoot $TbccRoot -ServiceName $ServiceName
    Clear-TbccServiceTabShell -TbccRoot $TbccRoot -ServiceName $ServiceName
    return $true
  }

  $closed = $false
  $wrappers = @(Get-TbccServiceTabWrapperProcesses -ServiceName $ServiceName)
  $hasShellRecord = Test-Path -LiteralPath (Get-TbccServiceTabShellPidPath -TbccRoot $TbccRoot -ServiceName $ServiceName)
  if ($wrappers.Count -gt 0 -or $hasShellRecord) {
    $killed = @(Stop-TbccServiceTabShell -TbccRoot $TbccRoot -ServiceName $ServiceName)
    $closed = ($killed.Count -gt 0)
  }

  if (-not $closed -and (Test-TbccWtCloseTabEnabled -TbccRoot $TbccRoot)) {
    $sessionPath = Get-TbccServiceTabSessionPath -TbccRoot $TbccRoot -ServiceName $ServiceName
    $target = $null
    if (Test-Path -LiteralPath $sessionPath) {
      try { $target = (Get-Content -LiteralPath $sessionPath -Raw -ErrorAction Stop).Trim() } catch {}
    }
    $wtExe = Get-TbccWtExePath
    if ((Test-TbccWtExeSupportsCloseTab -WtExe $wtExe) -and $target -and ($target -match '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')) {
      $hostPid = Resolve-TbccWtHostPidForCloseTab -TbccRoot $TbccRoot
      if ($hostPid -gt 0) {
        $exitCode = Invoke-TbccWtCommandSilent -WtExe $wtExe -WtArgs @('-w', "$hostPid", ';', 'close-tab', '--target', $target)
        $closed = ($exitCode -eq 0)
      }
    }
  }

  Clear-TbccServiceTabSession -TbccRoot $TbccRoot -ServiceName $ServiceName
  Clear-TbccServiceTabShell -TbccRoot $TbccRoot -ServiceName $ServiceName
  return $closed
}

function Invoke-TbccSweepStaleServiceTabShells {
  <# After orchestrated stop, kill any tab shells still recorded under .tbcc-run\tabs. #>
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $persist = @('TBCC-Errors', 'TBCC-Orchestrator', 'TBCC-StackWatch')
  $tabDir = Get-TbccServiceTabDir -TbccRoot $TbccRoot
  if (-not (Test-Path -LiteralPath $tabDir)) { return }
  foreach ($shellFile in @(Get-ChildItem -LiteralPath $tabDir -Filter '*.shell.pid' -ErrorAction SilentlyContinue)) {
    $svc = $shellFile.BaseName
    if ($svc -in $persist) { continue }
    $null = Invoke-TbccCloseServiceTab -TbccRoot $TbccRoot -ServiceName $svc
  }
}

function Add-TbccWtTabShellInvocation {
  <# Launch self-closing PowerShell tabs (never cmd /k — dead tabs on exit). #>
  param(
    [Parameter(Mandatory = $true)][System.Collections.ArrayList]$ArgumentList,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$Command,
    [int]$Cols = 84,
    [int]$Lines = 24
  )
  [void]$ArgumentList.Add('new-tab')
  [void]$ArgumentList.Add('--title')
  [void]$ArgumentList.Add($Title)

  $launchCmd = $Command
  if (-not (Test-TbccWtPowershellHubCommand -Command $launchCmd)) {
    $launchCmd = Register-TbccSelfClosingServiceTab -TbccRoot $TbccRoot -ServiceName $Title -Command $Command
  }

  if (Test-TbccWtPowershellHubCommand -Command $launchCmd) {
    $file = $null
    $root = $null
    if ($launchCmd -match '-File\s+"([^"]+)"') { $file = $Matches[1] }
    if ($launchCmd -match '-TbccRoot\s+"([^"]+)"') { $root = $Matches[1] }
    if (-not $file -or -not $root) {
      throw "Add-TbccWtTabShellInvocation: could not parse hub wrapper command."
    }
    [void]$ArgumentList.Add('powershell')
    [void]$ArgumentList.Add('-NoProfile')
    [void]$ArgumentList.Add('-NonInteractive')
    [void]$ArgumentList.Add('-ExecutionPolicy')
    [void]$ArgumentList.Add('Bypass')
    [void]$ArgumentList.Add('-File')
    [void]$ArgumentList.Add($file)
    [void]$ArgumentList.Add('-TbccRoot')
    [void]$ArgumentList.Add($root)
    if ($launchCmd -match 'run-tbcc-service\.ps1') {
      [void]$ArgumentList.Add('-ServiceName')
      [void]$ArgumentList.Add($Title)
    }
    if ($launchCmd -match 'run-tbcc-orchestrator\.ps1') {
      if ($launchCmd -match '-Action\s+(\w+)') {
        [void]$ArgumentList.Add('-Action')
        [void]$ArgumentList.Add($Matches[1])
      }
      if ($launchCmd -match '-NoOpen') {
        [void]$ArgumentList.Add('-NoOpen')
      }
    }
    if ($launchCmd -match 'run-tbcc-stackwatch\.ps1') {
      if ($launchCmd -match '-IntervalSec\s+(\d+)') {
        [void]$ArgumentList.Add('-IntervalSec')
        [void]$ArgumentList.Add($Matches[1])
      }
    }
    return
  }

  throw "Add-TbccWtTabShellInvocation: could not build self-closing tab for $Title"
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

function Get-TbccStackWatchCmd {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [int]$IntervalSec = 60
  )
  $watch = Join-Path $TbccRoot "scripts\run-tbcc-stackwatch.ps1"
  $tbccQ = '"' + $TbccRoot + '"'
  $watchQ = '"' + $watch + '"'
  return ('powershell -NoProfile -ExecutionPolicy Bypass -File ' + $watchQ + ' -TbccRoot ' + $tbccQ + ' -IntervalSec ' + $IntervalSec)
}

function Format-TbccHubLine {
  param([string]$Text, [int]$MaxLen = $script:TbccErrorHubMaxLineLen)
  if (-not $Text) { return "" }
  $one = ($Text -replace "[\r\n]+", " ").Trim()
  if ($one.Length -le $MaxLen) { return $one }
  return $one.Substring(0, $MaxLen) + " ...."
}

function Add-TbccErrorHubLogBytes {
  param(
    [Parameter(Mandatory = $true)][string]$LogPath,
    [Parameter(Mandatory = $true)][byte[]]$Bytes
  )
  # FileShare.ReadWrite lets show-tbcc-error-hub.ps1 (Get-Content -Wait) tail without blocking writers.
  $stream = [System.IO.File]::Open(
    $LogPath,
    [System.IO.FileMode]::Append,
    [System.IO.FileAccess]::Write,
    [System.IO.FileShare]::ReadWrite
  )
  try {
    $stream.Write($Bytes, 0, $Bytes.Length)
    $stream.Flush()
  } finally {
    $stream.Close()
    $stream.Dispose()
  }
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

  $utf8 = New-Object System.Text.UTF8Encoding $false
  $bytes = $utf8.GetBytes($line + [Environment]::NewLine)
  $mutex = New-Object System.Threading.Mutex($false, $script:TbccErrorHubMutexName)
  $gotMutex = $false
  try {
    $gotMutex = $mutex.WaitOne(15000)
    if (-not $gotMutex) { return }
    for ($attempt = 0; $attempt -lt 4; $attempt++) {
      try {
        Add-TbccErrorHubLogBytes -LogPath $paths.LogPath -Bytes $bytes
        return
      } catch [System.IO.IOException] {
        if ($attempt -ge 3) { throw }
        Start-Sleep -Milliseconds (40 * ($attempt + 1))
      }
    }
  } finally {
    if ($mutex -and $gotMutex) {
      try { $mutex.ReleaseMutex() } catch {}
    }
    if ($mutex) { $mutex.Dispose() }
  }
}

function Test-TbccAlreadyHubLine {
  param([string]$Line)
  if (-not $Line) { return $false }
  $t = $Line.Trim()
  if (-not $t) { return $false }
  return ($t -match '^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}\] \[[^\]]+\] \[(ERROR|WARN|INFO|CRITICAL|FATAL)\]')
}

function Test-TbccBenignHubLine {
  param([string]$Line)
  if (-not $Line) { return $true }
  $t = $Line.Trim()
  if (-not $t) { return $true }
  if (Test-TbccAlreadyHubLine -Line $t) { return $true }

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
    'oneDNN custom operations are on',
    'QuickGELU mismatch',
    'unauthenticated requests to the HF Hub',
    '^\s*I\d{4}\s',  # TensorFlow / absl INFO written to stderr (e.g. I0000 ...)
    'actively refused it\),\s*retry\s+\d+/\d+',  # API not up yet; bots retry on startup
    'failed \(.*\),\s*retry\s+\d+/\d+\s+in\s+\d+s',
    'httpx - INFO - HTTP Request:.*api\.telegram\.org.*HTTP/1\.1"\s+(502|503|504)',
    'networkloop\.py.*network_retry_loop'
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
  if (Test-TbccAlreadyHubLine -Line $t) { return $false }
  if (Test-TbccBenignHubLine -Line $t) { return $false }

  # Benign noise (uvicorn uses "INFO:" with a colon)
  if ($t -match '^(INFO|DEBUG)[\s:]') { return $false }
  if ($t -match 'HTTP/1\.1"\s+2\d\d\s') { return $false }
  if ($t -match '0 errors?\b') { return $false }
  if ($t -match 'no errors?\b') { return $false }
  if ($t -imatch 'is not recognized as the name of a cmdlet') { return $false }
  # Python logging " - WARNING - " / " - INFO - " (not ERROR); real failures use ERROR level or exceptions below
  if ($t -imatch '\s-\s(WARNING|INFO)\s-') { return $false }

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
