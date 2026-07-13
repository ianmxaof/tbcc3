# Capture clipboard text as a TBCC secret -> same store as browser extension
# (POST /extension/capture-secret when API is up) -> tbcc/.env + Credential Manager.
#
# Usage (after copying a key):
#   .\scripts\tbcc-capture-secret.ps1
#   .\scripts\tbcc-capture-secret.ps1 -Key TBCC_CF_API_TOKEN
#   .\scripts\tbcc-capture-secret.ps1 -FromClipboard -Quiet
#
# Context-menu launcher uses -Quiet (no console). Unknown keys open a WinForms picker.
param(
    [string] $Key = "",
    [string] $Value = "",
    [switch] $FromClipboard,
    [switch] $Quiet,
    [switch] $SkipCredentialManager,
    [switch] $OpenCredentialManager,
    [switch] $SkipApi,
    [switch] $ListKeys
)

$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path $PSScriptRoot -Parent
$envPath = Join-Path $tbccRoot ".env"
$registryPath = Join-Path $tbccRoot "backend\app\data\tbcc_env_secret_registry.json"
$logPath = Join-Path $tbccRoot ".tbcc-run\capture-secret.log"
$apiBases = @("http://127.0.0.1:8000", "http://localhost:8000")

function Write-Info([string]$msg) {
    if (-not $Quiet) { Write-Host $msg }
}

function Write-CaptureLog([string]$msg) {
    try {
        $dir = Split-Path $logPath -Parent
        if (-not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        $line = "{0:o} {1}" -f (Get-Date).ToUniversalTime(), $msg
        Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
    } catch { }
}

function Show-Balloon([string]$title, [string]$text, [string]$icon = "Info") {
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        Add-Type -AssemblyName System.Drawing -ErrorAction Stop
        $ni = New-Object System.Windows.Forms.NotifyIcon
        $ni.Icon = [System.Drawing.SystemIcons]::Information
        if ($icon -eq "Error") { $ni.Icon = [System.Drawing.SystemIcons]::Error }
        elseif ($icon -eq "Warning") { $ni.Icon = [System.Drawing.SystemIcons]::Warning }
        $ni.Visible = $true
        $toolIcon = [System.Windows.Forms.ToolTipIcon]::Info
        if ($icon -eq "Error") { $toolIcon = [System.Windows.Forms.ToolTipIcon]::Error }
        elseif ($icon -eq "Warning") { $toolIcon = [System.Windows.Forms.ToolTipIcon]::Warning }
        $ni.ShowBalloonTip(5000, $title, $text, $toolIcon)
        Start-Sleep -Milliseconds 600
        $ni.Visible = $false
        $ni.Dispose()
    } catch { }
}

function Open-CredentialManager {
    try {
        Start-Process -FilePath "control.exe" -ArgumentList "/name Microsoft.CredentialManager" -ErrorAction Stop
        return
    } catch { }
    try {
        Start-Process "explorer.exe" "shell:::{1206F5F1-0569-412C-8FEC-3204630DFB70}" -ErrorAction SilentlyContinue
    } catch { }
}

function Get-ClipboardText {
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        $t = [System.Windows.Forms.Clipboard]::GetText()
        if ($null -ne $t -and "$t".Length -gt 0) {
            return ("$t" -replace "`r`n", "" -replace "`n", "" -replace "`r", "").Trim()
        }
    } catch { }
    try {
        $raw = Get-Clipboard -Raw -ErrorAction Stop
        if ($null -eq $raw) { return "" }
        return ("$raw" -replace "`r`n", "" -replace "`n", "" -replace "`r", "").Trim()
    } catch {
        return ""
    }
}

function Normalize-SecretValue([string]$text, [string]$envKey) {
    $t = ($text -replace '^\s+|\s+$', '')
    if (-not $t) { return $t }
    # Dashboard "S3 API" copy often includes /bucket - store host only.
    if ($envKey -eq "TBCC_R2_S3_ENDPOINT" -or $t -match '\.r2\.cloudflarestorage\.com/') {
        if ($t -match '^(https://[a-z0-9.-]+\.r2\.cloudflarestorage\.com)(/.*)?$') {
            return $Matches[1]
        }
    }
    if ($envKey -eq "TBCC_R2_PUBLIC_BASE_URL" -or $t -match '^https://pub-[a-z0-9]+\.r2\.dev/') {
        if ($t -match '^(https://pub-[a-z0-9]+\.r2\.dev)(/.*)?$') {
            return $Matches[1]
        }
    }
    return $t.TrimEnd('/')
}

function Normalize-EnvKeyName([string]$raw) {
    $k = ($raw -replace '^\s+|\s+$', '')
    if (-not $k) { return "" }
    $k = $k -replace '[^A-Za-z0-9]+', '_'
    $k = $k -replace '_+', '_'
    $k = $k.Trim('_').ToUpperInvariant()
    $aliases = @{
        "TBCC_GEMINI_KEY"           = "TBCC_GEMINI_API_KEY"
        "GEMINI_KEY"                = "TBCC_GEMINI_API_KEY"
        "GEMINI_API_KEY"            = "TBCC_GEMINI_API_KEY"
        "TBCC_CLOUDFLARE_TOKEN"     = "TBCC_CF_API_TOKEN"
        "CLOUDFLARE_TOKEN"          = "TBCC_CF_API_TOKEN"
        "TBCC_CLOUDFLARE_API_TOKEN" = "TBCC_CF_API_TOKEN"
        "ACCOUNT_ID"                = "TBCC_R2_ACCOUNT_ID"
        "R2_ACCOUNT_ID"             = "TBCC_R2_ACCOUNT_ID"
        "PUBLIC_DEVELOPMENT_URL"    = "TBCC_R2_PUBLIC_BASE_URL"
        "PUBLIC_DEV_URL"            = "TBCC_R2_PUBLIC_BASE_URL"
        "R2_PUBLIC_URL"             = "TBCC_R2_PUBLIC_BASE_URL"
        "S3_API"                    = "TBCC_R2_S3_ENDPOINT"
        "S3_ENDPOINT"               = "TBCC_R2_S3_ENDPOINT"
        "R2_S3_API"                 = "TBCC_R2_S3_ENDPOINT"
    }
    if ($aliases.ContainsKey($k)) { return $aliases[$k] }
    return $k
}

function Test-LooksLikeApiKey([string]$text) {
    $t = $text.Trim()
    if ($t.Length -lt 12 -or $t.Length -gt 600) { return $false }
    if ($t -match "\s") { return $false }
    if ($t -match '^(sk-|pk_|r8_|ghp_|gho_|github_pat_|xox[baprs]-|AIza|Bearer\s|tskey-|tskey-auth-)') { return $true }
    if ($t -match '^https://pub-[a-z0-9]+\.r2\.dev(/.*)?$') { return $true }
    # Account subdomain +/- optional /bucket path (dashboard often copies .../aof-x-promo)
    if ($t -match '^https://[a-z0-9.-]+\.r2\.cloudflarestorage\.com(/[A-Za-z0-9._-]*)?/?$') { return $true }
    if ($t -match '^[A-Za-z0-9._\-+/=]{16,}$') { return $true }
    return $false
}

function Get-RegistryHints {
    if (-not (Test-Path -LiteralPath $registryPath)) { return @() }
    try {
        $data = Get-Content -LiteralPath $registryPath -Raw -Encoding UTF8 | ConvertFrom-Json
        return @($data.hints)
    } catch {
        return @()
    }
}

function Get-KnownKeyFallbacks {
    return @(
        "TBCC_CF_API_TOKEN",
        "TBCC_R2_ACCOUNT_ID",
        "TBCC_R2_PUBLIC_BASE_URL",
        "TBCC_R2_S3_ENDPOINT",
        "TBCC_R2_ACCESS_KEY_ID",
        "TBCC_R2_SECRET_ACCESS_KEY",
        "TBCC_IMGBB_API_KEY",
        "TBCC_GEMINI_API_KEY",
        "TBCC_PIXELDRAIN_API_KEY",
        "BUFFER_API_TOKEN",
        "OPENROUTER_API_KEY",
        "REPLICATE_API_TOKEN",
        "TBCC_TAILSCALE_AUTHKEY",
        "TBCC_GHCR_TOKEN"
    )
}

function Get-ActiveBrowserUrl {
    try {
        $shell = New-Object -ComObject Shell.Application
        foreach ($w in $shell.Windows()) {
            $loc = $w.LocationURL
            if ($loc -and $loc -match '^https?://') { return [string]$loc }
        }
    } catch { }
    return ""
}

function Suggest-EnvKey([string]$text, [string]$pageUrl) {
    $hints = Get-RegistryHints
    $url = if ($pageUrl) { $pageUrl.ToLower() } else { "" }
    foreach ($h in $hints) {
        $pat = [string]$h.pattern
        if ($pat -and $text -match $pat) {
            return [string]$h.suggest_key
        }
    }
    foreach ($h in $hints) {
        $mu = [string]$h.match_url
        if ($mu -and $url -like "*$mu*") {
            return [string]$h.suggest_key
        }
        $mt = [string]$h.match_title
        if ($mt -and $url -like "*$mt*") {
            return [string]$h.suggest_key
        }
    }
    # High-confidence local heuristics (no ImgBB-on-any-32-hex - that stole Cloudflare Account IDs).
    if ($text -match '^https://pub-[a-z0-9]+\.r2\.dev(/.*)?$') { return "TBCC_R2_PUBLIC_BASE_URL" }
    if ($text -match '^https://[a-z0-9.-]+\.r2\.cloudflarestorage\.com(/.*)?$') { return "TBCC_R2_S3_ENDPOINT" }
    if ($text -match '^AIza') { return "TBCC_GEMINI_API_KEY" }
    if ($text -match '^tskey-') { return "TBCC_TAILSCALE_AUTHKEY" }
    if ($text -match '^sk-or-') { return "OPENROUTER_API_KEY" }
    if ($text -match '^r8_') { return "REPLICATE_API_TOKEN" }
    if ($text -match '^(ghp_|gho_|github_pat_)') { return "TBCC_GHCR_TOKEN" }
    if ($text -match '^[a-f0-9]{32}$') { return "TBCC_R2_ACCOUNT_ID" }
    return ""
}

function Get-EnvKeysFromFile {
    if (-not (Test-Path -LiteralPath $envPath)) { return @() }
    $keys = @()
    foreach ($line in Get-Content -LiteralPath $envPath -Encoding UTF8) {
        if ($line -match '^\s*(TBCC_[A-Z0-9_]+|BUFFER_[A-Z0-9_]+|OPENROUTER_[A-Z0-9_]+|REPLICATE_[A-Z0-9_]+|GEMINI_[A-Z0-9_]+)\s*=') {
            $keys += $Matches[1]
        }
    }
    return $keys | Sort-Object -Unique
}

function Test-WindowsAppsUseDarkTheme {
    try {
        $v = Get-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize" -Name "AppsUseLightTheme" -ErrorAction Stop
        return ([int]$v.AppsUseLightTheme -eq 0)
    } catch {
        return $true  # default dark to match TBCC / Cursor chrome
    }
}

function Show-KeyPicker([string]$preview, [string]$suggested) {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $choices = @(Get-EnvKeysFromFile)
    if (-not $choices.Count) { $choices = Get-KnownKeyFallbacks }
    foreach ($fb in (Get-KnownKeyFallbacks)) {
        if ($choices -notcontains $fb) { $choices += $fb }
    }
    if ($suggested -and ($choices -notcontains $suggested)) {
        $choices = @($suggested) + $choices
    }

    $dark = Test-WindowsAppsUseDarkTheme
    # Dark palette matched to Cursor/editor charcoal (~#1e1e1e / #2d2d2d).
    if ($dark) {
        $bg       = [System.Drawing.Color]::FromArgb(255, 30, 30, 30)      # #1e1e1e
        $bgInput  = [System.Drawing.Color]::FromArgb(255, 45, 45, 45)      # #2d2d2d
        $fg       = [System.Drawing.Color]::FromArgb(255, 220, 220, 220)
        $fgMuted  = [System.Drawing.Color]::FromArgb(255, 160, 160, 160)
        $btnFace  = [System.Drawing.Color]::FromArgb(255, 55, 55, 55)
        $btnText  = [System.Drawing.Color]::FromArgb(255, 230, 230, 230)
    } else {
        $bg       = [System.Drawing.SystemColors]::Control
        $bgInput  = [System.Drawing.SystemColors]::Window
        $fg       = [System.Drawing.SystemColors]::ControlText
        $fgMuted  = [System.Drawing.SystemColors]::GrayText
        $btnFace  = [System.Drawing.SystemColors]::Control
        $btnText  = [System.Drawing.SystemColors]::ControlText
    }

    $form = New-Object System.Windows.Forms.Form
    $form.Text = "TBCC - Save API key"
    $form.Size = New-Object System.Drawing.Size(480, 280)
    $form.StartPosition = "CenterScreen"
    $form.TopMost = $true
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.ShowInTaskbar = $true
    $form.BackColor = $bg
    $form.ForeColor = $fg

    $lbl = New-Object System.Windows.Forms.Label
    $lbl.Location = New-Object System.Drawing.Point(12, 12)
    $lbl.Size = New-Object System.Drawing.Size(440, 40)
    $lbl.Text = "Clipboard looks like a secret ($($preview.Length) chars). Pick the .env key:"
    $lbl.BackColor = $bg
    $lbl.ForeColor = $fg
    $form.Controls.Add($lbl)

    $prev = New-Object System.Windows.Forms.Label
    $prev.Location = New-Object System.Drawing.Point(12, 52)
    $prev.Size = New-Object System.Drawing.Size(440, 24)
    $head = if ($preview.Length -gt 6) { $preview.Substring(0, 6) } else { $preview }
    $tail = if ($preview.Length -gt 4) { $preview.Substring($preview.Length - 4) } else { "" }
    $prev.Text = "$head...$tail"
    $prev.BackColor = $bg
    $prev.ForeColor = $fgMuted
    $form.Controls.Add($prev)

    $combo = New-Object System.Windows.Forms.ComboBox
    $combo.Location = New-Object System.Drawing.Point(12, 84)
    $combo.Size = New-Object System.Drawing.Size(440, 28)
    $combo.DropDownStyle = "DropDown"
    $combo.FlatStyle = "Flat"
    $combo.BackColor = $bgInput
    $combo.ForeColor = $fg
    foreach ($c in $choices) { [void]$combo.Items.Add($c) }
    if ($suggested) { $combo.Text = $suggested }
    elseif ($combo.Items.Count -gt 0) { $combo.SelectedIndex = 0 }
    $form.Controls.Add($combo)

    $ok = New-Object System.Windows.Forms.Button
    $ok.Text = "Save to .env"
    $ok.Location = New-Object System.Drawing.Point(250, 150)
    $ok.Size = New-Object System.Drawing.Size(100, 32)
    $ok.FlatStyle = "Flat"
    $ok.BackColor = $btnFace
    $ok.ForeColor = $btnText
    $ok.FlatAppearance.BorderColor = $fgMuted
    $ok.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $ok.UseVisualStyleBackColor = $false
    $form.AcceptButton = $ok
    $form.Controls.Add($ok)

    $cancel = New-Object System.Windows.Forms.Button
    $cancel.Text = "Cancel"
    $cancel.Location = New-Object System.Drawing.Point(360, 150)
    $cancel.Size = New-Object System.Drawing.Size(90, 32)
    $cancel.FlatStyle = "Flat"
    $cancel.BackColor = $btnFace
    $cancel.ForeColor = $btnText
    $cancel.FlatAppearance.BorderColor = $fgMuted
    $cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $cancel.UseVisualStyleBackColor = $false
    $form.CancelButton = $cancel
    $form.Controls.Add($cancel)

    $hint = New-Object System.Windows.Forms.Label
    $hint.Location = New-Object System.Drawing.Point(12, 200)
    $hint.Size = New-Object System.Drawing.Size(440, 40)
    $hint.BackColor = $bg
    $hint.ForeColor = $fgMuted
    $hint.Text = "Same store as browser extension. Also backs up to Windows Credential Manager as TBCC/<KEY>."
    $form.Controls.Add($hint)

    [void]$form.Activate()
    $result = $form.ShowDialog()
    if ($result -ne [System.Windows.Forms.DialogResult]::OK) { return "" }
    return (Normalize-EnvKeyName ($combo.Text))
}

function Set-CredentialManagerSecret([string]$envKey, [string]$secret) {
    $target = "TBCC/$envKey"
    & cmdkey /generic:$target /user:tbcc /pass:$secret | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "cmdkey failed (exit $LASTEXITCODE)"
    }
}

function Invoke-CaptureSecretApi([string]$secretValue, [string]$envKey, [string]$pageUrl) {
    $bodyObj = @{ value = $secretValue }
    if ($envKey) { $bodyObj.key = $envKey }
    if ($pageUrl) { $bodyObj.page_url = $pageUrl }
    $json = $bodyObj | ConvertTo-Json -Compress
    foreach ($base in $apiBases) {
        try {
            $resp = Invoke-RestMethod -Method Post -Uri "$base/extension/capture-secret" `
                -ContentType "application/json; charset=utf-8" -Body $json -TimeoutSec 8
            if ($resp -and $resp.ok) {
                return @{
                    ok        = $true
                    key       = [string]$resp.key
                    backed_up = [bool]$resp.backed_up_credential_manager
                    via       = "api:$base"
                }
            }
        } catch {
            $status = $null
            try { $status = [int]$_.Exception.Response.StatusCode } catch { }
            if ($status -eq 422) {
                return @{ ok = $false; need_key = $true; via = "api:$base" }
            }
            if ($status -eq 400) {
                return @{ ok = $false; bad_value = $true; via = "api:$base"; error = "$_" }
            }
        }
    }
    return @{ ok = $false; offline = $true }
}

Write-CaptureLog "START quiet=$Quiet fromClipboard=$FromClipboard keyLen=$($Key.Length)"

if ($ListKeys) {
    Get-EnvKeysFromFile | ForEach-Object { Write-Host $_ }
    exit 0
}

if ($FromClipboard -or -not $Value) {
    $Value = Get-ClipboardText
}
if (-not $Value) {
    Write-CaptureLog "FAIL empty clipboard"
    if ($Quiet) {
        Show-Balloon "TBCC secrets" "Clipboard empty - copy the API key first." "Warning"
        exit 1
    }
    Write-Error "Clipboard empty. Copy the API key first, then re-run."
}
if (-not (Test-LooksLikeApiKey $Value)) {
    Write-CaptureLog "FAIL not-api-key len=$($Value.Length)"
    if ($Quiet) {
        Show-Balloon "TBCC secrets" "Not recognized as a secret shape ($($Value.Length) chars). Copy value only." "Warning"
        exit 1
    }
    Write-Host "Clipboard does not look like an API key ($($Value.Length) chars)." -ForegroundColor Yellow
    $confirm = Read-Host "Save anyway? [y/N]"
    if ($confirm -notmatch '^[yY]') { exit 1 }
}

$pageUrl = Get-ActiveBrowserUrl
if ($Key) {
    $Key = Normalize-EnvKeyName $Key
}
if (-not $Key) {
    $Key = Suggest-EnvKey $Value $pageUrl
    if ($Key) { $Key = Normalize-EnvKeyName $Key }
}

# Desktop Quiet path: always show picker so the user can confirm/override the guessed key.
# (Auto-guess alone skipped the dialog for pub-*.r2.dev -> TBCC_R2_PUBLIC_BASE_URL.)
if ($Quiet) {
    $picked = Show-KeyPicker -preview $Value -suggested $Key
    if (-not $picked) {
        Write-CaptureLog "FAIL picker cancelled (suggested was '$Key')"
        Show-Balloon "TBCC secrets" "Cancelled - no key saved." "Warning"
        exit 1
    }
    $Key = $picked
} elseif (-not $Key) {
    Write-Host "Known .env keys:" -ForegroundColor Cyan
    $choices = Get-EnvKeysFromFile
    if (-not $choices.Count) { $choices = Get-KnownKeyFallbacks }
    $i = 0
    foreach ($c in $choices) {
        $i++
        Write-Host ("  {0,2}. {1}" -f $i, $c)
    }
    Write-Host "  0. Type custom key name"
    $pick = Read-Host "Pick number for this secret"
    if ($pick -eq "0") {
        $Key = Normalize-EnvKeyName (Read-Host "Env var name (e.g. TBCC_CF_API_TOKEN)")
    } elseif ($pick -match '^\d+$' -and [int]$pick -ge 1 -and [int]$pick -le $choices.Count) {
        $Key = $choices[[int]$pick - 1]
    } else {
        Write-Error "Invalid pick."
    }
}

$Key = Normalize-EnvKeyName $Key
if (-not $Key) { Write-Error "Key name required." }
$Value = Normalize-SecretValue $Value $Key

$savedVia = "local"
$apiBackedUp = $false
if (-not $SkipApi) {
    $apiResult = Invoke-CaptureSecretApi -secretValue $Value -envKey $Key -pageUrl $pageUrl
    if ($apiResult.ok) {
        $Key = [string]$apiResult.key
        $savedVia = [string]$apiResult.via
        $apiBackedUp = [bool]$apiResult.backed_up
        Write-CaptureLog "OK $Key ($($Value.Length) chars) via $savedVia"
        Write-Info "Done via API. $Key is in .env (+ Credential Manager backup)."
        if ($Quiet) {
            Show-Balloon "TBCC secrets" "Saved $Key to .env (+ Credential Manager)." "Info"
        }
        if ($OpenCredentialManager) { Open-CredentialManager }
        exit 0
    }
    if ($apiResult.bad_value) {
        Write-CaptureLog "FAIL api bad_value: $($apiResult.error)"
        if ($Quiet) {
            Show-Balloon "TBCC secrets" "Value rejected by API (not an API-key shape)." "Warning"
            exit 1
        }
        Write-Error "API rejected value: $($apiResult.error)"
    }
    if ($apiResult.need_key -and $Quiet -and -not $Key) {
        $Key = Show-KeyPicker -preview $Value -suggested ""
        if (-not $Key) {
            Write-CaptureLog "FAIL picker cancelled after api 422"
            Show-Balloon "TBCC secrets" "Cancelled - no key saved." "Warning"
            exit 1
        }
        $apiResult = Invoke-CaptureSecretApi -secretValue $Value -envKey $Key -pageUrl $pageUrl
        if ($apiResult.ok) {
            $Key = [string]$apiResult.key
            Write-CaptureLog "OK $Key ($($Value.Length) chars) via $($apiResult.via)"
            if ($Quiet) {
                Show-Balloon "TBCC secrets" "Saved $Key to .env (+ Credential Manager)." "Info"
            }
            if ($OpenCredentialManager) { Open-CredentialManager }
            exit 0
        }
    }
    Write-CaptureLog "INFO api unavailable - local fallback"
}

$secretScript = Join-Path $PSScriptRoot "tbcc-secret.ps1"
if (-not (Test-Path -LiteralPath $secretScript)) {
    Write-CaptureLog "FAIL missing tbcc-secret.ps1"
    if ($Quiet) {
        Show-Balloon "TBCC secrets" "Missing tbcc-secret.ps1" "Error"
        exit 1
    }
    Write-Error "Missing $secretScript"
}

if ($Quiet) {
    & $secretScript -Key $Key -Value $Value -Quiet
} else {
    & $secretScript -Key $Key -Value $Value
}

if (-not $SkipCredentialManager) {
    try {
        Set-CredentialManagerSecret $Key $Value
        Write-Info "Backed up to Windows Credential Manager: TBCC/$Key"
        $apiBackedUp = $true
    } catch {
        if (-not $Quiet) {
            Write-Host "Credential Manager backup skipped: $_" -ForegroundColor Yellow
        }
        Write-CaptureLog "WARN cmdkey failed: $_"
    }
}

Write-CaptureLog "OK $Key ($($Value.Length) chars) via local"
Write-Info "Done. $Key is in .env$(if ($apiBackedUp) { ' (+ Credential Manager)' } else { '' })."
if ($pageUrl) { Write-Info "Context URL: $pageUrl" }

if ($Quiet) {
    Show-Balloon "TBCC secrets" "Saved $Key to .env$(if ($apiBackedUp) { ' (+ Credential Manager)' } else { '' })." "Info"
}

if ($OpenCredentialManager) {
    Open-CredentialManager
}
