# Copy a Mega link, then: clip → AdMaven wrap → pack pool
# Usage:
#   .\scripts\clip-mega-pack.ps1              # dry-run
#   .\scripts\clip-mega-pack.ps1 -Execute     # queue + wire scheduler + copy gate to clipboard
#   .\scripts\clip-mega-pack.ps1 -Execute -Label "My Pack"

param(
    [switch]$Execute,
    [string]$Label = "",
    [switch]$NoWireScheduler,
    [switch]$AppendExport
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $root "backend"
$pyArgs = @("-3.13", (Join-Path $backend "scripts\clip_mega_to_pack_pool.py"))

if ($Execute) { $pyArgs += "--execute" }
if ($Label) { $pyArgs += @("--label", $Label) }
if ($NoWireScheduler) { $pyArgs += "--no-wire-scheduler" }
if (-not $NoWireScheduler -and $Execute) { $pyArgs += "--wire-scheduler" }
if ($AppendExport) { $pyArgs += "--append-export" }

Push-Location $backend
try {
    & py @pyArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
