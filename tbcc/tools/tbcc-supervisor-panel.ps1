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
  @{
    Bg          = [System.Drawing.Color]::FromArgb(18, 18, 20)
    ModuleBg    = [System.Drawing.Color]::FromArgb(24, 24, 28)
    ModuleBorder= [System.Drawing.Color]::FromArgb(52, 52, 58)
    HeaderBg    = [System.Drawing.Color]::FromArgb(32, 32, 38)
    Text        = [System.Drawing.Color]::FromArgb(220, 218, 210)
    Muted       = [System.Drawing.Color]::FromArgb(120, 118, 112)
    Ok          = [System.Drawing.Color]::FromArgb(52, 211, 153)
    Warn        = [System.Drawing.Color]::FromArgb(251, 191, 36)
    Crit        = [System.Drawing.Color]::FromArgb(248, 113, 113)
    Off         = [System.Drawing.Color]::FromArgb(90, 90, 96)
    BarBg       = [System.Drawing.Color]::FromArgb(40, 40, 46)
    FontMicro   = New-Object System.Drawing.Font("Segoe UI", 6.25)
    FontLabel   = New-Object System.Drawing.Font("Segoe UI", 6.75)
    FontHeader  = New-Object System.Drawing.Font("Segoe UI", 6.75, [System.Drawing.FontStyle]::Bold)
    FontTitle   = New-Object System.Drawing.Font("Segoe UI", 7.25, [System.Drawing.FontStyle]::Bold)
    FontMono    = New-Object System.Drawing.Font("Consolas", 6.5)
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
  $hdr.Height = 14
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
  # Cached perf counter (~0ms/sample) instead of a Win32_Processor WMI query every tick.
  try {
    if (-not $script:TbccSupCpuCounter) {
      $script:TbccSupCpuCounter = New-Object System.Diagnostics.PerformanceCounter(
        "Processor", "% Processor Time", "_Total", $true)
      [void]$script:TbccSupCpuCounter.NextValue()  # first sample is always 0 — warm up
      return $null
    }
    return [int][Math]::Round($script:TbccSupCpuCounter.NextValue())
  } catch {
    $script:TbccSupCpuCounter = $null
    try {
      $p = Get-CimInstance Win32_Processor -ErrorAction Stop | Select-Object -First 1
      if ($null -ne $p.LoadPercentage) { return [int]$p.LoadPercentage }
    } catch {}
    return $null
  }
}

function Get-TbccHostMetrics {
  param($NetPrev = $null)
  $cpu = Get-TbccCpuPercentFast
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
  $net = Get-TbccNetworkSample -Prev $NetPrev
  return @{
    CpuPct     = $cpu
    RamPct     = $ramPct
    RamUsedGb  = $ramUsedGb
    RamTotalGb = $ramTotalGb
    Net        = $net
  }
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

function New-TbccSupSparkline {
  param(
    [string]$Label,
    $Theme,
    [System.Drawing.Color]$LineColor,
    [int]$MaxPoints = 60
  )
  $wrap = New-Object System.Windows.Forms.Panel
  $wrap.Height = 22
  $wrap.Dock = [System.Windows.Forms.DockStyle]::Bottom
  $wrap.BackColor = $Theme.ModuleBg
  $wrap.Margin = New-Object System.Windows.Forms.Padding(0, 1, 0, 0)

  $lbl = New-Object System.Windows.Forms.Label
  $lbl.Text = $Label
  $lbl.Width = 28
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
  }
  $canvas.Add_Paint({
    param($sender, $e)
    $g = $e.Graphics
    $tag = $sender.Tag
    $w = $sender.Width
    $h = $sender.Height
    $bg = [System.Drawing.Color]::FromArgb(14, 14, 16)
    $bgBrush = New-Object System.Drawing.SolidBrush($bg)
    $g.FillRectangle($bgBrush, 0, 0, $w, $h)
    $bgBrush.Dispose()
    $vals = @($tag.Values)
    if ($vals.Count -lt 2) { return }
    $maxV = 100.0
    $minV = 0.0
    $pts = New-Object System.Collections.Generic.List[System.Drawing.PointF]
    for ($i = 0; $i -lt $vals.Count; $i++) {
      $x = [single](($i / [Math]::Max(1, ($vals.Count - 1))) * ($w - 2) + 1)
      $norm = ([double]$vals[$i] - $minV) / ($maxV - $minV)
      $norm = [Math]::Max(0, [Math]::Min(1, $norm))
      $y = [single](($h - 2) * (1.0 - $norm) + 1)
      $pts.Add([System.Drawing.PointF]::new($x, $y))
    }
    if ($pts.Count -ge 2) {
      $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
      $pen = New-Object System.Drawing.Pen($tag.LineColor, 1.2)
      $g.DrawLines($pen, $pts.ToArray())
      $pen.Dispose()
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

function Get-TbccHubLineSeverity {
  param([string]$Line)
  if (-not $Line) { return "muted" }
  $l = $Line.ToLowerInvariant()
  if ($l -match 'critical|fatal|database is locked|address already in use|traceback') { return "crit" }
  if ($l -match 'error|failed|exception|refused|eaddrinuse|winerror') { return "warn" }
  if ($l -match 'warning|warn') { return "warn" }
  return "ok"
}

function Get-TbccSupervisorHealthSnapshot {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    $NetPrev = $null
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
    Host          = Get-TbccHostMetrics -NetPrev $NetPrev
    UpdatedAt     = $now
  }
  # Service status cache enumerates Win32_Process (expensive) — refresh at most every 8s
  # and reuse the cached result between ticks. Service state doesn't change faster anyway.
  $cacheFresh = $script:TbccSupSvcCache -and $script:TbccSupSvcCacheAt -and `
    (($now - $script:TbccSupSvcCacheAt).TotalSeconds -lt 8)
  if (-not $cacheFresh) {
    try {
      $script:TbccSupSvcCache = Update-TbccServiceStatusCache -TbccRoot $TbccRoot -FullStack:$FullStack -MenuCatalog
      $script:TbccSupSvcCacheAt = $now
    } catch {}
  }
  $snap.Cache = $script:TbccSupSvcCache
  # One netstat pass per snapshot, shared with the UI (the ports row previously re-ran
  # Get-TbccListeningPortSet once per port, spawning 4 extra netstat processes per tick).
  try { $snap.Ports = Get-TbccListeningPortSet } catch {}
  $hubPath = Join-Path $TbccRoot ".tbcc-run\error-hub.log"
  $snap.HubLines = @(Read-TbccErrorHubTail -Path $hubPath -MaxLines 56)
  $auditPath = Join-Path $TbccRoot ".tbcc-run\process-audit.json"
  if (Test-Path -LiteralPath $auditPath) {
    try {
      $snap.ProcessAudit = Get-Content -LiteralPath $auditPath -Raw -ErrorAction Stop | ConvertFrom-Json
    } catch {}
  }
  # When the API is down, don't block the UI thread on HTTP timeouts every tick — back off 15s.
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
    } catch {
      $snap.HealthErr = $_.Exception.Message
      $script:TbccSupHealthFailAt = $now
    }
    if ($snap.HealthOk) {
      try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:8000/ops/alerts/poll" -Method GET -TimeoutSec 2
        if ($r -and $r.alerts) { $snap.OpsAlerts = @($r.alerts) }
      } catch {}
    }
  }
  return $snap
}

function New-TbccSupMetricBar {
  param(
    [string]$Label,
    [double]$Pct,
    $Theme,
    [System.Drawing.Color]$FillColor
  )
  $row = New-Object System.Windows.Forms.Panel
  $row.Height = 22
  $row.Dock = [System.Windows.Forms.DockStyle]::Top
  $row.Margin = New-Object System.Windows.Forms.Padding(0, 0, 0, 2)
  $row.BackColor = $Theme.ModuleBg

  $lbl = New-Object System.Windows.Forms.Label
  $lbl.Text = $Label
  $lbl.Width = 52
  $lbl.Dock = [System.Windows.Forms.DockStyle]::Left
  $lbl.ForeColor = $Theme.Muted
  $lbl.Font = $Theme.FontMicro
  $lbl.TextAlign = [System.Drawing.ContentAlignment]::MiddleLeft
  $row.Controls.Add($lbl)

  $barHost = New-Object System.Windows.Forms.Panel
  $barHost.Dock = [System.Windows.Forms.DockStyle]::Fill
  $barHost.BackColor = $Theme.ModuleBg
  $row.Controls.Add($barHost)

  $barBg = New-Object System.Windows.Forms.Panel
  $barBg.Height = 8
  $barBg.Width = 100
  $barBg.BackColor = $Theme.BarBg
  $barBg.Tag = @{ Pct = $Pct; Fill = $FillColor; Theme = $Theme; BarBg = $barBg; Row = $row }
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
  $barHost.Controls.Add($barBg)
  $barHost.Add_Resize({
    param($s, $ev)
    foreach ($c in $s.Controls) {
      if ($c -is [System.Windows.Forms.Panel]) {
        $c.Width = [Math]::Max(40, $s.Width - 44)
        $c.Top = [int](($s.Height - $c.Height) / 2)
        $c.Left = 0
      }
    }
  })

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
  $Bar.Tag.Pct = $Pct
  $Bar.Tag.Fill = $FillColor
  $Bar.Invalidate()
  $row = $Bar.Tag.Row
  if ($row -and $row.Controls.Count -ge 3) {
    $row.Controls[2].Text = if ($Pct -ge 0) { ("{0:N0}%" -f $Pct) } else { "-" }
  }
}

function New-TbccSupLedRow {
  param(
    [string]$Label,
    [string]$Status,
    [string]$Detail,
    $Theme
  )
  $row = New-Object System.Windows.Forms.Panel
  $row.Height = 13
  $row.Dock = [System.Windows.Forms.DockStyle]::Top
  $row.BackColor = $Theme.ModuleBg

  $led = New-Object System.Windows.Forms.Panel
  $led.Size = New-Object System.Drawing.Size(8, 8)
  $led.Left = 2
  $led.Top = 4
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
  $lbl.Height = 16
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
    $fill = if ($pct -ge 95) { $t.Ok } elseif ($pct -ge 70) { $t.Warn } else { $t.Crit }
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
    $fill = if ($pct -ge 90) { $t.Crit } elseif ($pct -ge 75) { $t.Warn } else { $t.Ok }
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
  }
  if ($null -ne $hostSnap.RamPct) {
    Push-TbccSupSparklineSample -Canvas $ui.RamSpark -Value ([double]$hostSnap.RamPct)
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
    $newRow.Height = 13
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
    $ids = @($cache.Services | ForEach-Object { $_.Id })
    $idKey = ($ids -join ',')
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
        [void]$ui.SvcGrid.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 14)))
      }
      for ($i = 0; $i -lt $ids.Count; $i++) {
        $id = $ids[$i]
        $col = if ($i -lt $half) { 0 } else { 1 }
        $ri2 = if ($i -lt $half) { $i } else { $i - $half }
        $cell = New-TbccSupLedRow -Label "" -Status "off" -Detail "" -Theme $t
        $cell.Tag.Id = $id
        $cell.Cursor = [System.Windows.Forms.Cursors]::Hand
        $cell.Add_Click({
          param($sender, $e)
          $tag = $sender.Tag
          if (-not $tag -or -not $tag.Id) { return }
          $ctrl = ([System.Windows.Forms.Control]::ModifierKeys -band [System.Windows.Forms.Keys]::Control) -ne 0
          $u = $script:TbccSupUi
          try {
            Invoke-TbccServiceMenuAction -ServiceId $tag.Id -TbccRoot $u.TbccRoot -FullStack:([bool]$u.FullStack) -MenuCatalog `
              -ForceRestart:$ctrl -OnNotify $u.OnNotify
            if ($u.OnRefreshCache) { & $u.OnRefreshCache }
          } catch {
            if ($u.OnNotify) { & $u.OnNotify ("Service action failed: " + $_.Exception.Message) }
          }
        })
        if ($ui.Tip) {
          $row0 = $cache.ById[$id]
          if ($row0) {
            $tipTxt = Get-TbccServiceMenuTooltip -Service $row0.Service -Status ([string]$row0.Status) -UserEnabled:([bool]$row0.UserEnabled)
            $ui.Tip.SetToolTip($cell, $tipTxt)
          } else {
            $ui.Tip.SetToolTip($cell, "Toggle | Ctrl+restart")
          }
        }
        [void]$ui.SvcGrid.Controls.Add($cell, $col, $ri2)
        $ui.SvcCells[$id] = $cell
      }
      $ui.SvcCellIdKey = $idKey
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

  $ui.HubList.Items.Clear()
  $hubCrit = 0
  $hubWarn = 0
  foreach ($entry in @($Snap.HubLines)) {
    $line = if ($entry.Text) { [string]$entry.Text } else { [string]$entry }
    $sev = Get-TbccHubLineSeverity -Line $line
    if ($sev -eq "crit") { $hubCrit++ } elseif ($sev -eq "warn") { $hubWarn++ }
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
    $ui.ModHubHeader.ForeColor = if ($hubCrit -gt 0) { $t.Crit } elseif ($hubWarn -gt 0) { $t.Warn } else { $t.Muted }
  }

  $ui.AlertList.Items.Clear()
  if ($Snap.HealthOk -and $health -and $health.conflicts) {
    foreach ($c in @($health.conflicts)) {
      $sev = if ($c.severity) { [string]$c.severity.ToUpper() } else { "WARN" }
      $msg = if ($c.message) { [string]$c.message } else { [string]$c.code }
      if ($msg.Length -gt 80) { $msg = $msg.Substring(0, 77) + "..." }
      [void]$ui.AlertList.Items.Add(("[$sev] {0}" -f $msg))
    }
  } elseif ($Snap.HealthErr) {
    [void]$ui.AlertList.Items.Add("[CRIT] API down")
  } else {
    [void]$ui.AlertList.Items.Add("No conflicts")
  }
  if ($health -and $health.recommendations) {
    foreach ($rec in @($health.recommendations)) {
      $r = [string]$rec
      if ($r.Length -gt 80) { $r = $r.Substring(0, 77) + "..." }
      [void]$ui.AlertList.Items.Add("-> " + $r)
    }
  }
  foreach ($a in @($Snap.OpsAlerts)) {
    if (-not $a) { continue }
    $sev = if ($a.severity) { [string]$a.severity.ToUpper() } else { "WARN" }
    if ($sev -eq "INFO") { continue }
    $title = if ($a.title) { [string]$a.title } else { "Alert" }
    [void]$ui.AlertList.Items.Add(("[$sev] {0}" -f $title))
  }

  $overall = if ($hubCrit -gt 0 -or ($Snap.HealthOk -and $health -and -not $health.ok)) { $t.Crit }
    elseif ($hubWarn -gt 0) { $t.Warn }
    else { $t.Ok }
  if ($ui.StatusLbl) {
    $ui.StatusLbl.Text = ("{0} | {1}" -f (Get-Date -Format "HH:mm:ss"), $ui.TbccRoot)
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

  if ($script:TbccSupMiniForm -and -not $script:TbccSupMiniForm.IsDisposed) {
    $script:TbccSupMiniForm.Show()
    $script:TbccSupMiniForm.Activate()
    return
  }

  $theme = Get-TbccSupervisorTheme
  $tip = New-Object System.Windows.Forms.ToolTip
  $tip.ShowAlways = $true

  $form = New-Object System.Windows.Forms.Form
  $form.Text = "TBCC Mini"
  $form.AutoScaleMode = [System.Windows.Forms.AutoScaleMode]::None
  $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedSingle
  $form.MaximizeBox = $false
  $form.MinimizeBox = $true
  $form.ClientSize = New-Object System.Drawing.Size(340, 108)
  $form.MinimumSize = $form.Size
  $form.MaximumSize = $form.Size
  $form.BackColor = $theme.Bg
  $form.ForeColor = $theme.Text
  $form.Font = $theme.FontMicro
  $form.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
  $form.Location = New-Object System.Drawing.Point(40, 40)
  $form.TopMost = $true
  $form.ShowInTaskbar = $true

  $toolRow = New-Object System.Windows.Forms.Panel
  $toolRow.Dock = [System.Windows.Forms.DockStyle]::Top
  $toolRow.Height = 18
  $toolRow.BackColor = $theme.HeaderBg
  $form.Controls.Add($toolRow)

  $chkPin = New-Object System.Windows.Forms.CheckBox
  $chkPin.Text = "Pin"
  $chkPin.Checked = $true
  $chkPin.AutoSize = $true
  $chkPin.Left = 4
  $chkPin.Top = 1
  $chkPin.ForeColor = $theme.Muted
  $chkPin.Font = $theme.FontMicro
  $chkPin.BackColor = $theme.HeaderBg
  [void]$chkPin.Add_CheckedChanged({
    param($sender, $e)
    $f = $script:TbccSupMiniForm
    if ($f -and -not $f.IsDisposed) { $f.TopMost = $sender.Checked }
  })
  $toolRow.Controls.Add($chkPin)

  $btnMin = New-Object System.Windows.Forms.Button
  $btnMin.Text = "_"
  $btnMin.Width = 22
  $btnMin.Height = 16
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
  $btnMin.Add_Resize({ $btnMin.Left = $toolRow.Width - 28 }) | Out-Null
  [void]$toolRow.Add_Resize({ $btnMin.Left = [Math]::Max(4, $toolRow.Width - 28) })

  $root = New-Object System.Windows.Forms.TableLayoutPanel
  $root.Dock = [System.Windows.Forms.DockStyle]::Fill
  $root.BackColor = $theme.Bg
  $root.RowCount = 3
  $root.ColumnCount = 1
  [void]$root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 18)))
  [void]$root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 55)))
  [void]$root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 16)))
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
  $cpuSpark = New-TbccSupSparkline -Label "CPU" -Theme $theme -LineColor $theme.Ok
  $cpuSpark.Wrap.Dock = [System.Windows.Forms.DockStyle]::Top
  $cpuSpark.Wrap.Height = 22
  $ramSpark = New-TbccSupSparkline -Label "RAM" -Theme $theme -LineColor ([System.Drawing.Color]::FromArgb(96, 165, 250))
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
    Show-TbccSupervisorPanel -TbccRoot $TbccRoot -FullStack:$FullStack -OnNotify $OnNotify -OnRefreshCache $OnRefreshCache
  }.GetNewClosure())
  [void]$ctx.Items.Add($miExpand)
  $miPin = New-Object System.Windows.Forms.ToolStripMenuItem
  $miPin.Text = "Always on top"
  $miPin.Checked = $true
  [void]$miPin.Add_Click({
    $form.TopMost = -not $form.TopMost
    $miPin.Checked = $form.TopMost
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
    TbccRoot  = $TbccRoot
    FullStack = [bool]$FullStack
    OnNotify  = $OnNotify
    OnRefreshCache = $OnRefreshCache
  }

  if ($script:TbccSupMiniRefreshTimer) {
    try { $script:TbccSupMiniRefreshTimer.Stop(); $script:TbccSupMiniRefreshTimer.Dispose() } catch {}
    $script:TbccSupMiniRefreshTimer = $null
  }
  $script:TbccSupMiniRefreshTimer = New-Object System.Windows.Forms.Timer
  $miniTimer = $script:TbccSupMiniRefreshTimer
  $miniTimer.Interval = 4000
  $script:TbccSupMiniClosing = $false
  [void]$miniTimer.Add_Tick({
    if ($script:TbccSupMiniClosing) { return }
    if (-not $script:TbccSupMiniForm -or $script:TbccSupMiniForm.IsDisposed) { return }
    if ($script:TbccSupPanelForm -and -not $script:TbccSupPanelForm.IsDisposed) { return }
    if ($script:TbccSupMiniBusy) { return }
    $script:TbccSupMiniBusy = $true
    try {
      $ui = $script:TbccSupMiniUi
      if (-not $ui -or [string]::IsNullOrWhiteSpace($ui.TbccRoot)) { return }
      $snap = Get-TbccSupervisorHealthSnapshot -TbccRoot $ui.TbccRoot -FullStack:([bool]$ui.FullStack) -NetPrev $ui.NetPrev
      if ($snap.Host.Net) { $ui.NetPrev = $snap.Host.Net }
      Update-TbccSupMiniUi -Snap $snap
      if ($ui.OnRefreshCache -and $snap.Cache) { & $ui.OnRefreshCache $snap.Cache }
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

  # After the fast first tick, settle into the normal cadence (sender = the timer;
  # local $miniTimer is out of scope by the time ticks fire).
  [void]$miniTimer.Add_Tick({
    param($s, $e)
    if ($s.Interval -ne 4000) { $s.Interval = 4000 }
  })

  $form.Add_Load({
    # Don't snapshot synchronously here — it blocks the first paint. Fire the timer
    # quickly once instead.
    $t = $script:TbccSupMiniRefreshTimer
    if (-not $t) { return }
    $t.Interval = 250
    $t.Start()
  })

  [void]$form.Add_MouseDoubleClick({
    $ui = $script:TbccSupMiniUi
    if (-not $ui -or [string]::IsNullOrWhiteSpace($ui.TbccRoot)) { return }
    Show-TbccSupervisorPanel -TbccRoot $ui.TbccRoot -FullStack:([bool]$ui.FullStack) `
      -OnNotify $ui.OnNotify -OnRefreshCache $ui.OnRefreshCache
  })

  $tip.SetToolTip($chkPin, "Always on top")
  $tip.SetToolTip($btnMin, "Minimize to taskbar")
  $tip.SetToolTip($form, "Double-click for full panel | right-click menu")
  $script:TbccSupMiniForm = $form
  try {
    [void]$form.Show()
    $form.BringToFront()
    $form.Activate()
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
    $fill = if ($pct -ge 95) { $t.Ok } elseif ($pct -ge 70) { $t.Warn } else { $t.Crit }
    $auditBit = ""
    if ($Snap.ProcessAudit -and [int]$Snap.ProcessAudit.issueCount -gt 0) {
      $micro = if ($Snap.ProcessAudit.summaryMicro) { [string]$Snap.ProcessAudit.summaryMicro } else { "!" }
      $auditBit = " | " + $micro
      if ([int]$Snap.ProcessAudit.issueCount -gt 0) { $fill = $t.Warn }
    }
    $script:TbccSupMiniUi.LblStack.Text = ("{0}/{1} up{2}" -f $cache.EnabledUp, $cache.Enabled, $auditBit)
    $script:TbccSupMiniUi.LblStack.ForeColor = $fill
  }
  $hostSnap = $Snap.Host
  if ($null -ne $hostSnap.CpuPct) {
    Push-TbccSupSparklineSample -Canvas $script:TbccSupMiniUi.CpuSpark -Value ([double]$hostSnap.CpuPct)
  }
  if ($null -ne $hostSnap.RamPct) {
    Push-TbccSupSparklineSample -Canvas $script:TbccSupMiniUi.RamSpark -Value ([double]$hostSnap.RamPct)
  }
  $hubCrit = 0
  $hubWarn = 0
  foreach ($entry in @($Snap.HubLines)) {
    $txt = if ($entry.Text) { [string]$entry.Text } else { [string]$entry }
    $sev = Get-TbccHubLineSeverity -Line $txt
    if ($sev -eq "crit") { $hubCrit++ } elseif ($sev -eq "warn") { $hubWarn++ }
  }
  $netTxt = "NET -"
  if ($hostSnap.Net) {
    $netTxt = ("NET dn {0} up {1}" -f (Format-TbccBitrate $hostSnap.Net.DownBps), (Format-TbccBitrate $hostSnap.Net.UpBps))
  }
  $hubColor = if ($hubCrit -gt 0) { $t.Crit } elseif ($hubWarn -gt 0) { $t.Warn } else { $t.Ok }
  $script:TbccSupMiniUi.Foot.Text = ("HUB {0}w {1}c  |  {2}" -f $hubWarn, $hubCrit, $netTxt)
  $script:TbccSupMiniUi.Foot.ForeColor = $hubColor
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

  if ($script:TbccSupPanelForm -and -not $script:TbccSupPanelForm.IsDisposed) {
    $script:TbccSupPanelClosing = $false
    if ($script:TbccSupUi) { $script:TbccSupUi.TbccRoot = $TbccRoot }
    $script:TbccSupPanelForm.Show()
    $script:TbccSupPanelForm.WindowState = [System.Windows.Forms.FormWindowState]::Normal
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

  $form = New-Object System.Windows.Forms.Form
  $form.Text = "TBCC Supervisor"
  $form.AutoScaleMode = [System.Windows.Forms.AutoScaleMode]::None
  $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedSingle
  $form.MaximizeBox = $false
  $form.MinimizeBox = $true
  $form.ClientSize = New-Object System.Drawing.Size(450, 320)
  $form.MinimumSize = $form.Size
  $form.MaximumSize = $form.Size
  $form.BackColor = $theme.Bg
  $form.ForeColor = $theme.Text
  $form.Font = $theme.FontLabel
  $form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
  $form.ShowInTaskbar = $true

  $toolStrip = New-Object System.Windows.Forms.Panel
  $toolStrip.Dock = [System.Windows.Forms.DockStyle]::Top
  $toolStrip.Height = 20
  $toolStrip.BackColor = $theme.HeaderBg
  $form.Controls.Add($toolStrip)

  $chkTop = New-Object System.Windows.Forms.CheckBox
  $chkTop.Text = "Pin"
  $chkTop.AutoSize = $true
  $chkTop.Left = 4
  $chkTop.Top = 2
  $chkTop.ForeColor = $theme.Muted
  $chkTop.Font = $theme.FontMicro
  $chkTop.BackColor = $theme.HeaderBg
  [void]$chkTop.Add_CheckedChanged({
    param($sender, $e)
    $f = $script:TbccSupPanelForm
    if ($f -and -not $f.IsDisposed) { $f.TopMost = $sender.Checked }
  })
  $toolStrip.Controls.Add($chkTop)

  $btnMini = New-Object System.Windows.Forms.Button
  $btnMini.Text = "Mini"
  $btnMini.Width = 36
  $btnMini.Height = 16
  $btnMini.Top = 2
  $btnMini.Left = 44
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
  $btnHubLog.Width = 36
  $btnHubLog.Height = 16
  $btnHubLog.Top = 2
  $btnHubLog.Left = 84
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

  $root = New-Object System.Windows.Forms.TableLayoutPanel
  $root.Dock = [System.Windows.Forms.DockStyle]::Fill
  $root.BackColor = $theme.Bg
  $root.ColumnCount = 2
  $root.RowCount = 4
  $root.Padding = New-Object System.Windows.Forms.Padding(1)
  [void]$root.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 50)))
  [void]$root.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 50)))
  [void]$root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 58)))
  [void]$root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 52)))
  [void]$root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 72)))
  [void]$root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 100)))
  $form.Controls.Add($root)

  # --- Row0: Stack | Host ---
  $modStack = New-TbccSupModule -Title "Stack" -Theme $theme
  $modHost = New-TbccSupModule -Title "Host" -Theme $theme
  [void]$root.Controls.Add($modStack.Outer, 0, 0)
  [void]$root.Controls.Add($modHost.Outer, 1, 0)

  $lblStackSummary = New-Object System.Windows.Forms.Label
  $lblStackSummary.Dock = [System.Windows.Forms.DockStyle]::Top
  $lblStackSummary.Height = 13
  $lblStackSummary.ForeColor = $theme.Text
  $lblStackSummary.Font = $theme.FontTitle
  $lblStackSummary.Text = "-"
  $modStack.Body.Controls.Add($lblStackSummary)

  $barStackObj = New-TbccSupMetricBar -Label "UP" -Pct 0 -Theme $theme -FillColor $theme.Ok
  $barStackObj.Row.Height = 16
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
    $b = New-TbccSupMetricBar -Label $pair.L -Pct -1 -Theme $theme -FillColor $theme.Ok
    $b.Row.Height = 16
    $b.BarFill.Tag.HostKey = $pair.K
    $modHost.Body.Controls.Add($b.Row)
    $hostBars += $b.BarFill
  }
  $lblHostSub = New-Object System.Windows.Forms.Label
  $lblHostSub.Dock = [System.Windows.Forms.DockStyle]::Bottom
  $lblHostSub.Height = 12
  $lblHostSub.ForeColor = $theme.Muted
  $lblHostSub.Font = $theme.FontMicro
  $modHost.Body.Controls.Add($lblHostSub)

  $cpuSparkFull = New-TbccSupSparkline -Label "C" -Theme $theme -LineColor $theme.Ok
  $cpuSparkFull.Wrap.Height = 16
  $cpuSparkFull.Wrap.Dock = [System.Windows.Forms.DockStyle]::Bottom
  $modHost.Body.Controls.Add($cpuSparkFull.Wrap)
  $ramSparkFull = New-TbccSupSparkline -Label "R" -Theme $theme -LineColor ([System.Drawing.Color]::FromArgb(96, 165, 250))
  $ramSparkFull.Wrap.Height = 16
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
  $hubList.ItemHeight = 12
  $hubList.Add_DrawItem({
    param($sender, $e)
    if ($e.Index -lt 0) { return }
    $entry = $sender.Items[$e.Index]
    $line = if ($entry.Text) { [string]$entry.Text } else { [string]$entry }
    $sev = Get-TbccHubLineSeverity -Line $line
    $t = if ($script:TbccSupUi -and $script:TbccSupUi.Theme) { $script:TbccSupUi.Theme } else { Get-TbccSupervisorTheme }
    $fg = switch ($sev) {
      "crit" { $t.Crit }
      "warn" { $t.Warn }
      "ok" { $t.Muted }
      default { $t.Text }
    }
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
  $modHub.Body.Controls.Add($hubList)

  $alertList = New-Object System.Windows.Forms.ListBox
  $alertList.Dock = [System.Windows.Forms.DockStyle]::Fill
  $alertList.BackColor = [System.Drawing.Color]::FromArgb(14, 14, 16)
  $alertList.ForeColor = $theme.Text
  $alertList.Font = $theme.FontMicro
  $alertList.BorderStyle = [System.Windows.Forms.BorderStyle]::None
  $modAlert.Body.Controls.Add($alertList)

  $statusStrip = New-Object System.Windows.Forms.StatusStrip
  $statusStrip.BackColor = $theme.HeaderBg
  $statusStrip.ForeColor = $theme.Muted
  $statusStrip.SizingGrip = $false
  $statusStrip.Height = 18
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
  $refreshTimer.Interval = 4000
  $script:TbccSupPanelClosing = $false
  [void]$refreshTimer.Add_Tick({
    if ($script:TbccSupPanelClosing) { return }
    if (-not $script:TbccSupPanelForm -or $script:TbccSupPanelForm.IsDisposed) { return }
    $ui = $script:TbccSupUi
    if (-not $ui -or [string]::IsNullOrWhiteSpace($ui.TbccRoot)) { return }
    # Re-entrancy guard: a slow snapshot (WMI, netstat, HTTP) must never stack a second
    # refresh on top of itself — that starved the message pump and pegged the CPU.
    if ($script:TbccSupPanelBusy) { return }
    $script:TbccSupPanelBusy = $true
    try {
      $snap = Get-TbccSupervisorHealthSnapshot -TbccRoot $ui.TbccRoot -FullStack:([bool]$ui.FullStack) -NetPrev $ui.NetPrev
      Update-TbccSupPanelUi -Snap $snap
      if ($ui.OnRefreshCache -and $snap.Cache) {
        & $ui.OnRefreshCache $snap.Cache
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
  })
  $form.Add_FormClosed({
    $script:TbccSupPanelClosing = $true
    $t = $script:TbccSupPanelRefreshTimer
    if ($t) {
      try { $t.Stop() } catch {}
      try { $t.Dispose() } catch {}
      $script:TbccSupPanelRefreshTimer = $null
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
    if ($s.Interval -ne 4000) { $s.Interval = 4000 }
  })

  $form.Add_Load({
    # Don't snapshot synchronously here — with the API down this blocked the first
    # paint for seconds and the panel appeared as a glitched, unpainted window.
    # The fast first tick populates the UI right after the form is visible.
    $t = $script:TbccSupPanelRefreshTimer
    if (-not $t) { return }
    $t.Interval = 250
    $t.Start()
  })

  $tip.SetToolTip($chkTop, "Always on top")
  $tip.SetToolTip($btnMini, "Open compact always-on-top monitor")
  $tip.SetToolTip($btnHubLog, "Open error-hub.log in Notepad")
  $tip.SetToolTip($barStackObj.Row, "Enabled services that are up")
  $tip.SetToolTip($lblStackSub, "StackWatch process audit (from .tbcc-run\process-audit.json, ~60s refresh)")
  $tip.SetToolTip($modHost.Outer, "CPU/RAM bars and sparkline history")
  $tip.SetToolTip($modSvc.Outer, "Click toggle | Ctrl+restart")
  $tip.SetToolTip($modAlert.Outer, "Conflicts and ops alerts")
  $tip.SetToolTip($hubList, "Double-click line to jump in Notepad")

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
    $form.BringToFront()
    $form.Activate()
  } catch {
    if ($OnNotify) { & $OnNotify ("Panel open failed: " + $_.Exception.Message) }
    $script:TbccSupPanelForm = $null
    $script:TbccSupUi = $null
  }
}
