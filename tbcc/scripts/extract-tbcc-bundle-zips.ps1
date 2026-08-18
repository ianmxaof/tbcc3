# Extract every .zip in a TBCC bundles folder into a same-named subfolder.
#
# Usage:
#   .\scripts\extract-tbcc-bundle-zips.ps1
#   .\scripts\extract-tbcc-bundle-zips.ps1 -RootPath "C:\path\to\TBCC BUNDLES"
#   .\scripts\extract-tbcc-bundle-zips.ps1 -Force          # re-extract even if folder exists
#   .\scripts\extract-tbcc-bundle-zips.ps1 -WhatIf         # dry run

param(
    [string]$RootPath = "C:\Users\ianmp\Downloads\Porn\tbcc\AOF NETWORK\TBCC BUNDLES",
    [switch]$Force,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Get-SafeFileName {
    param(
        [string]$Name,
        [int]$MaxLength = 180
    )

    $leaf = [IO.Path]::GetFileName($Name)
    if ([string]::IsNullOrWhiteSpace($leaf)) {
        return $null
    }

    $ext = [IO.Path]::GetExtension($leaf)
    $base = [IO.Path]::GetFileNameWithoutExtension($leaf)
    $maxBase = [Math]::Max(1, $MaxLength - $ext.Length)
    if ($base.Length -gt $maxBase) {
        $base = $base.Substring(0, $maxBase)
    }
    return ($base + $ext)
}

function Get-UniquePath {
    param(
        [string]$Directory,
        [string]$FileName
    )

    $candidate = Join-Path $Directory $FileName
    if (-not (Test-Path -LiteralPath $candidate)) {
        return $candidate
    }

    $base = [IO.Path]::GetFileNameWithoutExtension($FileName)
    $ext = [IO.Path]::GetExtension($FileName)
    $n = 1
    do {
        $candidate = Join-Path $Directory ("{0} ({1}){2}" -f $base, $n, $ext)
        $n++
    } while (Test-Path -LiteralPath $candidate)

    return $candidate
}

function Expand-ZipSafe {
    param(
        [string]$ZipPath,
        [string]$DestDir
    )

    $archive = [IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        foreach ($entry in $archive.Entries) {
            if ([string]::IsNullOrWhiteSpace($entry.Name)) {
                continue
            }

            $safeName = Get-SafeFileName $entry.FullName
            if (-not $safeName) {
                continue
            }

            $destPath = Get-UniquePath -Directory $DestDir -FileName $safeName
            $destDirPath = Split-Path -Parent $destPath
            if (-not (Test-Path -LiteralPath $destDirPath)) {
                New-Item -ItemType Directory -Path $destDirPath -Force | Out-Null
            }

            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $destPath, $true)
        }
    }
    finally {
        $archive.Dispose()
    }
}

if (-not (Test-Path -LiteralPath $RootPath)) {
    Write-Error "Root path not found: $RootPath"
}

$zips = @(Get-ChildItem -LiteralPath $RootPath -Filter "*.zip" -File | Sort-Object Name)
if ($zips.Count -eq 0) {
    Write-Host "No .zip files found in: $RootPath"
    exit 0
}

Write-Host "Found $($zips.Count) zip(s) in:"
Write-Host "  $RootPath"
Write-Host ""

$ok = 0
$skipped = 0
$failed = 0

foreach ($zip in $zips) {
    $destDir = Join-Path $RootPath $zip.BaseName
    $existingFiles = @()
    if (Test-Path -LiteralPath $destDir) {
        $existingFiles = @(Get-ChildItem -LiteralPath $destDir -Recurse -File -ErrorAction SilentlyContinue)
    }

    if ($existingFiles.Count -gt 0 -and -not $Force) {
        Write-Host "[skip] $($zip.Name) -> already extracted ($($existingFiles.Count) file(s))"
        $skipped++
        continue
    }

    if ($WhatIf) {
        Write-Host "[whatif] would extract: $($zip.Name)"
        Write-Host "         -> $destDir"
        $ok++
        continue
    }

    try {
        if (-not (Test-Path -LiteralPath $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        }

        Expand-ZipSafe -ZipPath $zip.FullName -DestDir $destDir

        $count = @(Get-ChildItem -LiteralPath $destDir -Recurse -File).Count
        Write-Host "[ok]   $($zip.Name) -> $count file(s)"
        $ok++
    }
    catch {
        Write-Warning "[fail] $($zip.Name): $($_.Exception.Message)"
        $failed++
    }
}

Write-Host ""
Write-Host "Done. ok=$ok skipped=$skipped failed=$failed"
if ($failed -gt 0) { exit 1 }
