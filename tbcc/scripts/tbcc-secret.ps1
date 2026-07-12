# Paste a secret into tbcc/.env without hand-editing the file.
# Usage:
#   .\scripts\tbcc-secret.ps1 -Key TBCC_CF_API_TOKEN
#   .\scripts\tbcc-secret.ps1 -Key TBCC_R2_ACCOUNT_ID -Value "abc123"
#   .\scripts\tbcc-secret.ps1 -Key TBCC_IMGBB_API_KEY -FromClipboard
#
# Paste tip: SecureString prompts often block Ctrl+V. This script prefers clipboard,
# then a visible (non-hidden) prompt so paste works.
param(
    [Parameter(Mandatory = $true)]
    [string] $Key,
    [string] $Value = "",
    [switch] $FromClipboard,
    [switch] $Quiet
)

$ErrorActionPreference = "Stop"
$envPath = Join-Path (Split-Path $PSScriptRoot -Parent) ".env"
if (-not (Test-Path -LiteralPath $envPath)) {
    Write-Error ".env not found at $envPath"
}

function Normalize-EnvKeyName([string]$raw) {
    $k = ($raw -replace '^\s+|\s+$', '')
    if (-not $k) { return "" }
    # "TBCC GEMINI KEY" / "tbcc-cloudflare-token" -> TBCC_GEMINI_KEY / TBCC_CLOUDFLARE_TOKEN
    $k = $k -replace '[^A-Za-z0-9]+', '_'
    $k = $k -replace '_+', '_'
    $k = $k.Trim('_').ToUpperInvariant()
    $aliases = @{
        "TBCC_GEMINI_KEY"            = "TBCC_GEMINI_API_KEY"
        "GEMINI_KEY"                 = "TBCC_GEMINI_API_KEY"
        "GEMINI_API_KEY"             = "TBCC_GEMINI_API_KEY"
        "TBCC_CLOUDFLARE_TOKEN"      = "TBCC_CF_API_TOKEN"
        "CLOUDFLARE_TOKEN"           = "TBCC_CF_API_TOKEN"
        "TBCC_CLOUDFLARE_API_TOKEN"  = "TBCC_CF_API_TOKEN"
        "ACCOUNT_ID"                 = "TBCC_R2_ACCOUNT_ID"
        "R2_ACCOUNT_ID"              = "TBCC_R2_ACCOUNT_ID"
        "PUBLIC_DEVELOPMENT_URL"     = "TBCC_R2_PUBLIC_BASE_URL"
        "PUBLIC_DEV_URL"             = "TBCC_R2_PUBLIC_BASE_URL"
        "R2_PUBLIC_URL"              = "TBCC_R2_PUBLIC_BASE_URL"
        "S3_API"                     = "TBCC_R2_S3_ENDPOINT"
        "S3_ENDPOINT"                = "TBCC_R2_S3_ENDPOINT"
        "R2_S3_API"                  = "TBCC_R2_S3_ENDPOINT"
    }
    if ($aliases.ContainsKey($k)) { return $aliases[$k] }
    return $k
}

function Get-ClipboardTextSafe {
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
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

function Write-EnvFileUtf8NoBom([string]$path, [string[]]$lines) {
    $text = ($lines -join "`n") + "`n"
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($path, $text, $utf8)
}

$Key = Normalize-EnvKeyName $Key
if (-not $Key) {
    Write-Error "Key name required."
}

if ($FromClipboard -or -not $Value) {
    $clip = Get-ClipboardTextSafe
    if ($clip) {
        if (-not $Value) {
            $Value = $clip
            if (-not $Quiet) {
                Write-Host "Using clipboard ($($Value.Length) chars)." -ForegroundColor DarkGray
            }
        }
    }
}

if (-not $Value) {
    # Visible prompt - SecureString blocks Ctrl+V paste on many Windows setups.
    if (-not $Quiet) {
        Write-Host "Paste value for $Key then press Enter (input is visible so paste works):" -ForegroundColor Cyan
    }
    $Value = (Read-Host).Trim()
}

if (-not $Value) {
    Write-Error "Empty value - nothing written."
}

$lines = Get-Content -LiteralPath $envPath -Encoding UTF8
$found = $false
$out = foreach ($line in $lines) {
    if ($line -match "^\s*$([regex]::Escape($Key))\s*=") {
        $found = $true
        "$Key=$Value"
    } else {
        $line
    }
}
if (-not $found) {
    $out += "$Key=$Value"
}
Write-EnvFileUtf8NoBom $envPath $out
if (-not $Quiet) {
    Write-Host "OK: $Key updated in .env ($($Value.Length) chars)" -ForegroundColor Green
}
