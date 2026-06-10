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

# Tray UI needs STA. Hidden shortcut sets TBCC_SUPERVISOR_TRAY=1; -ShowConsole keeps this window.
$showConsole = ($args -contains "-ShowConsole")
$self = $MyInvocation.MyCommand.Path
$isSta = ([Threading.Thread]::CurrentThread.GetApartmentState() -eq [Threading.ApartmentState]::STA)

# Single-instance arbiter. The live tray host owns this mutex for its whole lifetime, so any
# duplicate launch (autostart shortcut + manual double-click + extension daemon) must bow out.
$mutexName = "Global\TbccSupervisorTray"

function Test-TbccSupervisorAlreadyRunning {
  # True only while a live tray host holds the named mutex (its handle closes when that process dies).
  try {
    $existing = [System.Threading.Mutex]::OpenExisting($mutexName)
    $existing.Dispose()
    return $true
  } catch [System.Threading.WaitHandleCannotBeOpenedException] {
    return $false
  } catch {
    return $false
  }
}

if (-not $isSta -or ((-not $showConsole) -and $env:TBCC_SUPERVISOR_TRAY -ne "1")) {
  # Bootstrap stage: never spawn a hidden STA child if a tray is already live.
  if (Test-TbccSupervisorAlreadyRunning) { exit 0 }
  $argList = @(
    "-NoProfile", "-Sta", "-ExecutionPolicy", "Bypass", "-File", $self
  )
  if ($showConsole) { $argList += "-ShowConsole" }
  $winStyle = if ($showConsole) { "Normal" } else { "Hidden" }
  $env:TBCC_SUPERVISOR_TRAY = "1"
  Start-Process -FilePath "powershell.exe" -ArgumentList $argList -WindowStyle $winStyle
  exit 0
}

$env:TBCC_SUPERVISOR_TRAY = "1"

$toolsDir = $PSScriptRoot
$tbccDir = Split-Path -Parent $toolsDir
$controlScript = Join-Path $tbccDir "scripts\tbcc-service-control.ps1"
$errorHubLog = Join-Path $tbccDir ".tbcc-run\error-hub.log"

if (-not (Test-Path -LiteralPath $controlScript)) {
  Write-Error "Missing tbcc\scripts\tbcc-service-control.ps1"
  exit 1
}

. $controlScript

$panelScript = Join-Path $toolsDir "tbcc-supervisor-panel.ps1"
if (Test-Path -LiteralPath $panelScript) {
  . $panelScript
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$mutex = New-Object System.Threading.Mutex($false, $mutexName)
$acquired = $false
try {
  $acquired = $mutex.WaitOne(0, $false)
} catch [System.Threading.AbandonedMutexException] {
  # A previous tray host died without releasing the mutex; ownership transfers to us.
  $acquired = $true
}
if (-not $acquired) {
  # Another live tray host owns the mutex. Exit immediately and NEVER block on a modal
  # MessageBox here: launched -WindowStyle Hidden it renders invisible/unfocusable, so the
  # process hangs forever on a dialog nobody can dismiss -- that is the multi-instance meltdown.
  try {
    $runDir = Join-Path $tbccDir ".tbcc-run"
    if (-not (Test-Path -LiteralPath $runDir)) {
      New-Item -ItemType Directory -Force -Path $runDir | Out-Null
    }
    $line = "[{0:yyyy-MM-dd HH:mm:ss}] Duplicate supervisor launch ignored (another tray host already running)." -f (Get-Date)
    Add-Content -LiteralPath (Join-Path $runDir "supervisor.log") -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
  } catch {}
  $mutex.Dispose()
  exit 0
}

$script:TbccTrayRendererReady = $false

function Initialize-TbccTrayDarkRenderer {
  if ($script:TbccTrayRendererReady) { return $true }
  try {
    $null = [TbccTrayDarkMenuRenderer]
    $script:TbccTrayRendererReady = $true
    return $true
  } catch {
    # Type not loaded yet.
  }
  $src = @"
using System.Drawing;
using System.Windows.Forms;

public sealed class TbccTrayDarkColorTable : ProfessionalColorTable
{
    private static Color C(int r, int g, int b) { return Color.FromArgb(r, g, b); }
    private static readonly Color Bg = C(30, 30, 30);
    private static readonly Color Hover = C(58, 58, 62);
    private static readonly Color Pressed = C(45, 45, 48);
    private static readonly Color Border = C(45, 45, 48);
    private static readonly Color Sep = C(55, 55, 58);

    public override Color MenuItemSelected { get { return Hover; } }
    public override Color MenuItemSelectedGradientBegin { get { return Hover; } }
    public override Color MenuItemSelectedGradientEnd { get { return Hover; } }
    public override Color MenuItemPressedGradientBegin { get { return Pressed; } }
    public override Color MenuItemPressedGradientEnd { get { return Pressed; } }
    public override Color MenuItemBorder { get { return Border; } }
    public override Color MenuBorder { get { return Border; } }
    public override Color ToolStripDropDownBackground { get { return Bg; } }
    public override Color ImageMarginGradientBegin { get { return Bg; } }
    public override Color ImageMarginGradientMiddle { get { return Bg; } }
    public override Color ImageMarginGradientEnd { get { return Bg; } }
    public override Color SeparatorDark { get { return Sep; } }
    public override Color SeparatorLight { get { return Sep; } }
    public override Color MenuStripGradientBegin { get { return Bg; } }
    public override Color MenuStripGradientEnd { get { return Bg; } }
    public override Color OverflowButtonGradientBegin { get { return Bg; } }
    public override Color OverflowButtonGradientEnd { get { return Bg; } }
}

public sealed class TbccTrayDarkMenuRenderer : ToolStripProfessionalRenderer
{
    private static readonly Color Bone = Color.FromArgb(233, 230, 225);
    private static readonly Color BoneDim = Color.FromArgb(140, 138, 135);
    private static readonly Color Bg = Color.FromArgb(30, 30, 30);

    public TbccTrayDarkMenuRenderer() : base(new TbccTrayDarkColorTable()) { }

    protected override void OnRenderItemText(ToolStripItemTextRenderEventArgs e)
    {
        bool on = true;
        var tag = e.Item.Tag as System.Collections.IDictionary;
        if (tag != null && tag.Contains("TbccUserEnabled"))
        {
            try { on = System.Convert.ToBoolean(tag["TbccUserEnabled"]); } catch { on = true; }
        }
        else
        {
            on = e.Item.Enabled;
        }
        e.TextColor = on ? Bone : BoneDim;
        base.OnRenderItemText(e);
    }

    protected override void OnRenderMenuItemBackground(ToolStripItemRenderEventArgs e)
    {
        var g = e.Graphics;
        var r = new Rectangle(Point.Empty, e.Item.Size);
        if (e.Item.Selected && e.Item.Enabled)
            g.FillRectangle(new SolidBrush(Color.FromArgb(58, 58, 62)), r);
        else
            g.FillRectangle(new SolidBrush(Bg), r);
    }

    protected override void OnRenderSeparator(ToolStripSeparatorRenderEventArgs e)
    {
        var y = e.Item.Height / 2;
        var x1 = 8;
        var x2 = e.Item.Width - 8;
        if (x2 > x1)
            e.Graphics.DrawLine(new Pen(Color.FromArgb(55, 55, 58)), x1, y, x2, y);
    }
}
"@
  try {
    Add-Type -TypeDefinition $src -ReferencedAssemblies @(
      "System.Drawing.dll",
      "System.Windows.Forms.dll"
    ) -ErrorAction Stop
    $null = [TbccTrayDarkMenuRenderer]
    $script:TbccTrayRendererReady = $true
    return $true
  } catch {
    Write-TbccSupervisorLog ("Tray renderer compile failed: " + $_.Exception.Message)
    return $false
  }
}

function Set-TbccTrayMenuDarkTheme {
  param([System.Windows.Forms.ToolStrip]$Strip)
  if (-not $Strip) { return }
  $bg = [System.Drawing.Color]::FromArgb(30, 30, 30)
  $fg = [System.Drawing.Color]::FromArgb(233, 230, 225)
  $font = New-Object System.Drawing.Font("Segoe UI", 9.25)
  $Strip.BackColor = $bg
  $Strip.ForeColor = $fg
  $Strip.Font = $font
  $Strip.RenderMode = [System.Windows.Forms.ToolStripRenderMode]::Professional
  if (Initialize-TbccTrayDarkRenderer) {
    try {
      $Strip.Renderer = New-Object TbccTrayDarkMenuRenderer
    } catch {
      Write-TbccSupervisorLog ("Tray renderer attach failed: " + $_.Exception.Message)
    }
  }
  $Strip.ShowImageMargin = $false
  foreach ($item in $Strip.Items) {
    if ($item -is [System.Windows.Forms.ToolStripMenuItem]) {
      $item.BackColor = $bg
      $item.ForeColor = $fg
      $item.Font = $font
    }
  }
}

$script:lastColdStart = [DateTime]::MinValue
$script:notify = $null
$script:tbccStatusCache = $null
$script:tbccRestartMenuItems = @{}
$script:tbccStatusRefreshInFlight = $false
$script:tbccAlertsSeen = @{}
$script:lastOpsAlertPoll = [DateTime]::MinValue
$script:lastTrayBalloonAt = [DateTime]::MinValue
$script:allowSupervisorExit = $false
$script:supervisorLogPath = Join-Path $tbccDir ".tbcc-run\supervisor.log"
$script:orchestratorPending = $null
$script:lastOrchestratorPoll = [DateTime]::MinValue

function Write-TbccSupervisorLog {
  param([string]$Message)
  try {
    $runDir = Join-Path $tbccDir ".tbcc-run"
    if (-not (Test-Path -LiteralPath $runDir)) {
      New-Item -ItemType Directory -Force -Path $runDir | Out-Null
    }
    $line = "[{0:yyyy-MM-dd HH:mm:ss}] {1}" -f (Get-Date), $Message
    Add-Content -LiteralPath $script:supervisorLogPath -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
  } catch {}
}

function Show-TbccTrayBalloon {
  param([string]$Text, [int]$TimeoutMs = 2500, [switch]$Force)
  if (-not $script:notify) { return }
  $now = [DateTime]::UtcNow
  if (-not $Force -and ($now - $script:lastTrayBalloonAt).TotalSeconds -lt 12) { return }
  $tip = [string]$Text
  if ($tip.Length -gt 240) { $tip = $tip.Substring(0, 237) + "..." }
  try {
    $script:notify.BalloonTipTitle = "TBCC"
    $script:notify.BalloonTipText = $tip
    $script:notify.ShowBalloonTip([Math]::Min($TimeoutMs, 10000))
    $script:lastTrayBalloonAt = $now
  } catch {
    Write-TbccSupervisorLog ("Balloon failed: " + $_.Exception.Message)
  }
}

function Register-TbccOrchestratorWatch {
  param(
    [Parameter(Mandatory = $true)][ValidateSet("Stop", "Restart", "ColdStart")][string]$Action
  )
  $script:orchestratorPending = @{
    Action    = $Action
    StartedAt = Get-Date
  }
  $script:lastOrchestratorPoll = [DateTime]::MinValue
  Write-TbccSupervisorLog ("Orchestrator watch: " + $Action)
}

function Show-TbccOrchestratorCompletionBalloon {
  param(
    [Parameter(Mandatory = $true)][ValidateSet("Stop", "Restart", "ColdStart")][string]$Action,
    [Parameter(Mandatory = $true)][bool]$Success,
    [Parameter(Mandatory = $true)][string]$Message
  )
  $prefix = switch ($Action) {
    "Stop" { if ($Success) { "Stop complete" } else { "Stop finished with issues" } }
    "Restart" { if ($Success) { "Restart complete" } else { "Restart finished with issues" } }
    "ColdStart" { if ($Success) { "Cold start complete" } else { "Cold start finished with issues" } }
  }
  $timeoutMs = if ($Success) { 6000 } else { 9000 }
  Show-TbccTrayBalloon -Text ("$prefix - $Message") -TimeoutMs $timeoutMs -Force
  Write-TbccSupervisorLog ("Orchestrator notify: $prefix - $Message")
}

function Poll-TbccOrchestratorCompletion {
  if (-not $script:orchestratorPending) { return }
  $now = [DateTime]::UtcNow
  if (($now - $script:lastOrchestratorPoll).TotalSeconds -lt 2) { return }
  $script:lastOrchestratorPoll = $now

  $pending = $script:orchestratorPending
  $action = [string]$pending.Action
  $startedAt = $pending.StartedAt

  if (Test-TbccOrchestratorRunning) { return }

  $result = Read-TbccOrchestratorResult -TbccRoot $tbccDir
  $haveResult = $false
  if ($result -and $result.action -eq $action -and $result.finishedAt) {
    try {
      $finishedAt = [DateTime]::Parse([string]$result.finishedAt)
      if ($finishedAt.AddSeconds(-3) -ge $startedAt) { $haveResult = $true }
    } catch {}
  }

  if (-not $haveResult) {
    $elapsed = ((Get-Date) - $startedAt).TotalSeconds
    if ($elapsed -lt 8) { return }
    $msg = switch ($action) {
      "Stop" { Build-TbccOrchestratorStopMessage -TbccRoot $tbccDir -FullyStopped:$false }
      default { Build-TbccOrchestratorStartMessage -Action $action -TbccRoot $tbccDir -StartFailure "orchestrator finished without a result file" }
    }
    Show-TbccOrchestratorCompletionBalloon -Action $action -Success $false -Message $msg
    $script:orchestratorPending = $null
    Refresh-TbccSupervisorStatusCache
    return
  }

  $success = $false
  try { $success = [bool]$result.success } catch {}
  $msg = if ($result.message) { [string]$result.message } else { "Orchestrator finished." }
  Show-TbccOrchestratorCompletionBalloon -Action $action -Success:$success -Message $msg
  $script:orchestratorPending = $null
  Refresh-TbccSupervisorStatusCache
}

function Poll-TbccOpsAlerts {
  $now = [DateTime]::UtcNow
  if (($now - $script:lastOpsAlertPoll).TotalSeconds -lt 45) { return }
  $script:lastOpsAlertPoll = $now
  try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:8000/ops/alerts/poll" -Method GET -TimeoutSec 8
  } catch {
    return
  }
  if (-not $r -or $r.enabled -eq $false) { return }
  foreach ($a in @($r.alerts)) {
    try {
      if (-not $a -or -not $a.id) { continue }
      if ($script:tbccAlertsSeen.ContainsKey([string]$a.id)) { continue }
      $script:tbccAlertsSeen[[string]$a.id] = $true
      if ($script:tbccAlertsSeen.Count -gt 150) {
        $keys = @($script:tbccAlertsSeen.Keys)
        $drop = [Math]::Min(50, $keys.Count)
        for ($i = 0; $i -lt $drop; $i++) {
          $null = $script:tbccAlertsSeen.Remove($keys[$i])
        }
      }
      $sev = if ($a.severity) { [string]$a.severity } else { "warning" }
      if ($sev -eq "info") { continue }
      $title = if ($a.title) { [string]$a.title } else { "TBCC alert" }
      $msg = if ($a.message) { [string]$a.message } else { $title }
      if ($msg.Length -gt 180) { $msg = $msg.Substring(0, 180) + "..." }
      $force = ($sev -eq "critical")
      $timeoutMs = if ($force) { 8000 } else { 5000 }
      Show-TbccTrayBalloon -Text ("$title - $msg") -TimeoutMs $timeoutMs -Force:$force
    } catch {
      Write-TbccSupervisorLog ("Poll alert item failed: " + $_.Exception.Message)
    }
  }
}

function Invoke-TbccColdStartDebounced {
  $now = [DateTime]::UtcNow
  if (($now - $script:lastColdStart).TotalSeconds -lt 8) {
    Show-TbccTrayBalloon "Cold start ignored (wait a few seconds)."
    return
  }
  $script:lastColdStart = $now
  try {
    Register-TbccOrchestratorWatch -Action ColdStart
    Invoke-TbccColdStartFromTray -TbccRoot $tbccDir
    Show-TbccTrayBalloon "Cold start: TBCC-Orchestrator tab in Windows Terminal (you will be notified when finished)."
    Poll-TbccOrchestratorCompletion
  } catch {
    $script:orchestratorPending = $null
    Show-TbccTrayBalloon ("Cold start failed: " + $_.Exception.Message) -Force
  }
}

function Invoke-TbccRestartAllHot {
  try {
    Register-TbccOrchestratorWatch -Action Restart
    Invoke-TbccRestartFullStack -TbccRoot $tbccDir
    $script:lastColdStart = [DateTime]::UtcNow
    Show-TbccTrayBalloon "Restart: orchestrator tab will stop services then reopen tabs (you will be notified when finished)."
    Poll-TbccOrchestratorCompletion
  } catch {
    $script:orchestratorPending = $null
    Show-TbccTrayBalloon ("Restart failed: " + $_.Exception.Message) -Force
  }
}

function Invoke-TbccStopAllHot {
  try {
    Register-TbccOrchestratorWatch -Action Stop
    Invoke-TbccStopFullStack -TbccRoot $tbccDir
    Show-TbccTrayBalloon "Shutdown: orchestrator tab in Windows Terminal (you will be notified when it is safe to start again)."
    Poll-TbccOrchestratorCompletion
  } catch {
    $script:orchestratorPending = $null
    Show-TbccTrayBalloon ("Shutdown failed: " + $_.Exception.Message) -Force
  }
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
$script:notify.Text = "TBCC Supervisor (right-click)"
$script:notify.Visible = $true
# Win11 often hides new tray icons — balloon on start helps users find it.
$script:notify.BalloonTipTitle = "TBCC"

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

$stopAllItem = New-Object System.Windows.Forms.ToolStripMenuItem
$stopAllItem.Text = "Stop full stack (close services + terminal tabs)"
[void]$stopAllItem.Add_Click({
  try { Invoke-TbccStopAllHot } catch {
    Show-TbccTrayBalloon ("Shutdown failed: " + $_.Exception.Message)
  }
}.GetNewClosure())
[void]$menu.Items.Add($stopAllItem)

[void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

$sessionMenu = New-Object System.Windows.Forms.ToolStripMenuItem
$sessionMenu.Text = "Telegram session (admin.session)"

$stopContendersItem = New-Object System.Windows.Forms.ToolStripMenuItem
$stopContendersItem.Text = "Stop legacy scraper/admin bots (if any)"
$stopContendersItem.ToolTipText = "Kills python -m bots.scraper_bot / admin_bot if you ran them manually. Not part of start.ps1 -Full."
[void]$stopContendersItem.Add_Click({
  try {
    $n = @(Stop-TbccTelegramSessionContenders).Count
    if ($n -gt 0) {
      Show-TbccTrayBalloon ("Stopped $n contender process(es). Restart Celery if imports were stuck.")
    } else {
      Show-TbccTrayBalloon "No scraper_bot or admin_bot processes found."
    }
  } catch {
    Show-TbccTrayBalloon ("Stop contenders failed: " + $_.Exception.Message)
  }
}.GetNewClosure())
[void]$sessionMenu.DropDownItems.Add($stopContendersItem)

$restartCeleryItem = New-Object System.Windows.Forms.ToolStripMenuItem
$restartCeleryItem.Text = "Restart Celery worker"
[void]$restartCeleryItem.Add_Click({
  try {
    $null = Restart-TbccStackService -ServiceId "celery" -TbccRoot $tbccDir -FullStack -UseErrorHubWrapper
    Show-TbccTrayBalloon "Celery restarted (clears stuck import/Telegram tasks)."
  } catch {
    Show-TbccTrayBalloon ("Celery restart failed: " + $_.Exception.Message)
  }
}.GetNewClosure())
[void]$sessionMenu.DropDownItems.Add($restartCeleryItem)

[void]$menu.Items.Add($sessionMenu)

[void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

$apiPayItem = New-Object System.Windows.Forms.ToolStripMenuItem
$apiPayItem.Text = "Restart API + Payment bot"
[void]$apiPayItem.Add_Click({
  Invoke-TbccRestartApiPayment -TbccRoot $tbccDir
  Show-TbccTrayBalloon "Restart API + Payment bot..."
}.GetNewClosure())
[void]$menu.Items.Add($apiPayItem)

[void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

function Invoke-TbccFocusProfileApi {
  param([string]$Profile)
  try {
    if ($Profile -eq "off") {
      $null = Invoke-RestMethod -Uri "http://127.0.0.1:8000/ops/focus/restore" -Method POST -TimeoutSec 90
    } else {
      $body = (@{ profile = $Profile; reason = "Tray supervisor" } | ConvertTo-Json -Compress)
      $null = Invoke-RestMethod -Uri "http://127.0.0.1:8000/ops/focus" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 90
    }
    Show-TbccTrayBalloon ("Focus profile: " + $Profile)
    Refresh-TbccSupervisorStatusCache
  } catch {
    Show-TbccTrayBalloon ("Focus failed (TBCC-Backend up?): " + $_.Exception.Message)
  }
}

$focusMenu = New-Object System.Windows.Forms.ToolStripMenuItem
$focusMenu.Text = "Focus profile"
foreach ($pair in @(
    @{ Label = "Import burst (imports priority)"; Profile = "import_burst" },
    @{ Label = "Telegram relief (session lock storm)"; Profile = "telegram_relief" },
    @{ Label = "Watch folder only"; Profile = "watch_folder" },
    @{ Label = "End focus / restore services"; Profile = "off" }
  )) {
  $fi = New-Object System.Windows.Forms.ToolStripMenuItem
  $fi.Text = $pair.Label
  $prof = $pair.Profile
  [void]$fi.Add_Click({
    Invoke-TbccFocusProfileApi -Profile $prof
  }.GetNewClosure())
  [void]$focusMenu.DropDownItems.Add($fi)
}
Set-TbccTrayMenuDarkTheme -Strip $focusMenu.DropDown
[void]$menu.Items.Add($focusMenu)

[void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

$panelItem = New-Object System.Windows.Forms.ToolStripMenuItem
$panelItem.Text = "Open supervisor panel"
$panelItem.ToolTipText = "HWiNFO-style live stack dashboard (double-click tray icon)"
[void]$panelItem.Add_Click({
  try { Open-TbccSupervisorPanel } catch {
    Show-TbccTrayBalloon ("Panel failed: " + $_.Exception.Message) -Force
  }
}.GetNewClosure())
[void]$menu.Items.Add($panelItem)

$miniPanelItem = New-Object System.Windows.Forms.ToolStripMenuItem
$miniPanelItem.Text = "Open supervisor mini (always on top)"
$miniPanelItem.ToolTipText = "Compact CPU/RAM sparklines, stack up count, hub warn/crit"
[void]$miniPanelItem.Add_Click({
  try { Open-TbccSupervisorMiniPanel } catch {
    Show-TbccTrayBalloon ("Mini panel failed: " + $_.Exception.Message) -Force
  }
}.GetNewClosure())
[void]$menu.Items.Add($miniPanelItem)

[void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

$restartMenu = New-Object System.Windows.Forms.ToolStripMenuItem
$restartMenu.Text = "Services"
$restartMenu.ToolTipText = "Toggle each process on/off (white=enabled, gray=disabled). Ctrl+click restarts."
[void]$menu.Items.Add($restartMenu)

$procMonItem = New-Object System.Windows.Forms.ToolStripMenuItem
$procMonItem.Text = "Show process monitor (PowerShell)"
[void]$procMonItem.Add_Click({
  $script = Join-Path $tbccDir "scripts\show-tbcc-processes.ps1"
  if (Test-Path -LiteralPath $script) {
    Start-Process powershell.exe -ArgumentList @(
      "-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit", "-File", $script, "-Full"
    ) -WindowStyle Normal
  } else {
    Show-TbccTrayBalloon "Missing show-tbcc-processes.ps1"
  }
}.GetNewClosure())
[void]$menu.Items.Add($procMonItem)

function Open-TbccSupervisorPanel {
  if (-not (Get-Command Show-TbccSupervisorPanel -ErrorAction SilentlyContinue)) {
    Show-TbccTrayBalloon "Supervisor panel script missing (tbcc-supervisor-panel.ps1)." -Force
    return
  }
  try {
    Show-TbccSupervisorPanel -TbccRoot $tbccDir -FullStack `
      -OnNotify { param($msg) Show-TbccTrayBalloon $msg -Force } `
      -OnRefreshCache { param($cache) if ($cache) { Apply-TbccSupervisorStatusCacheUi -Cache $cache } else { Refresh-TbccSupervisorStatusCache } }
  } catch {
    Show-TbccTrayBalloon ("Panel failed: " + $_.Exception.Message) -Force
  }
}

function Open-TbccSupervisorMiniPanel {
  if (-not (Get-Command Show-TbccSupervisorMiniPanel -ErrorAction SilentlyContinue)) {
    Show-TbccTrayBalloon "Supervisor panel script missing (tbcc-supervisor-panel.ps1)." -Force
    return
  }
  try {
    Show-TbccSupervisorMiniPanel -TbccRoot $tbccDir -FullStack `
      -OnNotify { param($msg) Show-TbccTrayBalloon $msg -Force } `
      -OnRefreshCache { param($cache) if ($cache) { Apply-TbccSupervisorStatusCacheUi -Cache $cache } else { Refresh-TbccSupervisorStatusCache } }
  } catch {
    Show-TbccTrayBalloon ("Mini panel failed: " + $_.Exception.Message) -Force
  }
}

function Apply-TbccSupervisorStatusCacheUi {
  param($Cache)
  if (-not $Cache) { return }
  try {
    $script:tbccStatusCache = $Cache
    if ($script:notify) {
      Update-TbccSupervisorTrayStatus -NotifyIcon $script:notify -TbccRoot $tbccDir -FullStack -Cache $Cache
    }
    if ($script:tbccRestartMenuItems -and $script:tbccRestartMenuItems.Count -gt 0) {
      Apply-TbccServiceMenuItemsUi -MenuItemsById $script:tbccRestartMenuItems -Cache $Cache
    }
    Poll-TbccOpsAlerts
  } catch {
    Write-TbccSupervisorLog ("Apply status UI failed: " + $_.Exception.Message)
  }
}

function Refresh-TbccSupervisorStatusCache {
  if ($script:tbccStatusRefreshInFlight) { return }
  $script:tbccStatusRefreshInFlight = $true
  try {
    $cache = Update-TbccServiceStatusCache -TbccRoot $tbccDir -FullStack
    Apply-TbccSupervisorStatusCacheUi -Cache $cache
  } catch {
    Write-TbccSupervisorLog ("Status cache refresh failed: " + $_.Exception.Message)
  } finally {
    $script:tbccStatusRefreshInFlight = $false
  }
}

function Initialize-TbccSupervisorRestartMenu {
  $script:tbccRestartMenuItems = Initialize-TbccServiceToggleMenu -MenuItem $restartMenu -TbccRoot $tbccDir -FullStack -OnNotify {
    param($msg) Show-TbccTrayBalloon $msg -Force
  } -OnChanged {
    Refresh-TbccSupervisorStatusCache
  }
  Set-TbccTrayMenuDarkTheme -Strip $restartMenu.DropDown
}

[void]$restartMenu.Add_DropDownOpening({
  if (-not $script:tbccStatusCache) {
    Refresh-TbccSupervisorStatusCache
  } else {
    Apply-TbccServiceMenuItemsUi -MenuItemsById $script:tbccRestartMenuItems -Cache $script:tbccStatusCache
  }
  Set-TbccTrayMenuDarkTheme -Strip $restartMenu.DropDown
})

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

$openSupLog = New-Object System.Windows.Forms.ToolStripMenuItem
$openSupLog.Text = "Open supervisor log"
[void]$openSupLog.Add_Click({
  if (Test-Path -LiteralPath $script:supervisorLogPath) {
    Start-Process notepad.exe -ArgumentList $script:supervisorLogPath
  } else {
    Show-TbccTrayBalloon "No supervisor.log yet." -Force
  }
}.GetNewClosure())
[void]$menu.Items.Add($openSupLog)

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
  $script:allowSupervisorExit = $true
  $script:notify.Visible = $false
  $script:notify.Dispose()
  try { $mutex.ReleaseMutex() } catch {}
  $mutex.Dispose()
  [System.Windows.Forms.Application]::Exit()
}.GetNewClosure())
[void]$menu.Items.Add($exitItem)

Set-TbccTrayMenuDarkTheme -Strip $menu
Set-TbccTrayMenuDarkTheme -Strip $sessionMenu.DropDown

$script:notify.ContextMenuStrip = $menu

[void]$script:notify.Add_MouseDoubleClick({
  try { Open-TbccSupervisorPanel } catch {
    Show-TbccTrayBalloon ("Panel failed: " + $_.Exception.Message) -Force
  }
})

# Hidden form message loop
$form = New-Object System.Windows.Forms.Form
$form.Text = "TBCC Supervisor"
$form.ShowInTaskbar = $false
$form.WindowState = [System.Windows.Forms.FormWindowState]::Minimized
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedToolWindow
$form.Size = New-Object System.Drawing.Size(1, 1)
$statusTimer = New-Object System.Windows.Forms.Timer
$statusTimer.Interval = 30000
[void]$statusTimer.Add_Tick({
  try {
    Poll-TbccOrchestratorCompletion
    Refresh-TbccSupervisorStatusCache
  } catch {
    Write-TbccSupervisorLog ("Status timer: " + $_.Exception.Message)
  }
})

$orchestratorTimer = New-Object System.Windows.Forms.Timer
$orchestratorTimer.Interval = 2500
[void]$orchestratorTimer.Add_Tick({
  if (-not $script:orchestratorPending) { return }
  try { Poll-TbccOrchestratorCompletion } catch {
    Write-TbccSupervisorLog ("Orchestrator timer: " + $_.Exception.Message)
  }
})

$form.Add_FormClosing({
  param($sender, $e)
  if (-not $script:allowSupervisorExit) {
    $e.Cancel = $true
    try { $form.Hide() } catch {}
  }
})

$form.Add_Load({
  $form.Hide()
  try {
    [System.Windows.Forms.Application]::SetUnhandledExceptionMode(
      [System.Windows.Forms.UnhandledExceptionMode]::CatchException
    )
    [void][System.Windows.Forms.Application]::add_ThreadException({
      param($sender, $args)
      Write-TbccSupervisorLog ("UI thread: " + $args.Exception.Message)
      $args.ExceptionHandled = $true
    })
  } catch {}
  Initialize-TbccSupervisorRestartMenu
  Refresh-TbccSupervisorStatusCache
  $statusTimer.Start()
  $orchestratorTimer.Start()
  Show-TbccTrayBalloon "TBCC Supervisor ready. Double-click tray icon for the live panel." -Force
  Write-TbccSupervisorLog "Supervisor started."
})

try {
  [System.Windows.Forms.Application]::Run($form)
} catch {
  Write-TbccSupervisorLog ("Application.Run ended: " + $_.Exception.Message)
}

$statusTimer.Stop()
$statusTimer.Dispose()
$orchestratorTimer.Stop()
$orchestratorTimer.Dispose()

try { $mutex.ReleaseMutex() } catch {}
$mutex.Dispose()
