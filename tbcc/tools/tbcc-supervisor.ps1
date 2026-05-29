# TBCC system tray supervisor - one-click cold start and per-service restarts.
#
#   cd tbcc\tools
#   .\tbcc-supervisor.ps1              — tray only (spawns hidden host; console returns)
#   .\tbcc-supervisor.ps1 -ShowConsole — tray + keep this PowerShell window (debug)
#
# One-click shortcuts (Desktop / Start Menu — pin to taskbar):
#   .\install-tbcc-supervisor-shortcut.ps1 -AlsoDesktop
#   Or double-click: Launch-TBCC-Supervisor.bat
#
# Optional logon autostart:
#   .\register-supervisor-autostart.ps1
#
# Keep tbcc-launch-daemon.ps1 running for extension "Launch full stack" (cold start only).

$ErrorActionPreference = "Continue"

# Tray UI needs STA. By default run in a hidden host so restart/stop work does not
# close the console you launched from; use -ShowConsole to keep this window attached.
$showConsole = ($args -contains "-ShowConsole")
if (-not $showConsole -and $env:TBCC_SUPERVISOR_TRAY -ne "1") {
  $self = $MyInvocation.MyCommand.Path
  $env:TBCC_SUPERVISOR_TRAY = "1"
  Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-NoProfile", "-Sta", "-ExecutionPolicy", "Bypass", "-File", $self
  ) -WindowStyle Hidden
  exit 0
}
if ([Threading.Thread]::CurrentThread.GetApartmentState() -ne [Threading.ApartmentState]::STA) {
  $self = $MyInvocation.MyCommand.Path
  Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-NoProfile", "-Sta", "-ExecutionPolicy", "Bypass", "-File", $self
  ) -WindowStyle Hidden
  exit 0
}

$toolsDir = $PSScriptRoot
$tbccDir = Split-Path -Parent $toolsDir
$controlScript = Join-Path $tbccDir "scripts\tbcc-service-control.ps1"
$errorHubLog = Join-Path $tbccDir ".tbcc-run\error-hub.log"

if (-not (Test-Path -LiteralPath $controlScript)) {
  [System.Windows.Forms.MessageBox]::Show(
    "Missing tbcc\scripts\tbcc-service-control.ps1",
    "TBCC Supervisor",
    [System.Windows.Forms.MessageBoxButtons]::OK,
    [System.Windows.Forms.MessageBoxIcon]::Error
  ) | Out-Null
  exit 1
}

. $controlScript

$mutexName = "Global\TbccSupervisorTray"
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
if (-not $mutex.WaitOne(0, $false)) {
  [System.Windows.Forms.MessageBox]::Show(
    "TBCC Supervisor is already running (check the notification area).",
    "TBCC Supervisor",
    [System.Windows.Forms.MessageBoxButtons]::OK,
    [System.Windows.Forms.MessageBoxIcon]::Information
  ) | Out-Null
  exit 0
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$script:lastColdStart = [DateTime]::MinValue
$script:notify = $null

function Show-TbccTrayBalloon {
  param([string]$Text, [int]$TimeoutMs = 2500)
  if (-not $script:notify) { return }
  $script:notify.BalloonTipTitle = "TBCC"
  $script:notify.BalloonTipText = $Text
  $script:notify.ShowBalloonTip($TimeoutMs)
}

function Invoke-TbccColdStartDebounced {
  $now = [DateTime]::UtcNow
  if (($now - $script:lastColdStart).TotalSeconds -lt 8) {
    Show-TbccTrayBalloon "Cold start ignored (wait a few seconds)."
    return
  }
  $script:lastColdStart = $now
  try {
    Invoke-TbccColdStartFromTray -TbccRoot $tbccDir
    Show-TbccTrayBalloon "Cold start: one launcher window + Windows Terminal tabs (tray stays up)."
  } catch {
    Show-TbccTrayBalloon ("Cold start failed: " + $_.Exception.Message)
  }
}

function Invoke-TbccRestartAllHot {
  Show-TbccTrayBalloon "Full stack restart opening in launcher window..."
  try {
    Invoke-TbccRestartFullStack -TbccRoot $tbccDir
    $script:lastColdStart = [DateTime]::UtcNow
  } catch {
    Show-TbccTrayBalloon ("Restart failed: " + $_.Exception.Message)
  }
}

function New-TbccRestartMenuItem {
  param(
    [Parameter(Mandatory = $true)]$ParentMenu,
    [Parameter(Mandatory = $true)]$Service
  )
  $status = Get-TbccServiceStatusLabel -Service $Service
  $portLabel = if ($Service.Port -gt 0) { " :" + $Service.Port } else { "" }
  $item = New-Object System.Windows.Forms.ToolStripMenuItem
  $item.Text = ($Service.Title + $portLabel + " [" + $status + "]")
  $item.Tag = $Service.Id
  [void]$item.Add_Click({
    param($sender, $e)
    $id = $sender.Tag
    try {
      $null = Restart-TbccStackService -ServiceId $id -TbccRoot $tbccDir -FullStack -UseErrorHubWrapper
      Show-TbccTrayBalloon ("Restarted " + $sender.Text)
    } catch {
      Show-TbccTrayBalloon ("Restart failed: " + $_.Exception.Message)
    }
  }.GetNewClosure())
  [void]$ParentMenu.DropDownItems.Add($item)
}

# Tray icon
$iconPath = Join-Path $tbccDir "extension\icons\favicon.ico"
$icon = $null
if (Test-Path -LiteralPath $iconPath) {
  try { $icon = New-Object System.Drawing.Icon($iconPath) } catch {}
}
if (-not $icon) {
  $icon = [System.Drawing.SystemIcons]::Application
}

$script:notify = New-Object System.Windows.Forms.NotifyIcon
$script:notify.Icon = $icon
$script:notify.Text = "TBCC Supervisor"
$script:notify.Visible = $true

$menu = New-Object System.Windows.Forms.ContextMenuStrip

$coldStartItem = New-Object System.Windows.Forms.ToolStripMenuItem
$coldStartItem.Text = "Start full stack (cold)"
[void]$coldStartItem.Add_Click({
  try { Invoke-TbccColdStartDebounced } catch {
    Show-TbccTrayBalloon ("Cold start failed: " + $_.Exception.Message)
  }
}.GetNewClosure())
[void]$menu.Items.Add($coldStartItem)

$restartAllItem = New-Object System.Windows.Forms.ToolStripMenuItem
$restartAllItem.Text = "Restart full stack (stop all + cold start)"
[void]$restartAllItem.Add_Click({
  try { Invoke-TbccRestartAllHot } catch {
    Show-TbccTrayBalloon ("Restart failed: " + $_.Exception.Message)
  }
}.GetNewClosure())
[void]$menu.Items.Add($restartAllItem)

[void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

$apiPayItem = New-Object System.Windows.Forms.ToolStripMenuItem
$apiPayItem.Text = "Restart API + Payment bot"
[void]$apiPayItem.Add_Click({
  Invoke-TbccRestartApiPayment -TbccRoot $tbccDir
  Show-TbccTrayBalloon "Restart API + Payment bot..."
}.GetNewClosure())
[void]$menu.Items.Add($apiPayItem)

[void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

$restartMenu = New-Object System.Windows.Forms.ToolStripMenuItem
$restartMenu.Text = "Restart service"
$services = Get-TbccStackServices -TbccRoot $tbccDir -FullStack
foreach ($svc in $services) {
  New-TbccRestartMenuItem -ParentMenu $restartMenu -Service $svc
}
[void]$menu.Items.Add($restartMenu)

$cleanupItem = New-Object System.Windows.Forms.ToolStripMenuItem
$cleanupItem.Text = "Cleanup orphan API workers (port 8000)"
[void]$cleanupItem.Add_Click({
  $script = Join-Path $tbccDir "scripts\tbcc-cleanup-orphans.ps1"
  if (Test-Path -LiteralPath $script) {
    Start-Process powershell.exe -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $script) -WindowStyle Normal
    Show-TbccTrayBalloon "Orphan cleanup launched in PowerShell window."
  } else {
    Show-TbccTrayBalloon "Missing tbcc-cleanup-orphans.ps1"
  }
}.GetNewClosure())
[void]$menu.Items.Add($cleanupItem)

$healthItem = New-Object System.Windows.Forms.ToolStripMenuItem
$healthItem.Text = "Open system health (browser)"
[void]$healthItem.Add_Click({ Start-Process "http://127.0.0.1:8000/health/system" }.GetNewClosure())
[void]$menu.Items.Add($healthItem)

[void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

$openDash = New-Object System.Windows.Forms.ToolStripMenuItem
$openDash.Text = "Open dashboard"
[void]$openDash.Add_Click({ Start-Process "http://127.0.0.1:5173/" }.GetNewClosure())
[void]$menu.Items.Add($openDash)

$openErr = New-Object System.Windows.Forms.ToolStripMenuItem
$openErr.Text = "Open error hub log"
[void]$openErr.Add_Click({
  if (Test-Path -LiteralPath $errorHubLog) {
    Start-Process notepad.exe -ArgumentList $errorHubLog
  } else {
    Show-TbccTrayBalloon "No error-hub.log yet. Run cold start first."
  }
}.GetNewClosure())
[void]$menu.Items.Add($openErr)

$openFolder = New-Object System.Windows.Forms.ToolStripMenuItem
$openFolder.Text = "Open tbcc folder"
[void]$openFolder.Add_Click({ Start-Process explorer.exe -ArgumentList $tbccDir }.GetNewClosure())
[void]$menu.Items.Add($openFolder)

[void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

$exitItem = New-Object System.Windows.Forms.ToolStripMenuItem
$exitItem.Text = "Exit supervisor (services keep running)"
[void]$exitItem.Add_Click({
  $script:notify.Visible = $false
  $script:notify.Dispose()
  try { $mutex.ReleaseMutex() } catch {}
  $mutex.Dispose()
  [System.Windows.Forms.Application]::Exit()
}.GetNewClosure())
[void]$menu.Items.Add($exitItem)

$script:notify.ContextMenuStrip = $menu

# Hidden form message loop
$form = New-Object System.Windows.Forms.Form
$form.Text = "TBCC Supervisor"
$form.ShowInTaskbar = $false
$form.WindowState = [System.Windows.Forms.FormWindowState]::Minimized
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedToolWindow
$form.Size = New-Object System.Drawing.Size(1, 1)
$form.Add_Load({
  $form.Hide()
  Show-TbccTrayBalloon "TBCC Supervisor ready. Right-click tray icon for actions."
})

[System.Windows.Forms.Application]::Run($form)

try { $mutex.ReleaseMutex() } catch {}
$mutex.Dispose()
