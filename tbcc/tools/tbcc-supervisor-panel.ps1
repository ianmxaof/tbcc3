# TBCC Supervisor Panel — HWiNFO-style dense status dashboard (WinForms).
# Dot-sourced from tbcc-supervisor.ps1 or run standalone after tbcc-service-control.ps1

function Resolve-TbccSupervisorRoot {
  param([string]$TbccRoot = "")
  if (-not [string]::IsNullOrWhiteSpace($TbccRoot)) {
    $p = $TbccRoot.Trim()
    if (Test-Path -LiteralPath $p) {
      return (Resolve-Path -LiteralPath $p).Path
    }
  }
  $tools = $PSScriptRoot
  if ($tools) {
    $candidate = [System.IO.Path]::GetFullPath((Join-Path $tools ".."))
    $ctl = Join-Path $candidate "scripts\tbcc-service-control.ps1"
    if (Test-Path -LiteralPath $ctl) {
      return $candidate
    }
  }
  throw "Cannot resolve TBCC root (pass -TbccRoot or run from tbcc\tools)."
}

function Get-TbccErrorHubLogPath {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  Join-Path $TbccRoot ".tbcc-run\error-hub.log"
}

function Open-TbccErrorHubLog {
  param(
    [string]$TbccRoot,
    [scriptblock]$OnNotify
  )
  if ([string]::IsNullOrWhiteSpace($TbccRoot) -and $script:TbccSupUi -and $script:TbccSupUi.TbccRoot) {
    $TbccRoot = $script:TbccSupUi.TbccRoot
  }
  if ([string]::IsNullOrWhiteSpace($TbccRoot)) {
    if ($OnNotify) { & $OnNotify "TBCC root path is not set." }
    return
  }
  $runDir = Join-Path $TbccRoot ".tbcc-run"
  $hubPath = Get-TbccErrorHubLogPath -TbccRoot $TbccRoot
  try {
    if (-not (Test-Path -LiteralPath $runDir)) {
      New-Item -ItemType Directory -Force -Path $runDir | Out-Null
    }
    if (-not (Test-Path -LiteralPath $hubPath)) {
      $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
      Set-Content -LiteralPath $hubPath -Value @(
        "# TBCC error hub - service stderr is aggregated here"
        "[$stamp] (supervisor) Log file created - run cold start to populate."
      ) -Encoding UTF8
    }
    Start-Process notepad.exe -ArgumentList @($hubPath)
  } catch {
    if ($OnNotify) { & $OnNotify ("Open hub log failed: " + $_.Exception.Message) }
  }
}

function Get-TbccSupervisorTheme {
  # +15% type scale vs original micro sizes (6.25→7.2 etc.) for legible Services labels.
  @{
    Bg          = [System.Drawing.Color]::FromArgb(18, 18, 20)
    ModuleBg    = [System.Drawing.Color]::FromArgb(24, 24, 28)
    ModuleBorder= [System.Drawing.Color]::FromArgb(52, 52, 58)
    HeaderBg    = [System.Drawing.Color]::FromArgb(32, 32, 38)
    CaptionActive = [System.Drawing.Color]::FromArgb(48, 44, 58)
    Text        = [System.Drawing.Color]::FromArgb(220, 218, 210)
    Muted       = [System.Drawing.Color]::FromArgb(120, 118, 112)
    Ok          = [System.Drawing.Color]::FromArgb(52, 211, 153)
    Warn        = [System.Drawing.Color]::FromArgb(251, 191, 36)
    Crit        = [System.Drawing.Color]::FromArgb(248, 113, 113)
    Off         = [System.Drawing.Color]::FromArgb(90, 90, 96)
    BarBg       = [System.Drawing.Color]::FromArgb(40, 40, 46)
    UiScale     = 1.15
    FontMicro   = New-Object System.Drawing.Font("Segoe UI", 7.2)
    FontLabel   = New-Object System.Drawing.Font("Segoe UI", 7.75)
    FontHeader  = New-Object System.Drawing.Font("Segoe UI", 7.75, [System.Drawing.FontStyle]::Bold)
    FontTitle   = New-Object System.Drawing.Font("Segoe UI", 8.35, [System.Drawing.FontStyle]::Bold)
    FontMono    = New-Object System.Drawing.Font("Consolas", 7.5)
  }
}

function New-TbccSupModule {
  param(
    [string]$Title,
    [int]$Height = 120,
    $Theme
  )
  $outer = New-Object System.Windows.Forms.Panel
  $outer.BackColor = $Theme.ModuleBorder
  $outer.Padding = New-Object System.Windows.Forms.Padding(1)
  $outer.Margin = New-Object System.Windows.Forms.Padding(2)
  $outer.Dock = [System.Windows.Forms.DockStyle]::Fill

  $inner = New-Object System.Windows.Forms.Panel
  $inner.Dock = [System.Windows.Forms.DockStyle]::Fill
  $inner.BackColor = $Theme.ModuleBg
  $outer.Controls.Add($inner)

  $hdr = New-Object System.Windows.Forms.Label
  $hdr.Text = $Title.ToUpper()
  $hdr.Dock = [System.Windows.Forms.DockStyle]::Top
  $hdr.Height = 16
  $hdr.BackColor = $Theme.HeaderBg
  $hdr.ForeColor = $Theme.Muted
  $hdr.Font = $Theme.FontHeader
  $hdr.Padding = New-Object System.Windows.Forms.Padding(6, 2, 0, 0)
  $inner.Controls.Add($hdr)

  $body = New-Object System.Windows.Forms.Panel
  $body.Dock = [System.Windows.Forms.DockStyle]::Fill
  $body.BackColor = $Theme.ModuleBg
  $body.Padding = New-Object System.Windows.Forms.Padding(4, 2, 4, 4)
  $inner.Controls.Add($body)

  return @{ Outer = $outer; Body = $body; Header = $hdr }
}

function Get-TbccCpuPercentFast {
  # Prefer Processor Utility (matches Task Manager) over % Processor Time.
  # Cached PerformanceCounter — first NextValue after create is always ~0; warm up and return null once.
  try {
    if (-not $script:TbccSupCpuCounter) {
      $created = $null
      foreach ($spec in @(
          @{ Cat = "Processor Information"; Ctr = "% Processor Utility"; Inst = "_Total" },
          @{ Cat = "Processor"; Ctr = "% Processor Time"; Inst = "_Total" }
        )) {
        try {
          $c = New-Object System.Diagnostics.PerformanceCounter($spec.Cat, $spec.Ctr, $spec.Inst, $true)
          [void]$c.NextValue()
          $created = $c
          break
        } catch {
          try { if ($c) { $c.Dispose() } } catch {}
        }
      }
      $script:TbccSupCpuCounter = $created
      return $null
    }
    $v = [double]$script:TbccSupCpuCounter.NextValue()
    if ($v -lt 0) { $v = 0 }
    if ($v -gt 100) { $v = 100 }
    return [int][Math]::Round($v)
  } catch {
    try { if ($script:TbccSupCpuCounter) { $script:TbccSupCpuCounter.Dispose() } } catch {}
    $script:TbccSupCpuCounter = $null
    try {
      $p = Get-CimInstance Win32_Processor -ErrorAction Stop | Select-Object -First 1
      if ($null -ne $p.LoadPercentage) { return [int]$p.LoadPercentage }
    } catch {}
    return $null
  }
}

function Get-TbccRamMetricsCached {
  <# CimInstance Win32_OperatingSystem is relatively expensive — cache ~2s for mini ticks. #>
  param([int]$TtlSec = 2)
  $now = Get-Date
  if ($script:TbccSupRamCache -and $script:TbccSupRamCacheAt -and `
      (($now - $script:TbccSupRamCacheAt).TotalSeconds -lt $TtlSec)) {
    return $script:TbccSupRamCache
  }
  $ramPct = $null
  $ramUsedGb = $null
  $ramTotalGb = $null
  try {
    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
    $total = [double]$os.TotalVisibleMemorySize * 1024
    $free = [double]$os.FreePhysicalMemory * 1024
    if ($total -gt 0) {
      $ramPct = [Math]::Round((1 - ($free / $total)) * 100, 1)
      $ramTotalGb = [Math]::Round($total / 1GB, 1)
      $ramUsedGb = [Math]::Round(($total - $free) / 1GB, 1)
    }
  } catch {}
  $script:TbccSupRamCache = @{
    RamPct     = $ramPct
    RamUsedGb  = $ramUsedGb
    RamTotalGb = $ramTotalGb
  }
  $script:TbccSupRamCacheAt = $now
  return $script:TbccSupRamCache
}

function Get-TbccHostMetrics {
  param(
    $NetPrev = $null,
    [switch]$Lite
  )
  $cpu = Get-TbccCpuPercentFast
  $ram = Get-TbccRamMetricsCached -TtlSec $(if ($Lite) { 2 } else { 1 })
  $net = $null
  if (-not $Lite) {
    $net = Get-TbccNetworkSample -Prev $NetPrev
  }
  return @{
    CpuPct     = $cpu
    RamPct     = $ram.RamPct
    RamUsedGb  = $ram.RamUsedGb
    RamTotalGb = $ram.RamTotalGb
    Net        = $net
  }
}

function Ensure-TbccSupervisorNativeTypes {
  <# Form subclass: pinned caption stays "active"; pause heavy work during drag/resize. #>
  if (("TbccSupForm" -as [type]) -and ("TbccWin32Ui" -as [type])) { return }
  try {
    Add-Type -ReferencedAssemblies System.Windows.Forms, System.Drawing -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;

public static class TbccWin32Ui {
  public static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);
  public static readonly IntPtr HWND_NOTOPMOST = new IntPtr(-2);
  public const uint SWP_NOMOVE = 0x0002;
  public const uint SWP_NOSIZE = 0x0001;
  public const uint SWP_NOACTIVATE = 0x0010;
  public const uint SWP_SHOWWINDOW = 0x0040;
  public const int SB_BOTH = 3;
  [DllImport("user32.dll")]
  public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter,
    int X, int Y, int cx, int cy, uint uFlags);
  [DllImport("user32.dll")]
  public static extern bool ShowScrollBar(IntPtr hWnd, int wBar, bool bShow);
  public const int DWMWA_USE_IMMERSIVE_DARK_MODE = 20;
  public const int DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1 = 19;
  [DllImport("dwmapi.dll")]
  public static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int attrValue, int attrSize);
}

public class TbccSupForm : Form {
  public bool KeepActiveCaption;
  public bool InteractionPaused { get; private set; }

  protected override void WndProc(ref Message m) {
    const int WM_NCACTIVATE = 0x0086;
    const int WM_ENTERSIZEMOVE = 0x0231;
    const int WM_EXITSIZEMOVE = 0x0232;
    if (m.Msg == WM_ENTERSIZEMOVE) {
      InteractionPaused = true;
    } else if (m.Msg == WM_EXITSIZEMOVE) {
      InteractionPaused = false;
    }
    // While Pin is on, refuse inactive caption paint so title bar stays selected-colored.
    if (KeepActiveCaption && m.Msg == WM_NCACTIVATE) {
      m.Result = (IntPtr)1;
      return;
    }
    base.WndProc(ref m);
  }
}
"@ -ErrorAction Stop
  } catch {}
}

function New-TbccSupervisorForm {
  Ensure-TbccSupervisorNativeTypes
  if ("TbccSupForm" -as [type]) {
    return (New-Object TbccSupForm)
  }
  return (New-Object System.Windows.Forms.Form)
}

function Test-TbccFormInteractionPaused {
  param($Form)
  if (-not $Form -or $Form.IsDisposed) { return $false }
  try {
    if (("TbccSupForm" -as [type]) -and ($Form -is [TbccSupForm])) {
      return [bool]$Form.InteractionPaused
    }
  } catch {}
  return $false
}

function Hide-TbccControlScrollBars {
  <# Hide white WinForms scrollbar chrome without disabling scrolling.
     Visible=false on VerticalScroll breaks AutoScroll/wheel — never do that. #>
  param($Control)
  if (-not $Control -or $Control.IsDisposed) { return }
  Ensure-TbccSupervisorNativeTypes
  try {
    if ($Control -is [System.Windows.Forms.ListBox]) {
      $Control.HorizontalScrollbar = $false
    }
    if (("TbccWin32Ui" -as [type]) -and $Control.IsHandleCreated) {
      [void][TbccWin32Ui]::ShowScrollBar($Control.Handle, [TbccWin32Ui]::SB_BOTH, $false)
    }
  } catch {}
}

function Register-TbccScrollBarSuppression {
  param($Control)
  if (-not $Control) { return }
  $apply = {
    param($sender, $e)
    Hide-TbccControlScrollBars -Control $sender
  }.GetNewClosure()
  try {
    [void]$Control.Add_HandleCreated($apply)
    [void]$Control.Add_Resize($apply)
    [void]$Control.Add_Layout($apply)
  } catch {}
  if ($Control.IsHandleCreated) {
    Hide-TbccControlScrollBars -Control $Control
  }
}

function Register-TbccWheelScroll {
  <# Mouse-wheel scrolls AutoScroll panels even with chrome hidden; bubbles from children. #>
  param($Control, [int]$LinePx = 28)
  if (-not $Control) { return }
  $handler = {
    param($sender, $e)
    $scrollable = $sender
    while ($scrollable -and -not (
        ($scrollable -is [System.Windows.Forms.ScrollableControl] -and $scrollable.AutoScroll) -or
        ($scrollable -is [System.Windows.Forms.ListBox])
      )) {
      $scrollable = $scrollable.Parent
    }
    if (-not $scrollable) { return }
    if ($scrollable -is [System.Windows.Forms.ListBox]) {
      $deltaLines = -[Math]::Sign($e.Delta) * [Math]::Max(1, [Math]::Abs([int]($e.Delta / 120)))
      $next = [Math]::Max(0, [Math]::Min($scrollable.Items.Count - 1, $scrollable.TopIndex + $deltaLines))
      $scrollable.TopIndex = $next
      return
    }
    # AutoScrollPosition get is negative; set expects positive offsets.
    $pos = $scrollable.AutoScrollPosition
    $step = 28 * [Math]::Max(1, [Math]::Abs([int]($e.Delta / 120))) * -[Math]::Sign($e.Delta)
    $scrollable.AutoScrollPosition = New-Object System.Drawing.Point(-$pos.X, (-$pos.Y + $step))
    Hide-TbccControlScrollBars -Control $scrollable
  }.GetNewClosure()
  $walk = {
    param($c)
    if (-not $c) { return }
    try { [void]$c.Add_MouseWheel($handler) } catch {}
    foreach ($child in @($c.Controls)) { & $walk $child }
  }
  & $walk $Control
}

function Get-TbccSupActionTag {
  param($Control)
  $c = $Control
  while ($null -ne $c) {
    if ($c.Tag -and $c.Tag.Id) { return $c.Tag }
    $c = $c.Parent
  }
  return $null
}

function Register-TbccSupSubtreeMouseClick {
  <# WinForms Label/LED children swallow Panel.Click — wire MouseClick on the whole subtree. #>
  param($Control, [scriptblock]$Handler)
  if (-not $Control -or -not $Handler) { return }
  $walk = {
    param($c)
    if (-not $c) { return }
    try {
      $c.Cursor = [System.Windows.Forms.Cursors]::Hand
      [void]$c.Add_MouseClick($Handler)
    } catch {}
    foreach ($child in @($c.Controls)) { & $walk $child }
  }
  & $walk $Control
}

function Set-TbccFormAlwaysOnTop {
  <# WinForms TopMost can lose to other TopMost apps; reassert via SetWindowPos. #>
  param(
    [Parameter(Mandatory = $true)]$Form,
    [bool]$Enabled
  )
  if (-not $Form -or $Form.IsDisposed) { return }
  Ensure-TbccSupervisorNativeTypes
  try {
    $Form.TopMost = [bool]$Enabled
    if (("TbccWin32Ui" -as [type]) -and $Form.IsHandleCreated) {
      $after = if ($Enabled) { [TbccWin32Ui]::HWND_TOPMOST } else { [TbccWin32Ui]::HWND_NOTOPMOST }
      $flags = [TbccWin32Ui]::SWP_NOMOVE -bor [TbccWin32Ui]::SWP_NOSIZE -bor [TbccWin32Ui]::SWP_NOACTIVATE -bor [TbccWin32Ui]::SWP_SHOWWINDOW
      [void][TbccWin32Ui]::SetWindowPos($Form.Handle, $after, 0, 0, 0, 0, $flags)
    } elseif (("TbccWin32TopMost" -as [type]) -and $Form.IsHandleCreated) {
      $after = if ($Enabled) { [TbccWin32TopMost]::HWND_TOPMOST } else { [TbccWin32TopMost]::HWND_NOTOPMOST }
      $flags = [TbccWin32TopMost]::SWP_NOMOVE -bor [TbccWin32TopMost]::SWP_NOSIZE -bor [TbccWin32TopMost]::SWP_NOACTIVATE -bor [TbccWin32TopMost]::SWP_SHOWWINDOW
      [void][TbccWin32TopMost]::SetWindowPos($Form.Handle, $after, 0, 0, 0, 0, $flags)
    }
    if (("TbccSupForm" -as [type]) -and ($Form -is [TbccSupForm])) {
      $Form.KeepActiveCaption = [bool]$Enabled
      try { $Form.Invalidate() } catch {}
    }
  } catch {
    try { $Form.TopMost = [bool]$Enabled } catch {}
  }
}

function Ensure-TbccDwmCaptionTypes {
  if ("TbccDwmCaption" -as [type]) { return }
  try {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class TbccDwmCaption {
  public const int DWMWA_USE_IMMERSIVE_DARK_MODE = 20;
  public const int DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1 = 19;
  [DllImport("dwmapi.dll")]
  public static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int attrValue, int attrSize);
}
"@ -ErrorAction Stop
  } catch {}
}

function Invoke-TbccFormDarkCaptionCore {
  param(
    [Parameter(Mandatory = $true)]$Form,
    [bool]$Enabled = $true
  )
  if (-not $Form -or $Form.IsDisposed -or -not $Form.IsHandleCreated) { return }
  Ensure-TbccDwmCaptionTypes
  if (-not ("TbccDwmCaption" -as [type])) { return }
  $val = if ($Enabled) { 1 } else { 0 }
  foreach ($attr in @(
      [TbccDwmCaption]::DWMWA_USE_IMMERSIVE_DARK_MODE,
      [TbccDwmCaption]::DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1
    )) {
    try { [void][TbccDwmCaption]::DwmSetWindowAttribute($Form.Handle, $attr, [ref]$val, 4) } catch {}
  }
}

function Set-TbccFormDarkCaption {
  <# Win11/10 dark native caption — matches Cursor/Electron chrome; call on HandleCreated. #>
  param(
    [Parameter(Mandatory = $true)]$Form,
    [bool]$Enabled = $true
  )
  if (-not $Form -or $Form.IsDisposed) { return }
  Ensure-TbccDwmCaptionTypes
  if (-not ("TbccDwmCaption" -as [type])) { return }
  # Never `& $localScriptBlock` from a deferred event — locals die after return and produce
  # "expression after '&' ... was not valid". Call a named function instead.
  if ($Form.IsHandleCreated) {
    Invoke-TbccFormDarkCaptionCore -Form $Form -Enabled:$Enabled
  } else {
    [void]$Form.Add_HandleCreated({
      param($s, $e)
      try { Invoke-TbccFormDarkCaptionCore -Form $s -Enabled:$true } catch {}
    })
  }
}

function Register-TbccFormChrome {
  param([Parameter(Mandatory = $true)]$Form)
  Set-TbccFormDarkCaption -Form $Form -Enabled:$true
}

function Get-TbccNetworkSample {
  param($Prev = $null)
  $now = Get-Date
  $rx = 0L
  $tx = 0L
  try {
    $adapters = @(Get-NetAdapterStatistics -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -notmatch 'vEthernet|Loopback|Virtual|Hyper-V|WFP|Npcap|TAP' })
    foreach ($a in $adapters) {
      $rx += [long]$a.ReceivedBytes
      $tx += [long]$a.SentBytes
    }
  } catch {}
  $down = $null
  $up = $null
  if ($Prev -and $null -ne $Prev.Rx -and $null -ne $Prev.Tx) {
    $dt = ($now - $Prev.At).TotalSeconds
    if ($dt -gt 0.15) {
      $down = [Math]::Max(0, ($rx - [long]$Prev.Rx) / $dt)
      $up = [Math]::Max(0, ($tx - [long]$Prev.Tx) / $dt)
    }
  }
  return @{ Rx = $rx; Tx = $tx; At = $now; DownBps = $down; UpBps = $up }
}

function Format-TbccBitrate {
  param([double]$Bps)
  if ($null -eq $Bps) { return "-" }
  if ($Bps -ge 1MB) { return ("{0:N1} MB/s" -f ($Bps / 1MB)) }
  if ($Bps -ge 1KB) { return ("{0:N0} KB/s" -f ($Bps / 1KB)) }
  return ("{0:N0} B/s" -f $Bps)
}

function Read-TbccErrorHubTail {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [int]$MaxLines = 48
  )
  if (-not (Test-Path -LiteralPath $Path)) { return @() }
  try {
    $buf = New-Object System.Collections.Generic.Queue[object]
    $fs = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open,
      [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try {
      # Big logs: seek to the last 256KB instead of streaming the whole file every
      # refresh tick (whole-file reads on a multi-MB hub log starved the UI thread).
      $seekFrom = 0L
      $lineNumbersExact = $true
      if ($fs.Length -gt 262144) {
        $seekFrom = $fs.Length - 262144
        [void]$fs.Seek($seekFrom, [System.IO.SeekOrigin]::Begin)
        $lineNumbersExact = $false
      }
      $sr = New-Object System.IO.StreamReader($fs)
      try {
        $lineNo = 0
        if (-not $lineNumbersExact) { [void]$sr.ReadLine() }  # drop probable partial line
        while ($null -ne ($line = $sr.ReadLine())) {
          $lineNo++
          $num = if ($lineNumbersExact) { $lineNo } else { 0 }
          $obj = [PSCustomObject]@{ LineNumber = $num; Text = $line }
          $buf.Enqueue($obj)
          while ($buf.Count -gt $MaxLines) { $null = $buf.Dequeue() }
        }
      } finally {
        $sr.Dispose()
      }
    } finally {
      $fs.Dispose()
    }
    return @($buf.ToArray())
  } catch {
    return @()
  }
}

function Open-TbccErrorHubAtLine {
  param(
    [Parameter(Mandatory = $true)][string]$LogPath,
    [Parameter(Mandatory = $true)][int]$LineNumber
  )
  if (-not (Test-Path -LiteralPath $LogPath)) { return $false }
  try {
    Start-Process notepad.exe -ArgumentList @("/G", [string]$LineNumber, $LogPath)
    return $true
  } catch {
    return $false
  }
}

function Get-TbccSupMeltdownStyle {
  <# Softer throttle strip: amber band, not nuclear red. Detail explains why HTTP/WMI backed off. #>
  param($Snap)
  $heat = 46.0
  $detail = ""
  if ($Snap -and $Snap.HealthErr -match 'API poll') {
    $detail = "API"
    $heat = 50
  } elseif ($Snap -and $Snap.Host) {
    $cpu = if ($null -ne $Snap.Host.CpuPct) { [double]$Snap.Host.CpuPct } else { 0 }
    $ram = if ($null -ne $Snap.Host.RamPct) { [double]$Snap.Host.RamPct } else { 0 }
    if ($cpu -ge 82) {
      $detail = ("CPU {0}%" -f [int]$cpu)
      $heat = [Math]::Min(68, 42 + ($cpu - 82) * 1.8)
    } elseif ($ram -ge 88) {
      $detail = ("RAM {0}%" -f [int]$ram)
      $heat = [Math]::Min(68, 42 + ($ram - 88) * 1.8)
    } else {
      $detail = "host"
      $heat = 44
    }
  }
  $prefix = if ($detail) { "THROTTLE $detail" } else { "THROTTLE" }
  return @{
    Prefix     = $prefix
    HeatPct    = $heat
    MiniPrefix = "THR"
  }
}

function New-TbccSupSparkline {
  param(
    [string]$Label,
    $Theme,
    [System.Drawing.Color]$LineColor,
    [int]$MaxPoints = 60,
    [int]$RowHeight = 28
  )
  $wrap = New-Object System.Windows.Forms.Panel
  $wrap.Height = $RowHeight
  $wrap.Dock = [System.Windows.Forms.DockStyle]::Bottom
  $wrap.BackColor = $Theme.ModuleBg
  $wrap.Margin = New-Object System.Windows.Forms.Padding(0, 1, 0, 0)

  $lbl = New-Object System.Windows.Forms.Label
  $lbl.Text = $Label
  $lbl.Width = 32
  $lbl.Dock = [System.Windows.Forms.DockStyle]::Left
  $lbl.ForeColor = $Theme.Muted
  $lbl.Font = $Theme.FontMicro
  $lbl.TextAlign = [System.Drawing.ContentAlignment]::MiddleLeft
  $wrap.Controls.Add($lbl)

  $canvas = New-Object System.Windows.Forms.Panel
  $canvas.Dock = [System.Windows.Forms.DockStyle]::Fill
  $canvas.BackColor = [System.Drawing.Color]::FromArgb(14, 14, 16)
  $canvas.Tag = @{
    Values    = (New-Object System.Collections.Generic.List[double])
    Max       = $MaxPoints
    Theme     = $Theme
    LineColor = $LineColor
    Mode      = "bars"
  }
  $canvas.Add_Paint({
    param($sender, $e)
    $g = $e.Graphics
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::None
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
    $tag = $sender.Tag
    $w = $sender.Width
    $h = $sender.Height
    $bg = [System.Drawing.Color]::FromArgb(14, 14, 16)
    $bgBrush = New-Object System.Drawing.SolidBrush($bg)
    $g.FillRectangle($bgBrush, 0, 0, $w, $h)
    $bgBrush.Dispose()
    $vals = @($tag.Values)
    if ($vals.Count -lt 1) { return }
    $pad = 1
    $innerW = [Math]::Max(1, $w - ($pad * 2))
    $innerH = [Math]::Max(1, $h - ($pad * 2))
    $count = $vals.Count
    $barW = [Math]::Max(1, [int][Math]::Floor($innerW / $count))
    $base = $tag.LineColor
    $dim = [System.Drawing.Color]::FromArgb(
      [int][Math]::Round($base.R * 0.48),
      [int][Math]::Round($base.G * 0.48),
      [int][Math]::Round($base.B * 0.48))
    for ($i = 0; $i -lt $count; $i++) {
      $norm = [Math]::Max(0, [Math]::Min(1, [double]$vals[$i] / 100.0))
      $barH = [int][Math]::Max(1, [Math]::Round($norm * $innerH))
      $x = $pad + ($i * $barW)
      if ($x + $barW -gt $w - $pad) { $barW = [Math]::Max(1, $w - $pad - $x) }
      $y = $pad + ($innerH - $barH)
      $isLast = ($i -eq ($count - 1))
      $fill = if ($isLast) { $base } else { $dim }
      $barBrush = New-Object System.Drawing.SolidBrush($fill)
      $g.FillRectangle($barBrush, $x, $y, $barW, $barH)
      $barBrush.Dispose()
      if ($isLast -and $barH -ge 2) {
        $flashBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(170, 255, 255, 255))
        $capH = [Math]::Min(2, $barH)
        $g.FillRectangle($flashBrush, $x, $y, $barW, $capH)
        $flashBrush.Dispose()
      }
    }
  })
  $wrap.Controls.Add($canvas)

  return @{ Wrap = $wrap; Canvas = $canvas }
}

function Push-TbccSupSparklineSample {
  param($Canvas, [double]$Value)
  if (-not $Canvas -or $null -eq $Value -or $Value -lt 0) { return }
  $list = $Canvas.Tag.Values
  [void]$list.Add($Value)
  while ($list.Count -gt $Canvas.Tag.Max) { $list.RemoveAt(0) }
  $Canvas.Invalidate()
}

function Get-TbccHubEntryText {
  param($Entry)
  if ($null -eq $Entry) { return "" }
  if ($Entry -is [string]) { return [string]$Entry }
  $prop = $Entry.PSObject.Properties['Text']
  if ($prop) { return [string]$prop.Value }
  return [string]$Entry
}

function Get-TbccHubLineSeverity {
  param([string]$Line)
  if (-not $Line) { return "muted" }
  $l = $Line.ToLowerInvariant()
  # Reserve "crit" for actionable meltdown signals — plain Traceback/Error stay "warn"
  # so the Hub pane is not a wall of nuclear red.
  if ($l -match 'database is locked|address already in use|eaddrinuse') { return "crit" }
  if ($l -match '(^|\W)critical(\W|$)|fatal error|out of memory|access is denied') { return "crit" }
  if ($l -match 'traceback|error|failed|exception|refused|winerror|warning|\bwarn\b') { return "warn" }
  return "ok"
}

function Get-TbccHeatColor {
  <# Continuous green → amber → nuclear-red. Pct 0 = stable green; 100 = brightest red.
     Mild mid band; upper percentiles punch harder so ~89% is near-peak (not mid yellow). #>
  param(
    [double]$Pct,
    [switch]$Invert
  )
  $t = [Math]::Max(0.0, [Math]::Min(100.0, $Pct)) / 100.0
  if ($Invert) { $t = 1.0 - $t }
  # Ease: keep 0–55% relatively mild, then accelerate toward red (89% ≈ 0.93 on curve).
  $u = [Math]::Pow($t, 0.72)
  $green = @{ R = 52; G = 211; B = 153 }
  $amber = @{ R = 251; G = 191; B = 36 }
  $peak = @{ R = 248; G = 113; B = 113 }
  $nuke = @{ R = 220; G = 38; B = 38 }
  if ($u -le 0.55) {
    $f = $u / 0.55
    $a = $green; $b = $amber
  } else {
    $f = ($u - 0.55) / 0.45
    # last 8%: blend peak → nuke so 100% is distinct from 89%
    if ($u -ge 0.92) {
      $f = ($u - 0.92) / 0.08
      $a = $peak; $b = $nuke
    } else {
      $f = ($u - 0.55) / 0.37
      $a = $amber; $b = $peak
    }
  }
  $f = [Math]::Max(0.0, [Math]::Min(1.0, $f))
  return [System.Drawing.Color]::FromArgb(
    [int][Math]::Round($a.R + ($b.R - $a.R) * $f),
    [int][Math]::Round($a.G + ($b.G - $a.G) * $f),
    [int][Math]::Round($a.B + ($b.B - $a.B) * $f)
  )
}

function Get-TbccHubInkColor {
  param([string]$Severity, $Theme)
  switch ($Severity) {
    "crit" { return (Get-TbccHeatColor -Pct 94) }
    "warn" { return (Get-TbccHeatColor -Pct 58) }
    "ok" { return (Get-TbccHeatColor -Pct 14) }
    default {
      if ($Theme) { return $Theme.Muted }
      return [System.Drawing.Color]::FromArgb(120, 118, 112)
    }
  }
}

function Get-TbccHubLineHint {
  <# Dynamic recovery hint for Hub hover / Mini footer. Suggests - does not auto-apply. #>
  param([string]$Line)
  if ([string]::IsNullOrWhiteSpace($Line)) {
    return "Hub is quiet. Double-click a line later to jump in notepad."
  }
  $l = $Line.ToLowerInvariant()
  if ($l -match 'database is locked') {
    return "CAUSE: two Telethon/bot writers share a session.`nFIX: stop duplicate bots (panel Off) - keep one writer. Wait ~5s, then start only what you need. Do not Start from a second terminal."
  }
  if ($l -match 'address already in use|eaddrinuse') {
    return "CAUSE: port already taken.`nFIX: panel Off on the service owning that port, or tray Stop that id. Confirm with stack-cli Status before Start again."
  }
  if ($l -match 'connection refused|actively refused|timed out|timeout') {
    return "CAUSE: backend/:8000 down or hung.`nFIX: Start Backend from tray; wait until Health OK. Avoid mass-restarting Celery until API answers."
  }
  if ($l -match 'celery|workerlost|soft time limit|timelimitexceeded') {
    return "CAUSE: Celery worker crash/timeout.`nFIX: open this line (double-click Hub). Fix the task error, then Ctrl+click restart only the affected celery_* service - not all bots."
  }
  if ($l -match 'traceback|exception') {
    return "CAUSE: unhandled exception in a service.`nFIX: double-click to open the hub log at this line. Restart that one service after the root fix. Prefer not to auto-heal Tracebacks (wrong restart can 409 Telegram)."
  }
  if ($l -match '401|403|unauthorized|forbidden') {
    return "CAUSE: auth/token rejected.`nFIX: check .env credentials for that bot/API (do not commit). Restart only that service after the secret is fixed."
  }
  if ($l -match 'discord|buffer|graphql') {
    return "CAUSE: external API failure.`nFIX: check network + provider status. Retry later; don't hammer Start. Buffer/Discord errors rarely need a full stack restart."
  }
  if ($l -match 'error|failed|warn') {
    return "CAUSE: service logged a failure.`nFIX: double-click Hub line -> notepad. Prefer targeted restart (Ctrl+click that service) over full stack bounce."
  }
  return "HINT: double-click to open error-hub.log at this line. Toggle services with click; Ctrl+click restarts."
}

function Get-TbccHubFootHint {
  param($HubLines, [int]$HubWarn, [int]$HubCrit, [double]$CpuPct = -1)
  $parts = New-Object System.Collections.Generic.List[string]
  if ($HubCrit -gt 0) {
    [void]$parts.Add(("{0} critical signal(s) - red reserved for port/session/auth meltdown." -f $HubCrit))
  } elseif ($HubWarn -gt 0) {
    [void]$parts.Add(("{0} warning line(s) - amber = attention, not panic." -f $HubWarn))
  } else {
    [void]$parts.Add("Hub quiet.")
  }
  if ($CpuPct -ge 0) {
    [void]$parts.Add(("CPU heat {0:N0}% (footer color tracks load + hub pressure)." -f $CpuPct))
  }
  $sample = $null
  foreach ($entry in @($HubLines)) {
    $txt = Get-TbccHubEntryText -Entry $entry
    $sev = Get-TbccHubLineSeverity -Line $txt
    if ($sev -eq "crit") { $sample = $txt; break }
    if ($sev -eq "warn" -and -not $sample) { $sample = $txt }
  }
  if ($sample) {
    [void]$parts.Add("")
    [void]$parts.Add((Get-TbccHubLineHint -Line $sample))
  }
  return ($parts -join "`n")
}

function Test-TbccSupMeltdownMode {
  <# Phase 2: under API-down backoff or host saturation, skip HTTP/WMI thrash; keep port/process LEDs. #>
  param($HostSnap = $null)
  if ($script:TbccSupHealthFailAt -and ((Get-Date) - $script:TbccSupHealthFailAt).TotalSeconds -lt 60) {
    return $true
  }
  if ($HostSnap) {
    if ($null -ne $HostSnap.CpuPct -and [double]$HostSnap.CpuPct -ge 82) { return $true }
    if ($null -ne $HostSnap.RamPct -and [double]$HostSnap.RamPct -ge 88) { return $true }
  }
  return $false
}

function Get-TbccSupCoreServiceIdSet {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack
  )
  $set = @{}
  foreach ($svc in @(Get-TbccStackServices -TbccRoot $TbccRoot -FullStack:$FullStack)) {
    if ($svc.Id) { $set[[string]$svc.Id] = $true }
  }
  return $set
}

function Get-TbccSupFilteredServiceIds {
  param($Cache, [string]$Filter, $CoreIdSet)
  if (-not $Cache -or -not $Cache.ById) { return @() }
  $ids = @($Cache.Services | ForEach-Object { [string]$_.Id })
  switch ($Filter) {
    'core' {
      if ($CoreIdSet) {
        $ids = @($ids | Where-Object { $CoreIdSet.ContainsKey($_) })
      }
    }
    'off' {
      $ids = @($ids | Where-Object {
          $row = $Cache.ById[$_]
          $row -and -not [bool]$row.UserEnabled
        })
    }
    'down' {
      $ids = @($ids | Where-Object {
          $row = $Cache.ById[$_]
          $row -and [bool]$row.UserEnabled -and [string]$row.Status -ne 'up'
        })
    }
    default { }
  }
  return $ids
}

function Invoke-TbccSupDisableOptionalServices {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    [scriptblock]$OnNotify
  )
  $core = Get-TbccSupCoreServiceIdSet -TbccRoot $TbccRoot -FullStack:$FullStack
  $n = 0
  foreach ($svc in @(Get-TbccStackServices -TbccRoot $TbccRoot -FullStack:$FullStack -MenuCatalog)) {
    $id = [string]$svc.Id
    if ($core.ContainsKey($id)) { continue }
    Set-TbccServiceUserEnabled -ServiceId $id -Enabled $false -TbccRoot $TbccRoot
    $n++
  }
  if ($OnNotify) { & $OnNotify ("Disabled $n optional services (core stack unchanged).") }
  return $n
}

function Invoke-TbccSupCycleSvcFilter {
  param($Ui)
  if (-not $Ui) { return 'all' }
  $order = @('all', 'core', 'down', 'off')
  $idx = [array]::IndexOf($order, [string]$Ui.SvcFilter)
  if ($idx -lt 0) { $idx = 0 } else { $idx = ($idx + 1) % $order.Count }
  $Ui.SvcFilter = $order[$idx]
  $Ui.SvcCellIdKey = $null
  return $Ui.SvcFilter
}

function Get-TbccSupervisorHealthSnapshot {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    $NetPrev = $null,
    [switch]$Lite
  )
  if ([string]::IsNullOrWhiteSpace($TbccRoot)) {
    throw "TbccRoot is required for health snapshot."
  }
  $now = Get-Date
  $snap = @{
    Cache         = $null
    Health        = $null
    HealthOk      = $false
    HealthErr     = $null
    HubLines      = @()
    OpsAlerts     = @()
    Ports         = $null
    ProcessAudit  = $null
    Host          = Get-TbccHostMetrics -NetPrev $NetPrev -Lite:$Lite
    UpdatedAt     = $now
    HeavyAt       = $now
    Meltdown      = $false
  }
  $meltdown = Test-TbccSupMeltdownMode -HostSnap $snap.Host
  $snap.Meltdown = $meltdown
  $cacheTtlSec = if ($meltdown) { 5 } else { 8 }
  # Mini path: host graphs every tick; stack/hub/API only every ~8s (reuse cache).
  $cacheFresh = $script:TbccSupSvcCache -and $script:TbccSupSvcCacheAt -and `
    (($now - $script:TbccSupSvcCacheAt).TotalSeconds -lt $cacheTtlSec)
  if (-not $cacheFresh -and -not $Lite) {
    try {
      $script:TbccSupSvcCache = Update-TbccServiceStatusCache -TbccRoot $TbccRoot -FullStack:$FullStack -MenuCatalog -Meltdown:$meltdown
      $script:TbccSupSvcCacheAt = $now
    } catch {}
  } elseif (-not $cacheFresh -and $Lite) {
    # Soften mini overload: defer heavy process enum unless cache is empty.
    if (-not $script:TbccSupSvcCache) {
      try {
        $script:TbccSupSvcCache = Update-TbccServiceStatusCache -TbccRoot $TbccRoot -FullStack:$FullStack -MenuCatalog -Meltdown:$meltdown
        $script:TbccSupSvcCacheAt = $now
      } catch {}
    }
  }
  $snap.Cache = $script:TbccSupSvcCache

  if ($Lite) {
    # Footer hub counts from a thin tail; skip netstat + health HTTP most ticks.
    $hubPath = Join-Path $TbccRoot ".tbcc-run\error-hub.log"
    $hubAgeOk = $script:TbccSupHubLiteAt -and (($now - $script:TbccSupHubLiteAt).TotalSeconds -lt 6)
    if ($hubAgeOk -and $script:TbccSupHubLiteLines) {
      $snap.HubLines = $script:TbccSupHubLiteLines
    } else {
      $snap.HubLines = @(Read-TbccErrorHubTail -Path $hubPath -MaxLines 24)
      $script:TbccSupHubLiteLines = $snap.HubLines
      $script:TbccSupHubLiteAt = $now
    }
    return $snap
  }

  if ($meltdown) {
    if ($snap.Cache -and $snap.Cache.Ports) {
      $snap.Ports = $snap.Cache.Ports
    } else {
      try { $snap.Ports = Get-TbccListeningPortSet } catch {}
    }
    $hubPath = Join-Path $TbccRoot ".tbcc-run\error-hub.log"
    $hubMeltdownFresh = $script:TbccSupHubMeltdownAt -and (($now - $script:TbccSupHubMeltdownAt).TotalSeconds -lt 10)
    if ($hubMeltdownFresh -and $script:TbccSupHubMeltdownLines) {
      $snap.HubLines = $script:TbccSupHubMeltdownLines
    } else {
      $snap.HubLines = @(Read-TbccErrorHubTail -Path $hubPath -MaxLines 20)
      $script:TbccSupHubMeltdownLines = $snap.HubLines
      $script:TbccSupHubMeltdownAt = $now
    }
    $snap.HealthOk = $false
    if ($script:TbccSupHealthFailAt) {
      $snap.HealthErr = "meltdown: API poll paused"
    } else {
      $snap.HealthErr = "meltdown: host hot (HTTP/WMI throttled)"
    }
    if ($script:TbccSupLastHealthSnap) {
      $snap.Health = $script:TbccSupLastHealthSnap.Health
    }
    return $snap
  }

  # Reuse the port set the service cache already scanned (dedup: was a 2nd netstat spawn
  # every heavy tick). Ports rarely flip inside the 8s cache window and this now runs
  # off the UI thread, so an up-to-8s-old infra LED is an acceptable trade for one fewer
  # subprocess under CPU pressure.
  if ($snap.Cache -and $snap.Cache.Ports) {
    $snap.Ports = $snap.Cache.Ports
  } else {
    try { $snap.Ports = Get-TbccListeningPortSet } catch {}
  }
  $hubPath = Join-Path $TbccRoot ".tbcc-run\error-hub.log"
  $snap.HubLines = @(Read-TbccErrorHubTail -Path $hubPath -MaxLines 56)
  $auditPath = Join-Path $TbccRoot ".tbcc-run\process-audit.json"
  if (Test-Path -LiteralPath $auditPath) {
    try {
      $snap.ProcessAudit = Get-Content -LiteralPath $auditPath -Raw -ErrorAction Stop | ConvertFrom-Json
    } catch {}
  }
  $inBackoff = $script:TbccSupHealthFailAt -and `
    (($now - $script:TbccSupHealthFailAt).TotalSeconds -lt 15)
  if ($inBackoff) {
    $snap.HealthErr = "API down (retrying shortly)"
  } else {
    try {
      $h = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health/system" -Method GET -TimeoutSec 2
      $snap.Health = $h
      $snap.HealthOk = $true
      if ($h.ok -eq $false) { $snap.HealthOk = $false }
      $script:TbccSupHealthFailAt = $null
      $script:TbccSupLastHealthSnap = @{ Health = $snap.Health }
    } catch {
      $snap.HealthErr = $_.Exception.Message
      $script:TbccSupHealthFailAt = $now
    }
    if ($snap.HealthOk) {
      try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:8000/ops/alerts/poll" -Method GET -TimeoutSec 2
        if ($r -and $r.alerts) {
          $snap.OpsAlerts = @($r.alerts)
          if ($script:TbccSupLastHealthSnap) { $script:TbccSupLastHealthSnap.OpsAlerts = $snap.OpsAlerts }
        }
      } catch {}
    }
  }
  return $snap
}

function Start-TbccSupSnapshotProducer {
  <#
    Off-thread acquisition. Dot-source service-control + this panel into a background MTA
    runspace and run the health-snapshot loop THERE, publishing pure-data snapshots to a
    synchronized latest-slot. The UI timer then only reads that slot and applies it — no
    netstat / Win32_Process WMI / /health HTTP ever runs on the STA message pump again, so
    a heavy acquisition can no longer freeze drag/paint. Both source files are pure
    function + $script:-const definitions (no side-effecting top-level code), which is what
    makes dot-sourcing them into a fresh runspace safe.
    Returns $true if the producer started; $false means the caller should fall back to the
    old synchronous in-tick snapshot (graceful degradation — a runspace fault never bricks
    the panel).
  #>
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    [int]$HostIntervalMs = 1200,
    [int]$HeavyIntervalMs = 4000
  )
  Stop-TbccSupSnapshotProducer   # never leave two producers hammering WMI at once

  $panelPath = $PSCommandPath
  if ([string]::IsNullOrWhiteSpace($panelPath) -or -not (Test-Path -LiteralPath $panelPath)) {
    return $false
  }
  if (-not $PSScriptRoot) { return $false }
  $svcCtlPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\scripts\tbcc-service-control.ps1"))
  if (-not (Test-Path -LiteralPath $svcCtlPath)) { return $false }

  $shared = [hashtable]::Synchronized(@{
    TbccRoot        = $TbccRoot
    FullStack       = [bool]$FullStack
    HostIntervalMs  = [int]$HostIntervalMs
    HeavyIntervalMs = [int]$HeavyIntervalMs
    Stop            = $false
    ForceRefresh    = $false
    Snapshot        = $null
    SnapshotAt      = $null
    StartedAt       = (Get-Date)
    Alive           = $false
    LastError       = $null
    Iterations      = 0
  })

  $producerBody = {
    param($Shared, $SvcCtlPath, $PanelPath)
    try {
      . $SvcCtlPath
      . $PanelPath
    } catch {
      $Shared.LastError = "load: " + $_.Exception.Message
      return
    }
    $Shared.Alive = $true
    $netPrev = $null
    $lastFull = $null
    $lastHeavyAt = [datetime]::MinValue
    $null = Get-TbccCpuPercentFast   # create+warm the CPU counter so the first snap has a value
    while (-not $Shared.Stop) {
      try {
        $now = Get-Date
        if ($Shared.ForceRefresh) {
          $Shared.ForceRefresh = $false
          $script:TbccSupSvcCache = $null
          $script:TbccSupSvcCacheAt = $null
          $lastHeavyAt = [datetime]::MinValue
        }
        $hostForMeltdown = if ($lastFull -and $lastFull.Host) { $lastFull.Host } else { $null }
        $meltdownLoop = Test-TbccSupMeltdownMode -HostSnap $hostForMeltdown
        $heavyIntervalMs = if ($meltdownLoop) {
          [Math]::Max(5000, [int]$Shared.HeavyIntervalMs)
        } else {
          [int]$Shared.HeavyIntervalMs
        }
        $doHeavy = (-not $lastFull) -or `
          (($now - $lastHeavyAt).TotalMilliseconds -ge [double]$heavyIntervalMs)
        if ($doHeavy) {
          $snap = Get-TbccSupervisorHealthSnapshot -TbccRoot $Shared.TbccRoot `
            -FullStack:([bool]$Shared.FullStack) -NetPrev $netPrev
          if ($snap.Host -and $snap.Host.Net) { $netPrev = $snap.Host.Net }
          $lastFull = $snap
          $lastHeavyAt = $now
        } else {
          # Cheap host-only refresh between heavy ticks so sparklines stay smooth; reuse
          # the last heavy sub-data (Cache/Hub/Health) by shallow-cloning the last snap.
          $hostM = Get-TbccHostMetrics -NetPrev $netPrev
          if ($hostM.Net) { $netPrev = $hostM.Net }
          $snap = @{}
          foreach ($k in $lastFull.Keys) { $snap[$k] = $lastFull[$k] }
          $snap.Host = $hostM
          $snap.UpdatedAt = $now
          $snap.HeavyAt = $lastFull.HeavyAt   # carry heavy stamp so UI diff skips rebuilds
        }
        # Stamp freshness at PUBLISH time, not at loop-start: a cold heavy acquisition can
        # take 6-8s (WMI cold + API-down HTTP timeouts), and stamping the start time would
        # mark a just-published snapshot as instantly stale and flash STALE spuriously.
        $Shared.Snapshot = $snap
        $Shared.SnapshotAt = Get-Date
        $Shared.Iterations = [int]$Shared.Iterations + 1
        $Shared.LastError = $null
      } catch {
        # One bad WMI/netstat call must not kill the loop forever — record and keep going.
        $Shared.LastError = $_.Exception.Message
      }
      Start-Sleep -Milliseconds ([int]$Shared.HostIntervalMs)
    }
    $Shared.Alive = $false
  }

  try {
    $rs = [runspacefactory]::CreateRunspace()
    $rs.ApartmentState = 'MTA'
    $rs.ThreadOptions = 'ReuseThread'
    $rs.Open()
    $ps = [powershell]::Create()
    $ps.Runspace = $rs
    [void]$ps.AddScript($producerBody).AddArgument($shared).AddArgument($svcCtlPath).AddArgument($panelPath)
    $handle = $ps.BeginInvoke()
    $script:TbccSupProducer = @{
      Shared     = $shared
      Runspace   = $rs
      PowerShell = $ps
      Handle     = $handle
    }
    return $true
  } catch {
    $script:TbccSupProducer = $null
    return $false
  }
}

function Stop-TbccSupSnapshotProducer {
  <# Signal the loop to exit, then force-stop and dispose the runspace so no orphan
     thread keeps hammering netstat/WMI after the window closes. #>
  $p = $script:TbccSupProducer
  $script:TbccSupProducer = $null
  if (-not $p) { return }
  try { if ($p.Shared) { $p.Shared.Stop = $true } } catch {}
  try { if ($p.PowerShell) { [void]$p.PowerShell.Stop() } } catch {}
  try { if ($p.PowerShell) { $p.PowerShell.Dispose() } } catch {}
  try { if ($p.Runspace) { $p.Runspace.Dispose() } } catch {}
}

function Get-TbccSupProducerSnapshot {
  <#
    Read the producer's latest published snapshot plus freshness metadata. Returns $null
    when no producer object exists at all (caller then runs a synchronous fallback).
    Staleness guards the async design's own failure mode: if the producer wedges (stuck
    netstat) or dies (loop fault), the UI would otherwise keep painting stale data with no
    visible freeze — so we surface age instead of lying.
  #>
  param([int]$StaleAfterSec = 8, [int]$InitGraceSec = 15)
  $p = $script:TbccSupProducer
  if (-not $p -or -not $p.Shared) { return $null }
  $shared = $p.Shared
  $snap = $shared.Snapshot
  $at = $shared.SnapshotAt
  $age = if ($at) { ((Get-Date) - $at).TotalSeconds } else { [double]::PositiveInfinity }
  # Classify so the UI tick can tell "still dot-sourcing the runspace" (skip + wait, do NOT
  # run the 6s synchronous snapshot on the pump) apart from "dead/wedged" (fall back + restart).
  $state = if ($snap) {
    "ready"
  } elseif ($shared.LastError -like "load:*") {
    "loadfailed"
  } elseif ($shared.StartedAt -and (((Get-Date) - $shared.StartedAt).TotalSeconds -lt $InitGraceSec)) {
    "initializing"
  } else {
    "wedged"
  }
  return @{
    Snap      = $snap
    AgeSec    = $age
    Stale     = ($age -gt $StaleAfterSec)
    Producing = [bool]$shared.Alive
    State     = $state
    LastError = $shared.LastError
  }
}

function Get-TbccDiamondMosaicShade {
  <# Champagne-LED style: base heat hue + per-gem luminance flutter (+ optional white sparkle). #>
  param(
    [System.Drawing.Color]$Base,
    [double]$Brightness = 1.0,
    [double]$Sparkle = 0.0
  )
  $b = [Math]::Max(0.28, [Math]::Min(1.35, $Brightness))
  $sp = [Math]::Max(0.0, [Math]::Min(1.0, $Sparkle))
  $r = [int][Math]::Round([Math]::Min(255, $Base.R * $b))
  $g = [int][Math]::Round([Math]::Min(255, $Base.G * $b))
  $bl = [int][Math]::Round([Math]::Min(255, $Base.B * $b))
  if ($sp -gt 0.02) {
    $r = [int][Math]::Round($r + (255 - $r) * $sp)
    $g = [int][Math]::Round($g + (255 - $g) * $sp)
    $bl = [int][Math]::Round($bl + (255 - $bl) * $sp)
  }
  return [System.Drawing.Color]::FromArgb($r, $g, $bl)
}

function Invoke-TbccSupPaintDiamondMetricBar {
  <# 3-row micro diamond mosaic (FYP–AOF glyph vibe) on pure black.
     Only lit gems painted — no empty placeholders. Calm drift; heat speeds flicker. #>
  param($Sender, $Graphics)
  $g = $Graphics
  $tag = $Sender.Tag
  $w = [Math]::Max(1, $Sender.Width)
  $h = [Math]::Max(1, $Sender.Height)
  $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
  $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
  # Pure black track — high contrast like the emoji sheets.
  $bgBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::Black)
  $g.FillRectangle($bgBrush, 0, 0, $w, $h)
  $bgBrush.Dispose()

  $pct = [double]$tag.Pct
  if ($pct -lt 0) { return }
  $pct = [Math]::Max(0.0, [Math]::Min(100.0, $pct))
  if ($pct -le 0.05) { return }

  $rows = 3
  # Micro gems: pack 3 rows flush in the track (tip-to-tip).
  $half = [int][Math]::Floor($h / (2.0 * $rows))
  if ($half -lt 2) { $half = 2 }
  if ($half -gt 3) { $half = 3 }
  $step = $half * 2
  $gridH = $step * $rows
  $y0 = [int][Math]::Floor(($h - $gridH) / 2.0) + $half
  # Flush left — first tip sits on x=0 so the fill matches the solid bars below.
  $cols = [Math]::Max(6, [int][Math]::Floor(($w - 0.5) / [double]$step))
  $lit = [int][Math]::Floor($cols * ($pct / 100.0) + 0.0001)
  if ($pct -gt 0 -and $lit -lt 1) { $lit = 1 }
  if ($lit -gt $cols) { $lit = $cols }

  # Heat northstar: calm baseline; hotter = faster (hard-capped below prior erratic rates).
  $heatT = $pct / 100.0
  $speed = 0.28 + 0.72 * [Math]::Pow($heatT, 1.35)
  if ($speed -gt 1.0) { $speed = 1.0 }
  $tick = [Environment]::TickCount / 1000.0
  $traj = 0.0
  if ($null -ne $tag.Trajectory) { $traj = [double]$tag.Trajectory }
  # Angular rates (rad/s-ish): ~5–10x slower than the first diamond pass.
  $flutterRate = 0.55 * $speed
  $spotRate = 0.32 * $speed
  $shadowRate = 0.38 * $speed
  $sparkRate = 0.85 * $speed
  # Percentage-anchored drift so patterns slowly walk with load.
  $drift = $tick * (0.12 + 0.22 * $heatT) + ($pct * 0.031)

  $gems = New-Object System.Collections.Generic.List[object]
  for ($r = 0; $r -lt $rows; $r++) {
    $rowPhase = $r * 2.15
    $cy = $y0 + ($r * $step)
    for ($i = 0; $i -lt $lit; $i++) {
      $cx = $half + ($i * $step)
      if ($cx + $half -gt $w) { break }
      $pts = @(
        [System.Drawing.Point]::new($cx, $cy - $half),
        [System.Drawing.Point]::new($cx + $half, $cy),
        [System.Drawing.Point]::new($cx, $cy + $half),
        [System.Drawing.Point]::new($cx - $half, $cy)
      )
      $localPct = [Math]::Min(100.0, $pct * (0.62 + 0.38 * (($i + 1.0) / [Math]::Max(1.0, $lit))))
      $base = if ($tag.InvertHeat) {
        Get-TbccHeatColor -Pct $localPct -Invert
      } else {
        Get-TbccHeatColor -Pct $localPct
      }
      # Darker overall tones vs emoji sheet (still heat-linked).
      $base = [System.Drawing.Color]::FromArgb(
        [int][Math]::Round($base.R * 0.78),
        [int][Math]::Round($base.G * 0.78),
        [int][Math]::Round($base.B * 0.78))

      $seed = (($i * 7919) + ($r * 104729) + 17) % 1000
      $phase = ($seed / 1000.0) * [Math]::PI * 2.0 + $rowPhase
      # Sparse "spots" — darker gems across the lit field (F-glyph negative space).
      $spotWave = 0.5 + 0.5 * [Math]::Sin($tick * $spotRate + $phase + $drift + $r * 0.9)
      $isSpot = ((($seed + [int]($drift * 7 + $r * 13)) % 100) -lt (14 + [int](8 * $heatT))) -or ($spotWave -gt 0.88)
      $flutter = 0.78 + 0.14 * [Math]::Sin($tick * $flutterRate + $phase + $drift * 0.6)
      if ($isSpot) { $flutter = 0.34 + 0.10 * [Math]::Sin($tick * $spotRate * 1.3 + $phase) }

      $edge = if ($lit -gt 1) { 1.0 - ([Math]::Abs($i - ($lit - 1)) / [Math]::Max(1.0, $lit * 0.4)) } else { 1.0 }
      $edge = [Math]::Max(0.0, [Math]::Min(1.0, $edge))
      $spark = $edge * (0.06 + 0.14 * [Math]::Max(0.0, $traj) + 0.10 * $heatT) *
        (0.4 + 0.6 * (0.5 + 0.5 * [Math]::Sin($tick * $sparkRate + $phase)))
      if ($isSpot) { $spark = 0 }

      $col = Get-TbccDiamondMosaicShade -Base $base -Brightness $flutter -Sparkle $spark
      $brush = New-Object System.Drawing.SolidBrush($col)
      $g.FillPolygon($brush, $pts)
      $brush.Dispose()
      [void]$gems.Add(@{ Pts = $pts; Row = $r; Phase = $phase })
    }
  }

  # Oscillating shadow wash, masked to diamond shapes — staggered per row, heat-timed.
  if ($gems.Count -gt 0) {
    foreach ($gem in $gems) {
      $row = [int]$gem.Row
      $shadowWave = 0.5 + 0.5 * [Math]::Sin($tick * $shadowRate + $gem.Phase + $drift + $row * 1.7)
      # Calm alpha band; hotter load lifts the ceiling a little (still soft).
      $alpha = [int][Math]::Round((18 + 28 * $shadowWave) * (0.55 + 0.45 * $speed))
      if ($alpha -lt 8) { $alpha = 8 }
      if ($alpha -gt 52) { $alpha = 52 }
      $shadowBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb($alpha, 0, 0, 0))
      $g.FillPolygon($shadowBrush, $gem.Pts)
      $shadowBrush.Dispose()
    }
  }
}

function New-TbccSupMetricBar {
  param(
    [string]$Label,
    [double]$Pct,
    $Theme,
    [System.Drawing.Color]$FillColor,
    [ValidateSet('Solid', 'Diamond')][string]$Style = 'Solid',
    [switch]$InvertHeat
  )
  $row = New-Object System.Windows.Forms.Panel
  $row.Height = $(if ($Style -eq 'Diamond') { 20 } else { 25 })
  $row.Dock = [System.Windows.Forms.DockStyle]::Top
  $row.Margin = New-Object System.Windows.Forms.Padding(0, 0, 0, 2)
  $row.BackColor = $Theme.ModuleBg

  $lbl = New-Object System.Windows.Forms.Label
  $lbl.Text = $Label
  # Diamond meters share the narrow "C/R" spark label width so tracks align flush left.
  $lbl.Width = $(if ($Style -eq 'Diamond') { 32 } else { 58 })
  $lbl.Dock = [System.Windows.Forms.DockStyle]::Left
  $lbl.ForeColor = $Theme.Muted
  $lbl.Font = $Theme.FontMicro
  $lbl.TextAlign = [System.Drawing.ContentAlignment]::MiddleLeft
  $row.Controls.Add($lbl)

  $barHost = New-Object System.Windows.Forms.Panel
  $barHost.Dock = [System.Windows.Forms.DockStyle]::Fill
  $barHost.BackColor = $(if ($Style -eq 'Diamond') { [System.Drawing.Color]::Black } else { $Theme.ModuleBg })
  $row.Controls.Add($barHost)

  $barH = if ($Style -eq 'Diamond') { 18 } else { 9 }
  $barBg = New-Object System.Windows.Forms.Panel
  $barBg.Height = $barH
  $barBg.Width = 100
  $barBg.BackColor = $(if ($Style -eq 'Diamond') { [System.Drawing.Color]::Black } else { $Theme.BarBg })
  $barBg.Tag = @{
    Pct         = $Pct
    Fill        = $FillColor
    Theme       = $Theme
    BarBg       = $barBg
    Row         = $row
    Style       = $Style
    InvertHeat  = [bool]$InvertHeat
    PrevPct     = $Pct
    Trajectory  = 0.0
  }
  if ($Style -eq 'Diamond') {
    $barBg.Add_Paint({
      param($sender, $e)
      try { Invoke-TbccSupPaintDiamondMetricBar -Sender $sender -Graphics $e.Graphics } catch {}
    })
  } else {
    $barBg.Add_Paint({
      param($sender, $e)
      $g = $e.Graphics
      $tag = $sender.Tag
      $w = $sender.Width
      $h = $sender.Height
      $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::None
      $bgBrush = New-Object System.Drawing.SolidBrush($tag.Theme.BarBg)
      $g.FillRectangle($bgBrush, 0, 0, $w, $h)
      $bgBrush.Dispose()
      $pct = [Math]::Max(0, [Math]::Min(100, [double]$tag.Pct))
      $fw = [int](($w - 1) * ($pct / 100.0))
      if ($fw -gt 0) {
        $fillBrush = New-Object System.Drawing.SolidBrush($tag.Fill)
        $g.FillRectangle($fillBrush, 0, 0, $fw, $h)
        $fillBrush.Dispose()
      }
    })
  }
  $barHost.Controls.Add($barBg)
  $isDiamond = ($Style -eq 'Diamond')
  $barHost.Add_Resize({
    param($s, $ev)
    foreach ($c in $s.Controls) {
      if ($c -is [System.Windows.Forms.Panel]) {
        # Diamond meters: full track width, flush left (match spark bars). Solid keeps legacy inset.
        if ($s.Tag -and $s.Tag.FullBleed) {
          $c.Width = [Math]::Max(40, $s.Width)
        } else {
          $c.Width = [Math]::Max(40, $s.Width - 44)
        }
        $c.Top = [int](($s.Height - $c.Height) / 2)
        $c.Left = 0
      }
    }
  }.GetNewClosure())
  if ($isDiamond) {
    $barHost.Tag = @{ FullBleed = $true }
  }

  $val = New-Object System.Windows.Forms.Label
  $val.Width = 36
  $val.Dock = [System.Windows.Forms.DockStyle]::Right
  $val.ForeColor = $Theme.Text
  $val.Font = $Theme.FontMicro
  $val.TextAlign = [System.Drawing.ContentAlignment]::MiddleRight
  if ($Pct -ge 0) { $val.Text = ("{0:N0}%" -f $Pct) } else { $val.Text = "-" }
  $row.Controls.Add($val)

  return @{ Row = $row; BarFill = $barBg }
}

function Set-TbccSupMetricBarValue {
  param($Bar, [double]$Pct, $Theme, $FillColor)
  if (-not $Bar) { return }
  $prev = if ($null -ne $Bar.Tag.PrevPct) { [double]$Bar.Tag.PrevPct } else { [double]$Bar.Tag.Pct }
  $delta = $Pct - $prev
  # Soft trajectory: rising load → sparkle at tip; falling → quieter.
  $traj = [Math]::Max(-1.0, [Math]::Min(1.0, $delta / 6.0))
  if ([Math]::Abs($traj) -lt 0.08) {
    $old = if ($null -ne $Bar.Tag.Trajectory) { [double]$Bar.Tag.Trajectory } else { 0.0 }
    $traj = $old * 0.72
  }
  $Bar.Tag.PrevPct = $Pct
  $Bar.Tag.Trajectory = $traj
  $Bar.Tag.Pct = $Pct
  $Bar.Tag.Fill = $FillColor
  $Bar.Invalidate()
  $row = $Bar.Tag.Row
  if ($row -and $row.Controls.Count -ge 3) {
    $row.Controls[2].Text = if ($Pct -ge 0) { ("{0:N0}%" -f $Pct) } else { "-" }
  }
}

function Start-TbccSupDiamondSparkleTimer {
  <# Lightweight Invalidate loop so mosaic flutter continues between host sample ticks. #>
  param($Ui)
  if (-not $Ui) { return }
  if ($script:TbccSupDiamondSparkleTimer -and -not $script:TbccSupDiamondSparkleTimer.Enabled) {
    try { $script:TbccSupDiamondSparkleTimer.Start() } catch {}
    return
  }
  if ($script:TbccSupDiamondSparkleTimer) { return }
  $t = New-Object System.Windows.Forms.Timer
  # Calm refresh — paint uses TickCount for drift; ~7fps is enough for therapeutic flutter.
  $t.Interval = 140
  [void]$t.Add_Tick({
    $ui = $script:TbccSupUi
    if (-not $ui -or -not $ui.HostBars) { return }
    $form = $script:TbccSupPanelForm
    if ($form -and (Test-TbccFormInteractionPaused -Form $form)) { return }
    foreach ($bar in @($ui.HostBars)) {
      if ($bar -and -not $bar.IsDisposed -and $bar.Tag -and $bar.Tag.Style -eq 'Diamond') {
        try { $bar.Invalidate() } catch {}
      }
    }
  })
  $script:TbccSupDiamondSparkleTimer = $t
  $t.Start()
}

function New-TbccSupLedRow {
  param(
    [string]$Label,
    [string]$Status,
    [string]$Detail,
    $Theme
  )
  $row = New-Object System.Windows.Forms.Panel
  $row.Height = 15
  $row.Dock = [System.Windows.Forms.DockStyle]::Top
  $row.BackColor = $Theme.ModuleBg

  $led = New-Object System.Windows.Forms.Panel
  $led.Size = New-Object System.Drawing.Size(9, 9)
  $led.Left = 2
  $led.Top = 3
  $color = switch ($Status) {
    "up" { $Theme.Ok }
    "warn" { $Theme.Warn }
    "crit" { $Theme.Crit }
    "off" { $Theme.Off }
    default { $Theme.Off }
  }
  $led.BackColor = $color
  $row.Controls.Add($led)

  $lbl = New-Object System.Windows.Forms.Label
  $lbl.Left = 14
  $lbl.Top = 0
  $lbl.Height = 15
  $lbl.AutoSize = $false
  $lbl.Width = 200
  $lbl.Text = $Label
  $lbl.ForeColor = $Theme.Text
  $lbl.Font = $Theme.FontMicro
  $row.Controls.Add($lbl)

  $det = New-Object System.Windows.Forms.Label
  $det.Dock = [System.Windows.Forms.DockStyle]::Right
  $det.Width = 120
  $det.TextAlign = [System.Drawing.ContentAlignment]::MiddleRight
  $det.Text = $Detail
  $det.ForeColor = $Theme.Muted
  $det.Font = $Theme.FontMicro
  $row.Controls.Add($det)

  # Expose mutable parts so callers can update the row in place (avoids destroy/recreate handle leaks).
  $row.Tag = @{ Led = $led; Label = $lbl; Detail = $det }
  return $row
}

function Update-TbccSupLedRow {
  # Update an existing LED row in place instead of recreating it on every refresh.
  param(
    $Row,
    [string]$Label,
    [string]$Status,
    [string]$Detail,
    $Theme
  )
  if (-not $Row -or -not $Row.Tag) { return }
  $color = switch ($Status) {
    "up" { $Theme.Ok }
    "warn" { $Theme.Warn }
    "crit" { $Theme.Crit }
    "off" { $Theme.Off }
    default { $Theme.Off }
  }
  if ($Row.Tag.Led -and $Row.Tag.Led.BackColor -ne $color) { $Row.Tag.Led.BackColor = $color }
  if ($Row.Tag.Label -and $Row.Tag.Label.Text -ne $Label) { $Row.Tag.Label.Text = $Label }
  if ($Row.Tag.Detail -and $Row.Tag.Detail.Text -ne $Detail) { $Row.Tag.Detail.Text = $Detail }
}

function Update-TbccSupPanelUi {
  param($Snap)
  $ui = $script:TbccSupUi
  if (-not $Snap -or -not $ui) { return }
  $t = $ui.Theme
  $cache = $Snap.Cache
  if ($cache) {
    $pct = if ($cache.Enabled -gt 0) { [double]$cache.EnabledUp / [double]$cache.Enabled * 100.0 } else { 0 }
    # Invert heat: high UP% = green, low UP% = red
    $fill = Get-TbccHeatColor -Pct $pct -Invert
    $ui.LblStackSum.Text = ("{0}/{1} up" -f $cache.EnabledUp, $cache.Enabled)
    $ui.LblStackSum.ForeColor = $fill
    Set-TbccSupMetricBarValue -Bar $ui.BarStack -Pct $pct -Theme $t -FillColor $fill
    $auditBit = ""
    if ($Snap.ProcessAudit) {
      $pa = $Snap.ProcessAudit
      $micro = if ($pa.summaryMicro) { [string]$pa.summaryMicro } else { "?" }
      if ([int]$pa.issueCount -gt 0) {
        $auditBit = " | aud " + $micro
      } else {
        $auditBit = " | aud ok"
      }
    }
    $ui.LblStackSub.Text = ("{0}/{1} on | {2} en{3} | {4}" -f $cache.Up, $cache.Total, $cache.Enabled, $auditBit, (Get-Date -Format "HH:mm:ss"))
    if ($Snap.ProcessAudit -and [int]$Snap.ProcessAudit.issueCount -gt 0) {
      $ui.LblStackSub.ForeColor = $t.Warn
    } else {
      $ui.LblStackSub.ForeColor = $t.Muted
    }
  }

  $hostSnap = $Snap.Host
  foreach ($bar in $ui.HostBars) {
    $key = [string]$bar.Tag.HostKey
    $v = if ($hostSnap.ContainsKey($key)) { $hostSnap[$key] } else { $null }
    $pct = if ($null -ne $v) { [double]$v } else { -1 }
    $fill = if ($pct -ge 0) { Get-TbccHeatColor -Pct $pct } else { $t.Muted }
    Set-TbccSupMetricBarValue -Bar $bar -Pct $pct -Theme $t -FillColor $fill
  }
  if ($hostSnap.Net) { $ui.NetPrev = $hostSnap.Net }
  $netLine = "NET -"
  if ($hostSnap.Net) {
    $netLine = ("dn {0} up {1}" -f (Format-TbccBitrate $hostSnap.Net.DownBps), (Format-TbccBitrate $hostSnap.Net.UpBps))
  }
  if ($hostSnap.RamUsedGb -and $hostSnap.RamTotalGb) {
    $ui.LblHostSub.Text = ("{0} | {1}/{2}G" -f $netLine, $hostSnap.RamUsedGb, $hostSnap.RamTotalGb)
  } else {
    $ui.LblHostSub.Text = $netLine
  }
  if ($null -ne $hostSnap.CpuPct) {
    Push-TbccSupSparklineSample -Canvas $ui.CpuSpark -Value ([double]$hostSnap.CpuPct)
    if ($ui.CpuSpark -and $ui.CpuSpark.Tag) {
      $ui.CpuSpark.Tag.LineColor = Get-TbccHeatColor -Pct ([double]$hostSnap.CpuPct)
    }
  }
  if ($null -ne $hostSnap.RamPct) {
    Push-TbccSupSparklineSample -Canvas $ui.RamSpark -Value ([double]$hostSnap.RamPct)
    if ($ui.RamSpark -and $ui.RamSpark.Tag) {
      $ui.RamSpark.Tag.LineColor = Get-TbccHeatColor -Pct ([double]$hostSnap.RamPct)
    }
  }

  Update-TbccSupMiniUi -Snap $Snap

  $health = $Snap.Health
  $rows = @()
  if ($Snap.HealthOk -and $health) {
    $apiSt = if ($health.ok) { "up" } else { "crit" }
    $rows += @{ L = "Health"; S = $apiSt; D = if ($health.ok) { "OK" } else { "!" } }
    if ($health.conflicts) {
      foreach ($c in @($health.conflicts)) {
        $sev = if ($c.severity) { [string]$c.severity } else { "warning" }
        $st = if ($sev -eq "critical") { "crit" } else { "warn" }
        $rows += @{ L = [string]$c.code; S = $st; D = "" }
      }
    }
    $focus = $health.focus
    if ($focus -and $focus.profile) {
      $fp = [string]$focus.profile
      $rows += @{ L = "Focus"; S = $(if ($fp -eq "off") { "up" } else { "warn" }); D = $fp }
    }
  } else {
    $rows += @{ L = "API"; S = "crit"; D = "down" }
  }
  foreach ($portPair in @(
      @{ L = ":8000"; P = 8000 },
      @{ L = ":5173"; P = 5173 },
      @{ L = ":6379"; P = 6379 },
      @{ L = ":5432"; P = 5432 }
    )) {
    $listening = $false
    if ($Snap.Ports) {
      try { $listening = $Snap.Ports.Contains([int]$portPair.P) } catch {}
    }
    $rows += @{ L = $portPair.L; S = $(if ($listening) { "up" } else { "off" }); D = "" }
  }
  # Reusable Infra row pool. Grow as needed, update in place, hide the surplus — never
  # Clear()/recreate, which leaked window handles every refresh.
  if ($null -eq $ui.InfraRows) { $ui.InfraRows = New-Object System.Collections.Generic.List[object] }
  for ($i = $ui.InfraRows.Count; $i -lt $rows.Count; $i++) {
    $newRow = New-TbccSupLedRow -Label "" -Status "off" -Detail "" -Theme $t
    $newRow.Width = 100
    $newRow.Height = 15
    [void]$ui.InfraRows.Add($newRow)
    [void]$ui.InfraPanel.Controls.Add($newRow)
  }
  for ($i = 0; $i -lt $ui.InfraRows.Count; $i++) {
    $poolRow = $ui.InfraRows[$i]
    if ($i -lt $rows.Count) {
      Update-TbccSupLedRow -Row $poolRow -Label $rows[$i].L -Status $rows[$i].S -Detail $rows[$i].D -Theme $t
      if (-not $poolRow.Visible) { $poolRow.Visible = $true }
    } elseif ($poolRow.Visible) {
      $poolRow.Visible = $false
    }
  }

  if ($cache -and $cache.ById) {
    $filter = if ($ui.SvcFilter) { [string]$ui.SvcFilter } else { 'all' }
    $ids = @(Get-TbccSupFilteredServiceIds -Cache $cache -Filter $filter -CoreIdSet $ui.SvcCoreIdSet)
    $idKey = ($filter + '|' + ($ids -join ','))
    if ($ui.ModSvcHeader) {
      $filterLbl = switch ($filter) {
        'core' { 'CORE' }
        'down' { 'DOWN' }
        'off' { 'OFF' }
        default { 'ALL' }
      }
      $ui.ModSvcHeader.Text = ("SERVICES {0} ({1})" -f $filterLbl, $ids.Count).ToUpper()
    }
    # Build the service cells once (keyed by id). Rebuild only when the service set itself
    # changes (rare) — never every tick — so the 2s refresh no longer leaks window handles.
    if ($ui.SvcCellIdKey -ne $idKey) {
      foreach ($old in @($ui.SvcGrid.Controls)) { $old.Dispose() }
      $ui.SvcGrid.Controls.Clear()
      $ui.SvcGrid.RowStyles.Clear()
      $ui.SvcGrid.RowCount = 0
      $ui.SvcCells = @{}
      $half = [Math]::Ceiling($ids.Count / 2.0)
      $ui.SvcGrid.RowCount = [Math]::Max(1, [int]$half)
      for ($ri = 0; $ri -lt $half; $ri++) {
        [void]$ui.SvcGrid.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 16)))
      }
      for ($i = 0; $i -lt $ids.Count; $i++) {
        $id = $ids[$i]
        $col = if ($i -lt $half) { 0 } else { 1 }
        $ri2 = if ($i -lt $half) { $i } else { $i - $half }
        $cell = New-TbccSupLedRow -Label "" -Status "off" -Detail "" -Theme $t
        $cell.Tag.Id = $id
        $onSvcClick = {
          param($sender, $e)
          if ($e.Button -ne [System.Windows.Forms.MouseButtons]::Left) { return }
          $tag = Get-TbccSupActionTag -Control $sender
          if (-not $tag -or -not $tag.Id) { return }
          $ctrl = ([System.Windows.Forms.Control]::ModifierKeys -band [System.Windows.Forms.Keys]::Control) -ne 0
          $u = $script:TbccSupUi
          try {
            Invoke-TbccServiceMenuAction -ServiceId $tag.Id -TbccRoot $u.TbccRoot -FullStack:([bool]$u.FullStack) -MenuCatalog `
              -ForceRestart:$ctrl -OnNotify $u.OnNotify
            # Force producer to refresh enabled/running state on the next loop.
            $script:TbccSupSvcCache = $null
            $script:TbccSupSvcCacheAt = $null
            if ($script:TbccSupProducer -and $script:TbccSupProducer.Shared) {
              $script:TbccSupProducer.Shared.ForceRefresh = $true
            }
            if ($u.OnRefreshCache) { & $u.OnRefreshCache }
          } catch {
            if ($u.OnNotify) { & $u.OnNotify ("Service action failed: " + $_.Exception.Message) }
          }
        }.GetNewClosure()
        Register-TbccSupSubtreeMouseClick -Control $cell -Handler $onSvcClick
        Register-TbccWheelScroll -Control $cell
        if ($ui.Tip) {
          $row0 = $cache.ById[$id]
          if ($row0) {
            $tipTxt = Get-TbccServiceMenuTooltip -Service $row0.Service -Status ([string]$row0.Status) -UserEnabled:([bool]$row0.UserEnabled)
            $ui.Tip.SetToolTip($cell, $tipTxt)
            if ($cell.Tag.Label) { $ui.Tip.SetToolTip($cell.Tag.Label, $tipTxt) }
            if ($cell.Tag.Detail) { $ui.Tip.SetToolTip($cell.Tag.Detail, $tipTxt) }
            if ($cell.Tag.Led) { $ui.Tip.SetToolTip($cell.Tag.Led, $tipTxt) }
          } else {
            $ui.Tip.SetToolTip($cell, "Click: enable/disable | Ctrl+click: restart")
          }
        }
        [void]$ui.SvcGrid.Controls.Add($cell, $col, $ri2)
        $ui.SvcCells[$id] = $cell
      }
      $ui.SvcCellIdKey = $idKey
      Hide-TbccControlScrollBars -Control $ui.SvcGrid
    }
    # Update existing cells in place every tick (no control churn, no handle growth).
    for ($i = 0; $i -lt $ids.Count; $i++) {
      $id = $ids[$i]
      $row = $cache.ById[$id]
      if (-not $row) { continue }
      $cell = $ui.SvcCells[$id]
      if (-not $cell) { continue }
      $svc = $row.Service
      $st = [string]$row.Status
      $en = [bool]$row.UserEnabled
      $ledSt = if (-not $en) { "off" } elseif ($st -eq "up") { "up" } else { "crit" }
      $det = if (-not $en) { "off" } elseif ($st -eq "up") { "UP" } else { "DN" }
      $label = Get-TbccServicePanelShortLabel -Service $svc
      $cell.Tag.Service = $svc
      Update-TbccSupLedRow -Row $cell -Label $label -Status $ledSt -Detail $det -Theme $t
      if ($ui.Tip) {
        $tipTxt = Get-TbccServiceMenuTooltip -Service $svc -Status $st -UserEnabled:$en
        $ui.Tip.SetToolTip($cell, $tipTxt)
      }
    }
  }

  # Count severities every tick (cheap), but only rebuild the ListBox when the hub tail
  # actually changed — the applier now runs ~1.2s and Clear()+Add()+owner-draw repaint is
  # the expensive part. Signature = count + sev tallies + last line text.
  $hubCrit = 0
  $hubWarn = 0
  $hubLastTxt = ""
  foreach ($entry in @($Snap.HubLines)) {
    $line = Get-TbccHubEntryText -Entry $entry
    $sev = Get-TbccHubLineSeverity -Line $line
    if ($sev -eq "crit") { $hubCrit++ } elseif ($sev -eq "warn") { $hubWarn++ }
    $hubLastTxt = $line
  }
  $hubSig = ("{0}|{1}|{2}|{3}" -f @($Snap.HubLines).Count, $hubCrit, $hubWarn, $hubLastTxt)
  if ($ui.LastHubSig -ne $hubSig) {
    $ui.HubList.Items.Clear()
    foreach ($entry in @($Snap.HubLines)) {
      $line = Get-TbccHubEntryText -Entry $entry
      if ($entry.LineNumber) {
        [void]$ui.HubList.Items.Add($entry)
      } else {
        [void]$ui.HubList.Items.Add($line)
      }
    }
    if ($ui.HubList.Items.Count -gt 0) {
      $ui.HubList.TopIndex = [Math]::Max(0, $ui.HubList.Items.Count - 1)
    }
    if ($ui.ModHubHeader) {
      $ui.ModHubHeader.Text = ("HUB {0}w {1}c" -f $hubWarn, $hubCrit).ToUpper()
      $hubHeat = if ($hubCrit -gt 0) { [Math]::Min(100, 82 + $hubCrit * 4) } elseif ($hubWarn -gt 0) { [Math]::Min(78, 48 + $hubWarn * 2) } else { 12 }
      $ui.ModHubHeader.ForeColor = Get-TbccHeatColor -Pct $hubHeat
    }
    $ui.LastHubSig = $hubSig
  }

  # Build the alert lines first, then only touch the ListBox if they changed (same
  # rebuild-only-on-diff rule as the hub list, so the fast applier tick stays cheap).
  $alertItems = New-Object System.Collections.Generic.List[string]
  if ($Snap.HealthOk -and $health -and $health.conflicts) {
    foreach ($c in @($health.conflicts)) {
      $sev = if ($c.severity) { [string]$c.severity.ToUpper() } else { "WARN" }
      $msg = if ($c.message) { [string]$c.message } else { [string]$c.code }
      if ($msg.Length -gt 80) { $msg = $msg.Substring(0, 77) + "..." }
      [void]$alertItems.Add(("[$sev] {0}" -f $msg))
    }
  } elseif ($Snap.HealthErr) {
    if ($Snap.Meltdown -and [string]$Snap.HealthErr -match '^meltdown:') {
      $throttleMsg = [string]$Snap.HealthErr -replace '^meltdown:\s*', ''
      [void]$alertItems.Add(("[WARN] Throttle - {0}" -f $throttleMsg))
    } else {
      [void]$alertItems.Add("[CRIT] API down")
    }
  } else {
    [void]$alertItems.Add("No conflicts")
  }
  if ($health -and $health.recommendations) {
    foreach ($rec in @($health.recommendations)) {
      $r = [string]$rec
      if ($r.Length -gt 80) { $r = $r.Substring(0, 77) + "..." }
      [void]$alertItems.Add("-> " + $r)
    }
  }
  foreach ($a in @($Snap.OpsAlerts)) {
    if (-not $a) { continue }
    $sev = if ($a.severity) { [string]$a.severity.ToUpper() } else { "WARN" }
    if ($sev -eq "INFO") { continue }
    $title = if ($a.title) { [string]$a.title } else { "Alert" }
    [void]$alertItems.Add(("[$sev] {0}" -f $title))
  }
  $alertSig = ($alertItems -join "`n")
  if ($ui.LastAlertSig -ne $alertSig) {
    $ui.AlertList.Items.Clear()
    foreach ($it in $alertItems) { [void]$ui.AlertList.Items.Add($it) }
    $ui.LastAlertSig = $alertSig
  }

  $overallHeat = if ($hubCrit -gt 0 -or ($Snap.HealthOk -and $health -and -not $health.ok)) { 90 }
    elseif ($hubWarn -gt 0) { 58 }
    elseif ($cache -and $cache.Enabled -gt 0) { 100.0 - ([double]$cache.EnabledUp / [double]$cache.Enabled * 100.0) }
    else { 40 }
  $overall = Get-TbccHeatColor -Pct $overallHeat
  if ($ui.StatusLbl) {
    $stamp = Get-Date -Format "HH:mm:ss"
    if ($Snap.Meltdown) {
      $ms = Get-TbccSupMeltdownStyle -Snap $Snap
      $ui.StatusLbl.Text = ("{0} | {1} | {2}" -f $ms.Prefix, $stamp, $ui.TbccRoot)
      $ui.StatusLbl.ForeColor = Get-TbccHeatColor -Pct $ms.HeatPct
    } else {
      $ui.StatusLbl.Text = ("{0} | {1}" -f $stamp, $ui.TbccRoot)
      $ui.StatusLbl.ForeColor = $ui.Theme.Muted
    }
  }
  $ui.LblStackSum.ForeColor = $overall
}

function Show-TbccSupervisorMiniPanel {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    [scriptblock]$OnNotify,
    [scriptblock]$OnRefreshCache
  )

  try { $TbccRoot = Resolve-TbccSupervisorRoot -TbccRoot $TbccRoot } catch {
    if ($OnNotify) { & $OnNotify $_.Exception.Message }
    return
  }

  # Full panel + mini both ticking on the UI thread = freeze/static sparks. Park the big one.
  if ($script:TbccSupPanelForm -and -not $script:TbccSupPanelForm.IsDisposed) {
    try {
      if ($script:TbccSupPanelRefreshTimer) { $script:TbccSupPanelRefreshTimer.Stop() }
      $script:TbccSupPanelForm.Hide()
    } catch {}
  }

  if ($script:TbccSupMiniForm -and -not $script:TbccSupMiniForm.IsDisposed) {
    $ui = $script:TbccSupMiniUi
    if ($ui -and $ui.ChkPin) {
      Set-TbccFormAlwaysOnTop -Form $script:TbccSupMiniForm -Enabled:([bool]$ui.ChkPin.Checked)
    }
    try {
      if ($script:TbccSupMiniForm.WindowState -eq [System.Windows.Forms.FormWindowState]::Minimized) {
        $script:TbccSupMiniForm.WindowState = [System.Windows.Forms.FormWindowState]::Normal
      }
      [void]$script:TbccSupMiniForm.Show()
      # Restart the off-thread producer (full panel may have parked/replaced it).
      [void](Start-TbccSupSnapshotProducer -TbccRoot $TbccRoot -FullStack:$FullStack)
      if ($script:TbccSupMiniRefreshTimer -and -not $script:TbccSupMiniRefreshTimer.Enabled) {
        $script:TbccSupMiniRefreshTimer.Start()
      }
    } catch {}
    return
  }

  $theme = Get-TbccSupervisorTheme
  $tip = New-Object System.Windows.Forms.ToolTip
  $tip.ShowAlways = $true

  $form = New-TbccSupervisorForm
  $form.Text = "TBCC Mini"
  Register-TbccFormChrome -Form $form
  $form.AutoScaleMode = [System.Windows.Forms.AutoScaleMode]::None
  $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::Sizable
  $form.MaximizeBox = $false
  $form.MinimizeBox = $true
  $form.ClientSize = New-Object System.Drawing.Size(391, 124)
  $form.MinimumSize = New-Object System.Drawing.Size(320, 110)
  $form.BackColor = $theme.Bg
  $form.ForeColor = $theme.Text
  $form.Font = $theme.FontMicro
  $form.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
  $form.Location = New-Object System.Drawing.Point(40, 40)
  $form.TopMost = $true
  $form.ShowInTaskbar = $true

  $toolRow = New-Object System.Windows.Forms.Panel
  $toolRow.Dock = [System.Windows.Forms.DockStyle]::Top
  $toolRow.Height = 21
  $toolRow.BackColor = $theme.HeaderBg
  $form.Controls.Add($toolRow)

  $chkPin = New-Object System.Windows.Forms.CheckBox
  $chkPin.Text = "Pin"
  $chkPin.Checked = $true
  $chkPin.AutoSize = $true
  $chkPin.Left = 4
  $chkPin.Top = 2
  $chkPin.ForeColor = $theme.Muted
  $chkPin.Font = $theme.FontMicro
  $chkPin.BackColor = $theme.HeaderBg
  [void]$chkPin.Add_CheckedChanged({
    param($sender, $e)
    $f = $script:TbccSupMiniForm
    if ($f -and -not $f.IsDisposed) {
      Set-TbccFormAlwaysOnTop -Form $f -Enabled:([bool]$sender.Checked)
    }
    $ui = $script:TbccSupMiniUi
    if ($ui -and $ui.MiPin) { $ui.MiPin.Checked = [bool]$sender.Checked }
  })
  $toolRow.Controls.Add($chkPin)

  $btnMin = New-Object System.Windows.Forms.Button
  $btnMin.Text = "_"
  $btnMin.Width = 26
  $btnMin.Height = 18
  $btnMin.Top = 1
  $btnMin.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
  $btnMin.BackColor = $theme.ModuleBg
  $btnMin.ForeColor = $theme.Text
  $btnMin.Font = $theme.FontMicro
  [void]$btnMin.Add_Click({
    $f = $script:TbccSupMiniForm
    if ($f -and -not $f.IsDisposed) { $f.WindowState = [System.Windows.Forms.FormWindowState]::Minimized }
  })
  $toolRow.Controls.Add($btnMin)
  $btnMin.Add_Resize({ $btnMin.Left = $toolRow.Width - 32 }) | Out-Null
  [void]$toolRow.Add_Resize({ $btnMin.Left = [Math]::Max(4, $toolRow.Width - 32) })

  $root = New-Object System.Windows.Forms.TableLayoutPanel
  $root.Dock = [System.Windows.Forms.DockStyle]::Fill
  $root.BackColor = $theme.Bg
  $root.RowCount = 3
  $root.ColumnCount = 1
  [void]$root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 21)))
  [void]$root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 55)))
  [void]$root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 18)))
  $form.Controls.Add($root)

  $hdr = New-Object System.Windows.Forms.Panel
  $hdr.Dock = [System.Windows.Forms.DockStyle]::Fill
  $hdr.BackColor = $theme.HeaderBg
  $lblTitle = New-Object System.Windows.Forms.Label
  $lblTitle.Text = "TBCC SUPERVISOR"
  $lblTitle.ForeColor = $theme.Muted
  $lblTitle.Font = $theme.FontHeader
  $lblTitle.Left = 6
  $lblTitle.Top = 2
  $lblTitle.AutoSize = $true
  $hdr.Controls.Add($lblTitle)
  $lblStack = New-Object System.Windows.Forms.Label
  $lblStack.Dock = [System.Windows.Forms.DockStyle]::Right
  $lblStack.Width = 130
  $lblStack.TextAlign = [System.Drawing.ContentAlignment]::MiddleRight
  $lblStack.ForeColor = $theme.Ok
  $lblStack.Font = $theme.FontMicro
  $lblStack.Text = "-"
  $hdr.Controls.Add($lblStack)
  [void]$root.Controls.Add($hdr, 0, 0)

  $sparkRow = New-Object System.Windows.Forms.Panel
  $sparkRow.Dock = [System.Windows.Forms.DockStyle]::Fill
  $sparkRow.BackColor = $theme.ModuleBg
  $cpuSpark = New-TbccSupSparkline -Label "CPU" -Theme $theme -LineColor $theme.Ok -RowHeight 28
  $cpuSpark.Wrap.Dock = [System.Windows.Forms.DockStyle]::Top
  $ramSpark = New-TbccSupSparkline -Label "RAM" -Theme $theme -LineColor ([System.Drawing.Color]::FromArgb(96, 165, 250)) -RowHeight 28
  $ramSpark.Wrap.Dock = [System.Windows.Forms.DockStyle]::Fill
  $sparkRow.Controls.Add($ramSpark.Wrap)
  $sparkRow.Controls.Add($cpuSpark.Wrap)
  [void]$root.Controls.Add($sparkRow, 0, 1)

  $foot = New-Object System.Windows.Forms.Label
  $foot.Dock = [System.Windows.Forms.DockStyle]::Fill
  $foot.BackColor = $theme.ModuleBg
  $foot.ForeColor = $theme.Muted
  $foot.Font = $theme.FontMicro
  $foot.TextAlign = [System.Drawing.ContentAlignment]::MiddleLeft
  $foot.Padding = New-Object System.Windows.Forms.Padding(6, 0, 0, 0)
  $foot.Text = "HUB -/-  |  NET -"
  [void]$root.Controls.Add($foot, 0, 2)

  $ctx = New-Object System.Windows.Forms.ContextMenuStrip
  $miStart = New-Object System.Windows.Forms.ToolStripMenuItem
  $miStart.Text = "Start stack"
  [void]$miStart.Add_Click({
    $ui = $script:TbccSupMiniUi
    if (-not $ui -or [string]::IsNullOrWhiteSpace($ui.TbccRoot)) { return }
    try {
      if (Get-Command Invoke-TbccStackLaunch -ErrorAction SilentlyContinue) {
        Invoke-TbccStackLaunch -TbccRoot $ui.TbccRoot
        if ($ui.OnNotify) { & $ui.OnNotify "Stack launch started." }
      } elseif (Get-Command Invoke-TbccLeanStackLaunch -ErrorAction SilentlyContinue) {
        Invoke-TbccLeanStackLaunch -TbccRoot $ui.TbccRoot
        if ($ui.OnNotify) { & $ui.OnNotify "Stack launch started." }
      } elseif ($ui.OnNotify) {
        & $ui.OnNotify "Stack launch unavailable (reload supervisor)."
      }
    } catch {
      if ($ui.OnNotify) { & $ui.OnNotify ("Stack launch failed: " + $_.Exception.Message) }
    }
  }.GetNewClosure())
  [void]$ctx.Items.Add($miStart)
  [void]$ctx.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))
  $miExpand = New-Object System.Windows.Forms.ToolStripMenuItem
  $miExpand.Text = "Open full panel"
  [void]$miExpand.Add_Click({
    $ui = $script:TbccSupMiniUi
    if (-not $ui) { return }
    Show-TbccSupervisorPanel -TbccRoot $ui.TbccRoot -FullStack:([bool]$ui.FullStack) `
      -OnNotify $ui.OnNotify -OnRefreshCache $ui.OnRefreshCache
  }.GetNewClosure())
  [void]$ctx.Items.Add($miExpand)
  $miPin = New-Object System.Windows.Forms.ToolStripMenuItem
  $miPin.Text = "Always on top"
  $miPin.Checked = $true
  [void]$miPin.Add_Click({
    $ui = $script:TbccSupMiniUi
    $f = $script:TbccSupMiniForm
    if (-not $f -or $f.IsDisposed) { return }
    $next = -not $f.TopMost
    Set-TbccFormAlwaysOnTop -Form $f -Enabled:$next
    if ($ui -and $ui.ChkPin) { $ui.ChkPin.Checked = $next }
    $miPin.Checked = $next
  }.GetNewClosure())
  [void]$ctx.Items.Add($miPin)
  [void]$ctx.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))
  $miClose = New-Object System.Windows.Forms.ToolStripMenuItem
  $miClose.Text = "Close mini"
  [void]$miClose.Add_Click({ $form.Close() }.GetNewClosure())
  [void]$ctx.Items.Add($miClose)
  $form.ContextMenuStrip = $ctx

  $script:TbccSupMiniUi = @{
    Form      = $form
    LblStack  = $lblStack
    CpuSpark  = $cpuSpark.Canvas
    RamSpark  = $ramSpark.Canvas
    Foot      = $foot
    Theme     = $theme
    Tip       = $tip
    NetPrev   = $null
    LastNetTxt = "NET -"
    ChkPin    = $chkPin
    MiPin     = $miPin
    TbccRoot  = $TbccRoot
    FullStack = [bool]$FullStack
    OnNotify  = $OnNotify
    OnRefreshCache = $OnRefreshCache
    TickN     = 0
  }

  if ($script:TbccSupMiniRefreshTimer) {
    try { $script:TbccSupMiniRefreshTimer.Stop(); $script:TbccSupMiniRefreshTimer.Dispose() } catch {}
    $script:TbccSupMiniRefreshTimer = $null
  }
  $script:TbccSupMiniRefreshTimer = New-Object System.Windows.Forms.Timer
  $miniTimer = $script:TbccSupMiniRefreshTimer
  # Host sparks every ~1.2s; lite snapshot avoids WMI/HTTP thrash that felt like "overload".
  $miniTimer.Interval = 1200
  $script:TbccSupMiniClosing = $false
  [void]$miniTimer.Add_Tick({
    if ($script:TbccSupMiniClosing) { return }
    if (-not $script:TbccSupMiniForm -or $script:TbccSupMiniForm.IsDisposed) { return }
    if (Test-TbccFormInteractionPaused -Form $script:TbccSupMiniForm) { return }
    # Only skip if the FULL panel is visible (both open) — hidden full panel is OK.
    if ($script:TbccSupPanelForm -and -not $script:TbccSupPanelForm.IsDisposed -and $script:TbccSupPanelForm.Visible) {
      return
    }
    if ($script:TbccSupMiniBusy) { return }
    $script:TbccSupMiniBusy = $true
    try {
      $ui = $script:TbccSupMiniUi
      if (-not $ui -or [string]::IsNullOrWhiteSpace($ui.TbccRoot)) { return }
      $ui.TickN = [int]$ui.TickN + 1
      if ($script:TbccSupMiniRefreshTimer -and $script:TbccSupMiniRefreshTimer.Interval -ne 1200) {
        $script:TbccSupMiniRefreshTimer.Interval = 1200
      }
      # Read the off-thread producer; fall back to a synchronous lite snap only if it's
      # absent or dead/wedged (self-heal by (re)starting) — never while it is still
      # dot-sourcing, so a cold open doesn't freeze the pump. No WMI/netstat on the pump.
      $prod = Get-TbccSupProducerSnapshot
      $snap = $null
      $stale = $false
      if ($prod -and $prod.Snap) {
        $snap = $prod.Snap
        $stale = [bool]$prod.Stale
      } elseif ($null -eq $prod -or ($prod.State -ne "initializing")) {
        $snap = Get-TbccSupervisorHealthSnapshot -TbccRoot $ui.TbccRoot -FullStack:([bool]$ui.FullStack) `
          -NetPrev $ui.NetPrev -Lite
        [void](Start-TbccSupSnapshotProducer -TbccRoot $ui.TbccRoot -FullStack:([bool]$ui.FullStack))
      }
      # else: producer initializing (dot-sourcing) — skip apply this tick, let it come up.
      if ($snap) {
        Update-TbccSupMiniUi -Snap $snap
        if ($stale -and $script:TbccSupMiniUi -and $script:TbccSupMiniUi.Foot) {
          $script:TbccSupMiniUi.Foot.Text = ("STALE {0}s | {1}" -f [int]$prod.AgeSec, $script:TbccSupMiniUi.Foot.Text)
          $script:TbccSupMiniUi.Foot.ForeColor = $ui.Theme.Warn
        }
        if ($ui.OnRefreshCache -and $snap.Cache -and (($ui.TickN % 6) -eq 0)) {
          & $ui.OnRefreshCache $snap.Cache
        }
      }
      if ($ui.ChkPin -and $ui.ChkPin.Checked) {
        Set-TbccFormAlwaysOnTop -Form $script:TbccSupMiniForm -Enabled:$true
      }
    } catch {} finally {
      $script:TbccSupMiniBusy = $false
    }
  })

  $form.Add_FormClosing({
    $script:TbccSupMiniClosing = $true
    $t = $script:TbccSupMiniRefreshTimer
    if ($t) { $t.Stop() }
  })
  $form.Add_FormClosed({
    $script:TbccSupMiniClosing = $true
    Stop-TbccSupSnapshotProducer
    $t = $script:TbccSupMiniRefreshTimer
    if ($t) {
      try { $t.Stop() } catch {}
      try { $t.Dispose() } catch {}
      $script:TbccSupMiniRefreshTimer = $null
    }
    $ui = $script:TbccSupMiniUi
    if ($ui -and $ui.Tip) {
      try { $ui.Tip.Dispose() } catch {}
    }
    $script:TbccSupMiniForm = $null
    $script:TbccSupMiniUi = $null
  })

  $form.Add_Activated({
    $ui = $script:TbccSupMiniUi
    if ($ui -and $ui.ChkPin -and $ui.ChkPin.Checked) {
      Set-TbccFormAlwaysOnTop -Form $script:TbccSupMiniForm -Enabled:$true
    }
  })

  $form.Add_Load({
    $t = $script:TbccSupMiniRefreshTimer
    if (-not $t) { return }
    $null = Get-TbccCpuPercentFast  # warm counter so first live tick isn't null forever
    $u = $script:TbccSupMiniUi
    if ($u) {
      [void](Start-TbccSupSnapshotProducer -TbccRoot $u.TbccRoot -FullStack:([bool]$u.FullStack))
    }
    $t.Interval = 200
    $t.Start()
  })

  [void]$form.Add_MouseDoubleClick({
    $ui = $script:TbccSupMiniUi
    if (-not $ui -or [string]::IsNullOrWhiteSpace($ui.TbccRoot)) { return }
    Show-TbccSupervisorPanel -TbccRoot $ui.TbccRoot -FullStack:([bool]$ui.FullStack) `
      -OnNotify $ui.OnNotify -OnRefreshCache $ui.OnRefreshCache
  })

  $tip.SetToolTip($chkPin, "Always on top + keep active title color (Pin)")
  $tip.SetToolTip($btnMin, "Minimize to taskbar")
  $tip.SetToolTip($form, "Double-click / menu: full panel | Pin keeps mini above other windows")
  $script:TbccSupMiniForm = $form
  try {
    [void]$form.Show()
    Set-TbccFormAlwaysOnTop -Form $form -Enabled:$true
    $form.BringToFront()
  } catch {
    if ($OnNotify) { & $OnNotify ("Mini panel open failed: " + $_.Exception.Message) }
    $script:TbccSupMiniForm = $null
    $script:TbccSupMiniUi = $null
  }
}

function Update-TbccSupMiniUi {
  param($Snap)
  if (-not $script:TbccSupMiniUi -or -not $script:TbccSupMiniForm -or $script:TbccSupMiniForm.IsDisposed) { return }
  if (-not $Snap) { return }
  $t = $script:TbccSupMiniUi.Theme
  $cache = $Snap.Cache
  if ($cache) {
    $pct = if ($cache.Enabled -gt 0) { [double]$cache.EnabledUp / [double]$cache.Enabled * 100.0 } else { 0 }
    $fill = Get-TbccHeatColor -Pct $pct -Invert
    $auditBit = ""
    if ($Snap.ProcessAudit -and [int]$Snap.ProcessAudit.issueCount -gt 0) {
      $micro = if ($Snap.ProcessAudit.summaryMicro) { [string]$Snap.ProcessAudit.summaryMicro } else { "!" }
      $auditBit = " | " + $micro
      $fill = Get-TbccHeatColor -Pct 62
    }
    $script:TbccSupMiniUi.LblStack.Text = ("{0}/{1} up{2}" -f $cache.EnabledUp, $cache.Enabled, $auditBit)
    $script:TbccSupMiniUi.LblStack.ForeColor = $fill
  }
  $hostSnap = $Snap.Host
  $cpuPct = -1.0
  if ($null -ne $hostSnap.CpuPct) {
    $cpuPct = [double]$hostSnap.CpuPct
    Push-TbccSupSparklineSample -Canvas $script:TbccSupMiniUi.CpuSpark -Value $cpuPct
    if ($script:TbccSupMiniUi.CpuSpark -and $script:TbccSupMiniUi.CpuSpark.Tag) {
      $script:TbccSupMiniUi.CpuSpark.Tag.LineColor = Get-TbccHeatColor -Pct $cpuPct
    }
  }
  if ($null -ne $hostSnap.RamPct) {
    $ramPct = [double]$hostSnap.RamPct
    Push-TbccSupSparklineSample -Canvas $script:TbccSupMiniUi.RamSpark -Value $ramPct
    if ($script:TbccSupMiniUi.RamSpark -and $script:TbccSupMiniUi.RamSpark.Tag) {
      $script:TbccSupMiniUi.RamSpark.Tag.LineColor = Get-TbccHeatColor -Pct $ramPct
    }
  }
  $hubCrit = 0
  $hubWarn = 0
  foreach ($entry in @($Snap.HubLines)) {
    $txt = Get-TbccHubEntryText -Entry $entry
    $sev = Get-TbccHubLineSeverity -Line $txt
    if ($sev -eq "crit") { $hubCrit++ } elseif ($sev -eq "warn") { $hubWarn++ }
  }
  $netTxt = $script:TbccSupMiniUi.LastNetTxt
  if (-not $netTxt) { $netTxt = "NET -" }
  if ($hostSnap.Net) {
    $netTxt = ("NET dn {0} up {1}" -f (Format-TbccBitrate $hostSnap.Net.DownBps), (Format-TbccBitrate $hostSnap.Net.UpBps))
    $script:TbccSupMiniUi.LastNetTxt = $netTxt
  }
  # Footer color tracks CPU heat; hub pressure only pushes toward red when urgent.
  $heat = if ($cpuPct -ge 0) { $cpuPct } else { 20 }
  if ($hubWarn -gt 0) { $heat = [Math]::Max($heat, [Math]::Min(72, 48 + $hubWarn)) }
  if ($hubCrit -gt 0) { $heat = [Math]::Max($heat, [Math]::Min(100, 84 + $hubCrit * 4)) }
  $script:TbccSupMiniUi.Foot.Text = ("HUB {0}w {1}c  |  {2}" -f $hubWarn, $hubCrit, $netTxt)
  if ($Snap.Meltdown) {
    $ms = Get-TbccSupMeltdownStyle -Snap $Snap
    $script:TbccSupMiniUi.Foot.Text = ($ms.MiniPrefix + " | " + $script:TbccSupMiniUi.Foot.Text)
    if ($hubCrit -eq 0) {
      $heat = [Math]::Min(68, [Math]::Max($heat, $ms.HeatPct))
    }
  }
  $script:TbccSupMiniUi.Foot.ForeColor = Get-TbccHeatColor -Pct $heat
  if ($script:TbccSupMiniUi.Tip -and $script:TbccSupMiniUi.Foot) {
    $hint = Get-TbccHubFootHint -HubLines $Snap.HubLines -HubWarn $hubWarn -HubCrit $hubCrit -CpuPct $cpuPct
    $script:TbccSupMiniUi.Tip.SetToolTip($script:TbccSupMiniUi.Foot, $hint)
  }
}

function Show-TbccSupervisorPanel {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    [scriptblock]$OnNotify,
    [scriptblock]$OnRefreshCache
  )

  try { $TbccRoot = Resolve-TbccSupervisorRoot -TbccRoot $TbccRoot } catch {
    if ($OnNotify) { & $OnNotify $_.Exception.Message }
    return
  }

  # Don't leave mini ticking underneath the full panel (dual refresh = UI stall).
  if ($script:TbccSupMiniForm -and -not $script:TbccSupMiniForm.IsDisposed) {
    try {
      if ($script:TbccSupMiniRefreshTimer) { $script:TbccSupMiniRefreshTimer.Stop() }
      $script:TbccSupMiniForm.Hide()
    } catch {}
  }

  if ($script:TbccSupPanelForm -and -not $script:TbccSupPanelForm.IsDisposed) {
    $script:TbccSupPanelClosing = $false
    if ($script:TbccSupUi) { $script:TbccSupUi.TbccRoot = $TbccRoot }
    $script:TbccSupPanelForm.Show()
    $script:TbccSupPanelForm.WindowState = [System.Windows.Forms.FormWindowState]::Normal
    # Restart the off-thread producer (mini may have parked/replaced it while we were hidden).
    [void](Start-TbccSupSnapshotProducer -TbccRoot $TbccRoot -FullStack:$FullStack)
    if ($script:TbccSupPanelRefreshTimer -and -not $script:TbccSupPanelRefreshTimer.Enabled) {
      $script:TbccSupPanelRefreshTimer.Start()
    }
    $script:TbccSupPanelForm.Activate()
    return
  }

  $theme = Get-TbccSupervisorTheme
  $errorHubLog = Get-TbccErrorHubLogPath -TbccRoot $TbccRoot
  $tip = New-Object System.Windows.Forms.ToolTip
  $tip.AutoPopDelay = 12000
  $tip.InitialDelay = 350
  $tip.ReshowDelay = 120
  $tip.ShowAlways = $true

  $form = New-TbccSupervisorForm
  $form.Text = "TBCC Supervisor"
  Register-TbccFormChrome -Form $form
  $form.AutoScaleMode = [System.Windows.Forms.AutoScaleMode]::None
  $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::Sizable
  $form.MaximizeBox = $false
  $form.MinimizeBox = $true
  $form.ClientSize = New-Object System.Drawing.Size(518, 368)
  $form.MinimumSize = New-Object System.Drawing.Size(480, 340)
  $form.BackColor = $theme.Bg
  $form.ForeColor = $theme.Text
  $form.Font = $theme.FontLabel
  $form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
  $form.ShowInTaskbar = $true

  $toolStrip = New-Object System.Windows.Forms.Panel
  $toolStrip.Dock = [System.Windows.Forms.DockStyle]::Top
  $toolStrip.Height = 23
  $toolStrip.BackColor = $theme.HeaderBg
  $form.Controls.Add($toolStrip)

  $chkTop = New-Object System.Windows.Forms.CheckBox
  $chkTop.Text = "Pin"
  $chkTop.Checked = $true
  $chkTop.AutoSize = $true
  $chkTop.Left = 4
  $chkTop.Top = 3
  $chkTop.ForeColor = $theme.Muted
  $chkTop.Font = $theme.FontMicro
  $chkTop.BackColor = $theme.HeaderBg
  [void]$chkTop.Add_CheckedChanged({
    param($sender, $e)
    $f = $script:TbccSupPanelForm
    if ($f -and -not $f.IsDisposed) {
      Set-TbccFormAlwaysOnTop -Form $f -Enabled:([bool]$sender.Checked)
    }
  })
  $toolStrip.Controls.Add($chkTop)

  $btnMini = New-Object System.Windows.Forms.Button
  $btnMini.Text = "Mini"
  $btnMini.Width = 42
  $btnMini.Height = 18
  $btnMini.Top = 2
  $btnMini.Left = 50
  $btnMini.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
  $btnMini.BackColor = $theme.ModuleBg
  $btnMini.ForeColor = $theme.Text
  $btnMini.Font = $theme.FontMicro
  [void]$btnMini.Add_Click({
    $ui = $script:TbccSupUi
    if (-not $ui -or [string]::IsNullOrWhiteSpace($ui.TbccRoot)) { return }
    Show-TbccSupervisorMiniPanel -TbccRoot $ui.TbccRoot -FullStack:([bool]$ui.FullStack) `
      -OnNotify $ui.OnNotify -OnRefreshCache $ui.OnRefreshCache
  })
  $toolStrip.Controls.Add($btnMini)

  $btnHubLog = New-Object System.Windows.Forms.Button
  $btnHubLog.Text = "Hub"
  $btnHubLog.Width = 42
  $btnHubLog.Height = 18
  $btnHubLog.Top = 2
  $btnHubLog.Left = 96
  $btnHubLog.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
  $btnHubLog.BackColor = $theme.ModuleBg
  $btnHubLog.ForeColor = $theme.Text
  $btnHubLog.Font = $theme.FontMicro
  [void]$btnHubLog.Add_Click({
    $ui = $script:TbccSupUi
    if (-not $ui) { return }
    Open-TbccErrorHubLog -TbccRoot $ui.TbccRoot -OnNotify $ui.OnNotify
  })
  $toolStrip.Controls.Add($btnHubLog)

  $btnSvcFilter = New-Object System.Windows.Forms.Button
  $btnSvcFilter.Text = "Flt"
  $btnSvcFilter.Width = 30
  $btnSvcFilter.Height = 18
  $btnSvcFilter.Top = 2
  $btnSvcFilter.Left = 142
  $btnSvcFilter.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
  $btnSvcFilter.BackColor = $theme.ModuleBg
  $btnSvcFilter.ForeColor = $theme.Text
  $btnSvcFilter.Font = $theme.FontMicro
  [void]$btnSvcFilter.Add_Click({
    param($sender, $e)
    $ui = $script:TbccSupUi
    if (-not $ui) { return }
    $f = Invoke-TbccSupCycleSvcFilter -Ui $ui
    if ($sender -and $sender.PSObject.Properties['Text']) {
      $sender.Text = switch ($f) { 'core' { 'Core' } 'down' { 'Dn' } 'off' { 'Off' } default { 'All' } }
    }
    if ($ui.OnRefreshCache) { & $ui.OnRefreshCache }
  })
  $toolStrip.Controls.Add($btnSvcFilter)

  $btnOptOff = New-Object System.Windows.Forms.Button
  $btnOptOff.Text = "Opt-"
  $btnOptOff.Width = 36
  $btnOptOff.Height = 18
  $btnOptOff.Top = 2
  $btnOptOff.Left = 176
  $btnOptOff.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
  $btnOptOff.BackColor = $theme.ModuleBg
  $btnOptOff.ForeColor = $theme.Warn
  $btnOptOff.Font = $theme.FontMicro
  [void]$btnOptOff.Add_Click({
    $ui = $script:TbccSupUi
    if (-not $ui -or [string]::IsNullOrWhiteSpace($ui.TbccRoot)) { return }
    try {
      [void](Invoke-TbccSupDisableOptionalServices -TbccRoot $ui.TbccRoot -FullStack:([bool]$ui.FullStack) -OnNotify $ui.OnNotify)
      $script:TbccSupSvcCache = $null
      $script:TbccSupSvcCacheAt = $null
      if ($script:TbccSupProducer -and $script:TbccSupProducer.Shared) {
        $script:TbccSupProducer.Shared.ForceRefresh = $true
      }
      if ($ui.OnRefreshCache) { & $ui.OnRefreshCache }
    } catch {
      if ($ui.OnNotify) { & $ui.OnNotify ("Opt- failed: " + $_.Exception.Message) }
    }
  })
  $toolStrip.Controls.Add($btnOptOff)

  $root = New-Object System.Windows.Forms.TableLayoutPanel
  $root.Dock = [System.Windows.Forms.DockStyle]::Fill
  $root.BackColor = $theme.Bg
  $root.ColumnCount = 2
  $root.RowCount = 4
  $root.Padding = New-Object System.Windows.Forms.Padding(1)
  [void]$root.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 50)))
  [void]$root.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 50)))
  [void]$root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 78)))
  [void]$root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 52)))
  # Services + Hub grow with the window (Absolute Services used to clip/overflow on resize).
  [void]$root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 42)))
  [void]$root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 58)))
  $form.Controls.Add($root)

  # --- Row0: Stack | Host ---
  $modStack = New-TbccSupModule -Title "Stack" -Theme $theme
  $modHost = New-TbccSupModule -Title "Host" -Theme $theme
  [void]$root.Controls.Add($modStack.Outer, 0, 0)
  [void]$root.Controls.Add($modHost.Outer, 1, 0)

  $lblStackSummary = New-Object System.Windows.Forms.Label
  $lblStackSummary.Dock = [System.Windows.Forms.DockStyle]::Top
  $lblStackSummary.Height = 15
  $lblStackSummary.ForeColor = $theme.Text
  $lblStackSummary.Font = $theme.FontTitle
  $lblStackSummary.Text = "-"
  $modStack.Body.Controls.Add($lblStackSummary)

  $barStackObj = New-TbccSupMetricBar -Label "UP" -Pct 0 -Theme $theme -FillColor $theme.Ok
  $barStackObj.Row.Height = 18
  $modStack.Body.Controls.Add($barStackObj.Row)
  $barStackObj.Row.BringToFront() | Out-Null

  $lblStackSub = New-Object System.Windows.Forms.Label
  $lblStackSub.Dock = [System.Windows.Forms.DockStyle]::Fill
  $lblStackSub.ForeColor = $theme.Muted
  $lblStackSub.Font = $theme.FontMicro
  $lblStackSub.Text = "..."
  $modStack.Body.Controls.Add($lblStackSub)

  $hostBars = @()
  foreach ($pair in @(
      @{ L = "CPU"; K = "CpuPct" },
      @{ L = "RAM"; K = "RamPct" }
    )) {
    $b = New-TbccSupMetricBar -Label $pair.L -Pct -1 -Theme $theme -FillColor $theme.Ok -Style Diamond
    $b.Row.Height = 20
    $b.BarFill.Tag.HostKey = $pair.K
    $modHost.Body.Controls.Add($b.Row)
    $hostBars += $b.BarFill
  }
  $lblHostSub = New-Object System.Windows.Forms.Label
  $lblHostSub.Dock = [System.Windows.Forms.DockStyle]::Bottom
  $lblHostSub.Height = 14
  $lblHostSub.ForeColor = $theme.Muted
  $lblHostSub.Font = $theme.FontMicro
  $modHost.Body.Controls.Add($lblHostSub)

  $cpuSparkFull = New-TbccSupSparkline -Label "C" -Theme $theme -LineColor $theme.Ok -RowHeight 26
  $cpuSparkFull.Wrap.Dock = [System.Windows.Forms.DockStyle]::Bottom
  $modHost.Body.Controls.Add($cpuSparkFull.Wrap)
  $ramSparkFull = New-TbccSupSparkline -Label "R" -Theme $theme -LineColor ([System.Drawing.Color]::FromArgb(96, 165, 250)) -RowHeight 26
  $ramSparkFull.Wrap.Dock = [System.Windows.Forms.DockStyle]::Bottom
  $modHost.Body.Controls.Add($ramSparkFull.Wrap)

  # --- Row1: Infra (full width) ---
  $modInfra = New-TbccSupModule -Title "Infra" -Theme $theme
  [void]$root.SetColumnSpan($modInfra.Outer, 2)
  [void]$root.Controls.Add($modInfra.Outer, 0, 1)

  $infraPanel = New-Object System.Windows.Forms.FlowLayoutPanel
  $infraPanel.Dock = [System.Windows.Forms.DockStyle]::Fill
  $infraPanel.FlowDirection = [System.Windows.Forms.FlowDirection]::LeftToRight
  $infraPanel.WrapContents = $true
  $infraPanel.AutoScroll = $false
  $infraPanel.BackColor = $theme.ModuleBg
  $modInfra.Body.Controls.Add($infraPanel)

  # --- Row2: Services (full width) ---
  $modSvc = New-TbccSupModule -Title "Services" -Theme $theme
  [void]$root.SetColumnSpan($modSvc.Outer, 2)
  [void]$root.Controls.Add($modSvc.Outer, 0, 2)

  $svcGrid = New-Object System.Windows.Forms.TableLayoutPanel
  $svcGrid.Dock = [System.Windows.Forms.DockStyle]::Fill
  $svcGrid.BackColor = $theme.ModuleBg
  $svcGrid.ColumnCount = 2
  [void]$svcGrid.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 50)))
  [void]$svcGrid.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 50)))
  $svcGrid.AutoScroll = $true
  Register-TbccScrollBarSuppression -Control $svcGrid
  Register-TbccWheelScroll -Control $svcGrid
  $modSvc.Body.Controls.Add($svcGrid)

  # --- Row3: Hub | Alerts ---
  $modHub = New-TbccSupModule -Title "Error hub" -Theme $theme
  $modAlert = New-TbccSupModule -Title "Alerts" -Theme $theme
  [void]$root.Controls.Add($modHub.Outer, 0, 3)
  [void]$root.Controls.Add($modAlert.Outer, 1, 3)

  $hubList = New-Object System.Windows.Forms.ListBox
  $hubList.Dock = [System.Windows.Forms.DockStyle]::Fill
  $hubList.BackColor = [System.Drawing.Color]::FromArgb(14, 14, 16)
  $hubList.ForeColor = $theme.Text
  $hubList.Font = $theme.FontMono
  $hubList.BorderStyle = [System.Windows.Forms.BorderStyle]::None
  $hubList.IntegralHeight = $false
  $hubList.DrawMode = [System.Windows.Forms.DrawMode]::OwnerDrawFixed
  $hubList.ItemHeight = 14
  Register-TbccScrollBarSuppression -Control $hubList
  Register-TbccWheelScroll -Control $hubList
  $hubList.Add_DrawItem({
    param($sender, $e)
    if ($e.Index -lt 0) { return }
    $entry = $sender.Items[$e.Index]
    $line = Get-TbccHubEntryText -Entry $entry
    $sev = Get-TbccHubLineSeverity -Line $line
    $t = if ($script:TbccSupUi -and $script:TbccSupUi.Theme) { $script:TbccSupUi.Theme } else { Get-TbccSupervisorTheme }
    $fg = Get-TbccHubInkColor -Severity $sev -Theme $t
    $bg = if ($e.State -band [System.Windows.Forms.DrawItemState]::Selected) {
      [System.Drawing.Color]::FromArgb(38, 38, 44)
    } else {
      [System.Drawing.Color]::FromArgb(14, 14, 16)
    }
    $e.DrawBackground()
    $bgBrush = New-Object System.Drawing.SolidBrush($bg)
    $e.Graphics.FillRectangle($bgBrush, $e.Bounds)
    $bgBrush.Dispose()
    $clip = $line
    if ($clip.Length -gt 140) { $clip = $clip.Substring(0, 137) + "..." }
    $fgBrush = New-Object System.Drawing.SolidBrush($fg)
    $e.Graphics.DrawString($clip, $sender.Font, $fgBrush, [System.Drawing.RectangleF]$e.Bounds)
    $fgBrush.Dispose()
    $e.DrawFocusRectangle()
  })
  [void]$hubList.Add_DoubleClick({
    $idx = $script:TbccSupUi.HubList.SelectedIndex
    if ($idx -lt 0) { return }
    $entry = $script:TbccSupUi.HubList.Items[$idx]
    $lineNo = 0
    if ($entry.LineNumber) { $lineNo = [int]$entry.LineNumber }
    if ($lineNo -le 0) { return }
    $logPath = $script:TbccSupUi.ErrorHubLog
    $ok = Open-TbccErrorHubAtLine -LogPath $logPath -LineNumber $lineNo
    if (-not $ok -and $script:TbccSupUi.OnNotify) {
      & $script:TbccSupUi.OnNotify "Could not open error hub log."
    }
  })
  [void]$hubList.Add_MouseMove({
    param($sender, $e)
    $ui = $script:TbccSupUi
    if (-not $ui -or -not $ui.Tip) { return }
    $idx = $sender.IndexFromPoint($e.Location)
    if ($idx -lt 0 -or $idx -ge $sender.Items.Count) {
      if ($script:TbccSupHubTipIdx -ne -2) {
        $script:TbccSupHubTipIdx = -2
        $ui.Tip.SetToolTip($sender, "Hover a line for CAUSE/FIX · Double-click jumps in Notepad · wheel scrolls")
      }
      return
    }
    if ($script:TbccSupHubTipIdx -eq $idx) { return }
    $script:TbccSupHubTipIdx = $idx
    $entry = $sender.Items[$idx]
    $line = Get-TbccHubEntryText -Entry $entry
    $ui.Tip.SetToolTip($sender, (Get-TbccHubLineHint -Line $line))
  })
  $modHub.Body.Controls.Add($hubList)

  $alertList = New-Object System.Windows.Forms.ListBox
  $alertList.Dock = [System.Windows.Forms.DockStyle]::Fill
  $alertList.BackColor = [System.Drawing.Color]::FromArgb(14, 14, 16)
  $alertList.ForeColor = $theme.Text
  $alertList.Font = $theme.FontMicro
  $alertList.BorderStyle = [System.Windows.Forms.BorderStyle]::None
  Register-TbccScrollBarSuppression -Control $alertList
  Register-TbccWheelScroll -Control $alertList
  $modAlert.Body.Controls.Add($alertList)

  $statusStrip = New-Object System.Windows.Forms.StatusStrip
  $statusStrip.BackColor = $theme.HeaderBg
  $statusStrip.ForeColor = $theme.Muted
  $statusStrip.SizingGrip = $true
  $statusStrip.Height = 21
  $statusLbl = New-Object System.Windows.Forms.ToolStripStatusLabel
  $statusLbl.Text = "4s refresh"
  $statusLbl.Spring = $true
  $statusLbl.Font = $theme.FontMicro
  $statusLbl.TextAlign = [System.Drawing.ContentAlignment]::MiddleLeft
  [void]$statusStrip.Items.Add($statusLbl)
  $form.Controls.Add($statusStrip)

  $script:TbccSupUi = @{
    Form         = $form
    Theme        = $theme
    Tip          = $tip
    TbccRoot     = $TbccRoot
    FullStack    = [bool]$FullStack
    OnNotify     = $OnNotify
    OnRefreshCache = $OnRefreshCache
    ErrorHubLog  = $errorHubLog
    ModHubHeader = $modHub.Header
    LblStackSum  = $lblStackSummary
    LblStackSub  = $lblStackSub
    BarStack     = $barStackObj.BarFill
    HostBars     = $hostBars
    CpuSpark     = $cpuSparkFull.Canvas
    RamSpark     = $ramSparkFull.Canvas
    NetPrev      = $null
    LblHostSub   = $lblHostSub
    InfraPanel   = $infraPanel
    SvcGrid      = $svcGrid
    HubList      = $hubList
    AlertList    = $alertList
    StatusLbl    = $statusLbl
    ChkPin       = $chkTop
    ModSvcHeader = $modSvc.Header
    SvcFilter    = 'all'
    SvcCoreIdSet = (Get-TbccSupCoreServiceIdSet -TbccRoot $TbccRoot -FullStack:$FullStack)
    BtnSvcFilter = $btnSvcFilter
    ServiceRows  = @{}
    InfraRows    = (New-Object System.Collections.Generic.List[object])
    SvcCells     = @{}
    SvcCellIdKey = $null
  }

  if ($script:TbccSupPanelRefreshTimer) {
    try { $script:TbccSupPanelRefreshTimer.Stop(); $script:TbccSupPanelRefreshTimer.Dispose() } catch {}
    $script:TbccSupPanelRefreshTimer = $null
  }
  $script:TbccSupPanelRefreshTimer = New-Object System.Windows.Forms.Timer
  $refreshTimer = $script:TbccSupPanelRefreshTimer
  # Applier cadence matches the producer's host-sample interval so sparklines stay smooth;
  # the tick is now cheap (apply pre-computed data), so ~1.2s no longer risks a pump stall.
  $refreshTimer.Interval = 1200
  $script:TbccSupPanelClosing = $false
  [void]$refreshTimer.Add_Tick({
    if ($script:TbccSupPanelClosing) { return }
    if (-not $script:TbccSupPanelForm -or $script:TbccSupPanelForm.IsDisposed) { return }
    if (Test-TbccFormInteractionPaused -Form $script:TbccSupPanelForm) { return }
    $ui = $script:TbccSupUi
    if (-not $ui -or [string]::IsNullOrWhiteSpace($ui.TbccRoot)) { return }
    # Re-entrancy guard kept: even the cheap applier must never stack on itself.
    if ($script:TbccSupPanelBusy) { return }
    $script:TbccSupPanelBusy = $true
    try {
      # Read the off-thread producer's latest snapshot. Only run the (blocking) synchronous
      # fallback when the producer is genuinely absent or dead/wedged — NOT while it is still
      # dot-sourcing the runspace, or tick 1 would freeze the pump for ~6s on every cold open
      # and throw away the producer that is coming up.
      $prod = Get-TbccSupProducerSnapshot
      $snap = $null
      $stale = $false
      $ageSec = 0
      if ($prod -and $prod.Snap) {
        $snap = $prod.Snap
        $stale = [bool]$prod.Stale
        $ageSec = [int]$prod.AgeSec
      } elseif ($null -eq $prod -or ($prod.State -ne "initializing")) {
        # No producer object (cold), load-failed, or wedged → one sync snapshot + (re)start.
        $snap = Get-TbccSupervisorHealthSnapshot -TbccRoot $ui.TbccRoot -FullStack:([bool]$ui.FullStack) -NetPrev $ui.NetPrev
        [void](Start-TbccSupSnapshotProducer -TbccRoot $ui.TbccRoot -FullStack:([bool]$ui.FullStack))
      }
      # else: producer initializing (dot-sourcing) — skip apply, show "starting", let it come up.
      if (-not $snap -and $ui.StatusLbl) {
        $ui.StatusLbl.Text = "starting monitor..."
        $ui.StatusLbl.ForeColor = $ui.Theme.Muted
      }
      if ($snap) {
        Update-TbccSupPanelUi -Snap $snap
        if ($ui.OnRefreshCache -and $snap.Cache) {
          & $ui.OnRefreshCache $snap.Cache
        }
        if ($ui.StatusLbl) {
          if ($stale) {
            # Surface silent staleness instead of painting a stale lie with no freeze.
            $ui.StatusLbl.Text = ("STALE {0}s | {1} | {2}" -f $ageSec, (Get-Date -Format "HH:mm:ss"), $ui.TbccRoot)
            $ui.StatusLbl.ForeColor = if ($ageSec -ge 20 -or ($prod -and -not $prod.Producing)) { $ui.Theme.Crit } else { $ui.Theme.Warn }
          } else {
            if ($snap.Meltdown) {
              $ms = Get-TbccSupMeltdownStyle -Snap $snap
              $ui.StatusLbl.Text = ("{0} | {1} | {2}" -f $ms.Prefix, (Get-Date -Format "HH:mm:ss"), $ui.TbccRoot)
              $ui.StatusLbl.ForeColor = Get-TbccHeatColor -Pct $ms.HeatPct
            } else {
              $ui.StatusLbl.ForeColor = $ui.Theme.Muted
            }
          }
        }
      }
      foreach ($sc in @($ui.SvcGrid, $ui.HubList, $ui.AlertList)) {
        Hide-TbccControlScrollBars -Control $sc
      }
      if ($ui.ChkPin -and $ui.ChkPin.Checked) {
        Set-TbccFormAlwaysOnTop -Form $script:TbccSupPanelForm -Enabled:$true
      }
    } catch {
      if ($ui.StatusLbl) {
        $ui.StatusLbl.Text = ("Err: " + $_.Exception.Message)
      }
    } finally {
      $script:TbccSupPanelBusy = $false
    }
  })

  $form.Add_FormClosing({
    $script:TbccSupPanelClosing = $true
    $t = $script:TbccSupPanelRefreshTimer
    if ($t) { $t.Stop() }
    if ($script:TbccSupDiamondSparkleTimer) {
      try { $script:TbccSupDiamondSparkleTimer.Stop() } catch {}
    }
  })
  $form.Add_FormClosed({
    $script:TbccSupPanelClosing = $true
    # Single shared producer: closing a *hidden* (parked) full panel while the mini is the
    # active consumer would stop the producer the mini is using — the mini's next tick
    # self-heals (State != initializing -> sync + restart), so it recovers with one hitch.
    Stop-TbccSupSnapshotProducer
    $t = $script:TbccSupPanelRefreshTimer
    if ($t) {
      try { $t.Stop() } catch {}
      try { $t.Dispose() } catch {}
      $script:TbccSupPanelRefreshTimer = $null
    }
    if ($script:TbccSupDiamondSparkleTimer) {
      try { $script:TbccSupDiamondSparkleTimer.Stop() } catch {}
      try { $script:TbccSupDiamondSparkleTimer.Dispose() } catch {}
      $script:TbccSupDiamondSparkleTimer = $null
    }
    $ui = $script:TbccSupUi
    if ($ui -and $ui.Tip) {
      try { $ui.Tip.Dispose() } catch {}
    }
    $script:TbccSupPanelForm = $null
    $script:TbccSupUi = $null
  })

  [void]$refreshTimer.Add_Tick({
    param($s, $e)
    if ($s.Interval -ne 1200) { $s.Interval = 1200 }
  })

  $form.Add_Load({
    # Don't snapshot synchronously here — with the API down this blocked the first
    # paint for seconds and the panel appeared as a glitched, unpainted window.
    # The fast first tick populates the UI right after the form is visible.
    $ui = $script:TbccSupUi
    if ($ui -and $ui.ChkPin -and $ui.ChkPin.Checked -and $script:TbccSupPanelForm) {
      Set-TbccFormAlwaysOnTop -Form $script:TbccSupPanelForm -Enabled:$true
    }
    if ($script:TbccSupPanelForm) {
      Set-TbccFormDarkCaption -Form $script:TbccSupPanelForm -Enabled:$true
    }
    if ($ui) {
      foreach ($sc in @($ui.SvcGrid, $ui.HubList, $ui.AlertList)) {
        Hide-TbccControlScrollBars -Control $sc
      }
      # Kick off the off-thread acquisition producer; the first cheap tick applies its data.
      [void](Start-TbccSupSnapshotProducer -TbccRoot $ui.TbccRoot -FullStack:([bool]$ui.FullStack))
      Start-TbccSupDiamondSparkleTimer -Ui $ui
    }
    $t = $script:TbccSupPanelRefreshTimer
    if (-not $t) { return }
    $t.Interval = 250
    $t.Start()
  })

  $tip.SetToolTip($chkTop, "Always on top + dark title bar (Pin)")
  $tip.SetToolTip($btnMini, "Compact monitor - parks this panel so sparks keep updating")
  $tip.SetToolTip($btnHubLog, "Open error-hub.log in Notepad")
  $tip.SetToolTip($barStackObj.Row, "Enabled services that are up")
  $tip.SetToolTip($lblStackSub, "StackWatch process audit (from .tbcc-run\process-audit.json, ~60s refresh)")
  $tip.SetToolTip($modHost.Outer, "CPU/RAM champagne mosaic meters (heat + sparkle) and sparkline history")
  $tip.SetToolTip($btnSvcFilter, "Cycle filter: All / Core / Down / Off")
  $tip.SetToolTip($btnOptOff, "Disable all optional (non-core) services")
  $tip.SetToolTip($modSvc.Outer, "Click row: enable/disable | Ctrl+click: restart | wheel scrolls | Flt filters list")
  $tip.SetToolTip($modAlert.Outer, "Conflicts and ops alerts")
  $tip.SetToolTip($hubList, "Hover a line for CAUSE/FIX · Double-click jumps in Notepad · wheel scrolls")

  $panelCtx = New-Object System.Windows.Forms.ContextMenuStrip
  $miPanelStart = New-Object System.Windows.Forms.ToolStripMenuItem
  $miPanelStart.Text = "Start stack"
  [void]$miPanelStart.Add_Click({
    $ui = $script:TbccSupUi
    if (-not $ui -or [string]::IsNullOrWhiteSpace($ui.TbccRoot)) { return }
    try {
      if (Get-Command Invoke-TbccStackLaunch -ErrorAction SilentlyContinue) {
        Invoke-TbccStackLaunch -TbccRoot $ui.TbccRoot
        if ($ui.OnNotify) { & $ui.OnNotify "Stack launch started." }
      } elseif (Get-Command Invoke-TbccLeanStackLaunch -ErrorAction SilentlyContinue) {
        Invoke-TbccLeanStackLaunch -TbccRoot $ui.TbccRoot
        if ($ui.OnNotify) { & $ui.OnNotify "Stack launch started." }
      } elseif ($ui.OnNotify) {
        & $ui.OnNotify "Stack launch unavailable (reload supervisor)."
      }
    } catch {
      if ($ui.OnNotify) { & $ui.OnNotify ("Stack launch failed: " + $_.Exception.Message) }
    }
  }.GetNewClosure())
  [void]$panelCtx.Items.Add($miPanelStart)
  $form.ContextMenuStrip = $panelCtx

  $script:TbccSupPanelForm = $form
  try {
    [void]$form.Show()
    Set-TbccFormAlwaysOnTop -Form $form -Enabled:([bool]$chkTop.Checked)
    $form.BringToFront()
    $form.Activate()
  } catch {
    if ($OnNotify) { & $OnNotify ("Panel open failed: " + $_.Exception.Message) }
    $script:TbccSupPanelForm = $null
    $script:TbccSupUi = $null
  }
}
