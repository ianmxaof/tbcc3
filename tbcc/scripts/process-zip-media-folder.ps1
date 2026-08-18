# Extract zips -> flatten media to root -> dedupe by hash -> clean folder layout.
# Works on any directory passed via -RootPath.
#
# Usage:
#   .\scripts\process-zip-media-folder.ps1 -RootPath "C:\path\to\folder"
#   .\scripts\process-zip-media-folder.ps1 -RootPath "C:\path\to\folder" -WhatIf
#   .\scripts\process-zip-media-folder.ps1 -RootPath "C:\path\to\folder" -Force
#   .\scripts\process-zip-media-folder.ps1 -RootPath "C:\path\to\folder" -SkipExtract
#   .\scripts\process-zip-media-folder.ps1 -RootPath "C:\path\to\folder" -SkipDedupe

param(
    [Parameter(Mandatory = $true)]
    [string]$RootPath,
    [switch]$Force,
    [switch]$WhatIf,
    [switch]$SkipExtract,
    [switch]$SkipFlatten,
    [switch]$SkipDedupe
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem

$MediaExtensions = @(
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif",
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".flv", ".mpeg", ".mpg", ".3gp"
)

$SkipDirNames = @('_zips')
$ZipArchiveName = '_zips'

function Write-Step {
    param([string]$Title)
    Write-Host ""
    Write-Host "=== $Title ==="
    Write-Host ""
}

function Get-SafeFileName {
    param(
        [string]$Name,
        [int]$MaxLength = 180
    )

    $leaf = [IO.Path]::GetFileName($Name)
    if ([string]::IsNullOrWhiteSpace($leaf)) { return $null }

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
    if (-not (Test-Path -LiteralPath $candidate)) { return $candidate }

    $base = [IO.Path]::GetFileNameWithoutExtension($FileName)
    $ext = [IO.Path]::GetExtension($FileName)
    $n = 1
    do {
        $candidate = Join-Path $Directory ("{0} ({1}){2}" -f $base, $n, $ext)
        $n++
    } while (Test-Path -LiteralPath $candidate)

    return $candidate
}

function Get-PrefixedRootPath {
    param(
        [string]$Directory,
        [string]$FolderName,
        [string]$FileName
    )

    $safeFolder = ($FolderName -replace '[\\/:*?"<>|]', '_').Trim()
    if ([string]::IsNullOrWhiteSpace($safeFolder)) { $safeFolder = "bundle" }

    $prefixed = "{0}__{1}" -f $safeFolder, $FileName
    return Get-UniquePath -Directory $Directory -FileName $prefixed
}

function Expand-ZipSafe {
    param(
        [string]$ZipPath,
        [string]$DestDir
    )

    $archive = [IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        foreach ($entry in $archive.Entries) {
            if ([string]::IsNullOrWhiteSpace($entry.Name)) { continue }

            $safeName = Get-SafeFileName $entry.FullName
            if (-not $safeName) { continue }

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

function Get-KeepScore {
    param([System.IO.FileInfo]$File)

    $name = $File.Name
    $score = 0
    if ($File.DirectoryName -eq $RootPath) { $score += 5000 }
    if ($name -notmatch '__') { $score += 1000 }
    if ($name -notmatch ' \(\d+\)\.') { $score += 100 }
    $score -= $name.Length
    return $score
}

function Pick-Keeper {
    param([System.IO.FileInfo[]]$Files)
    return ($Files | Sort-Object { Get-KeepScore $_ } -Descending | Select-Object -First 1)
}

function Test-SkipDir {
    param([string]$Name)
    return ($SkipDirNames -contains $Name)
}

if (-not (Test-Path -LiteralPath $RootPath)) {
    Write-Error "Root path not found: $RootPath"
}

$RootPath = (Resolve-Path -LiteralPath $RootPath).Path

Write-Host "Processing:"
Write-Host "  $RootPath"
if ($WhatIf) { Write-Host "  (dry run)" }

$stats = @{
    extracted = 0
    extractSkipped = 0
    extractFailed = 0
    flattened = 0
    flattenFailed = 0
    deduped = 0
    junkRemoved = 0
    emptyDirsRemoved = 0
    zipsArchived = 0
    failed = 0
}

# --- Step 1: Extract zips ---
if (-not $SkipExtract) {
    Write-Step "1/3 Extract zips"

    $zips = @(Get-ChildItem -LiteralPath $RootPath -Filter "*.zip" -File | Sort-Object Name)
    Write-Host "Found $($zips.Count) zip(s)"

    foreach ($zip in $zips) {
        $destDir = Join-Path $RootPath $zip.BaseName
        $existingFiles = @()
        if (Test-Path -LiteralPath $destDir) {
            $existingFiles = @(Get-ChildItem -LiteralPath $destDir -Recurse -File -EA SilentlyContinue)
        }

        if ($existingFiles.Count -gt 0 -and -not $Force) {
            Write-Host "[skip] $($zip.Name) -> already extracted ($($existingFiles.Count) file(s))"
            $stats.extractSkipped++
            continue
        }

        if ($WhatIf) {
            Write-Host "[whatif] extract: $($zip.Name)"
            $stats.extracted++
            continue
        }

        try {
            if (-not (Test-Path -LiteralPath $destDir)) {
                New-Item -ItemType Directory -Path $destDir -Force | Out-Null
            }
            Expand-ZipSafe -ZipPath $zip.FullName -DestDir $destDir
            $count = @(Get-ChildItem -LiteralPath $destDir -Recurse -File).Count
            Write-Host "[ok]   $($zip.Name) -> $count file(s)"
            $stats.extracted++
        }
        catch {
            Write-Warning "[fail] $($zip.Name): $($_.Exception.Message)"
            $stats.extractFailed++
            $stats.failed++
        }
    }
}

# --- Step 2: Flatten media to root ---
if (-not $SkipFlatten) {
    Write-Step "2/3 Flatten media to root"

    $subdirs = @(
        Get-ChildItem -LiteralPath $RootPath -Directory |
            Where-Object { -not (Test-SkipDir $_.Name) }
    )

    Write-Host "Scanning $($subdirs.Count) folder(s)"

    foreach ($dir in $subdirs) {
        $mediaFiles = @(
            Get-ChildItem -LiteralPath $dir.FullName -Recurse -File |
                Where-Object { $MediaExtensions -contains $_.Extension.ToLowerInvariant() }
        )
        if ($mediaFiles.Count -eq 0) { continue }

        Write-Host "[$($dir.Name)] $($mediaFiles.Count) media file(s)"

        foreach ($file in $mediaFiles) {
            $destPath = Get-UniquePath -Directory $RootPath -FileName $file.Name
            if ($destPath -ne (Join-Path $RootPath $file.Name)) {
                $destPath = Get-PrefixedRootPath -Directory $RootPath -FolderName $dir.Name -FileName $file.Name
            }

            if ($WhatIf) {
                $stats.flattened++
                continue
            }

            try {
                Move-Item -LiteralPath $file.FullName -Destination $destPath
                $stats.flattened++
            }
            catch {
                Write-Warning "[fail] $($file.FullName): $($_.Exception.Message)"
                $stats.flattenFailed++
                $stats.failed++
            }
        }
    }
}

# --- Step 3: Dedupe + clean ---
if (-not $SkipDedupe) {
    Write-Step "3/3 Dedupe and clean"

    # Pull any remaining stray media from subfolders (non-prefixed path).
    foreach ($dir in @(Get-ChildItem -LiteralPath $RootPath -Directory)) {
        if (Test-SkipDir $dir.Name) { continue }

        foreach ($file in @(Get-ChildItem -LiteralPath $dir.FullName -Recurse -File -EA SilentlyContinue)) {
            if ($MediaExtensions -notcontains $file.Extension.ToLowerInvariant()) { continue }

            $dest = Get-UniquePath -Directory $RootPath -FileName $file.Name
            if ($WhatIf) {
                $stats.flattened++
                continue
            }
            Move-Item -LiteralPath $file.FullName -Destination $dest
            $stats.flattened++
        }
    }

    $mediaFiles = @(
        Get-ChildItem -LiteralPath $RootPath -File |
            Where-Object { $MediaExtensions -contains $_.Extension.ToLowerInvariant() }
    )

    Write-Host "Hashing $($mediaFiles.Count) media file(s)..."

    $byHash = @{}
    $hashed = 0
    foreach ($file in $mediaFiles) {
        $hashed++
        if ($hashed % 500 -eq 0) {
            Write-Host "  hashed $hashed / $($mediaFiles.Count)..."
        }
        $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
        if (-not $byHash.ContainsKey($hash)) {
            $byHash[$hash] = @()
        }
        $byHash[$hash] += $file
    }

    $duplicateGroups = @($byHash.GetEnumerator() | Where-Object { $_.Value.Count -gt 1 })
    Write-Host "Duplicate groups: $($duplicateGroups.Count)"

    foreach ($group in $duplicateGroups) {
        $keeper = Pick-Keeper -Files $group.Value
        foreach ($file in $group.Value) {
            if ($file.FullName -eq $keeper.FullName) { continue }

            if ($WhatIf) {
                Write-Host "[whatif] delete duplicate: $($file.Name)"
                $stats.deduped++
                continue
            }
            try {
                Remove-Item -LiteralPath $file.FullName -Force
                $stats.deduped++
            }
            catch {
                Write-Warning "[fail] $($file.FullName): $($_.Exception.Message)"
                $stats.failed++
            }
        }
    }

    foreach ($dir in @(Get-ChildItem -LiteralPath $RootPath -Directory)) {
        if (Test-SkipDir $dir.Name) { continue }

        foreach ($file in @(Get-ChildItem -LiteralPath $dir.FullName -Recurse -File -EA SilentlyContinue)) {
            $remove = $false
            if ($file.Name -like '*tbcc-meta*.json') { $remove = $true }
            if ($file.Name -like 'TBCC_README*.txt') { $remove = $true }
            if (-not $remove) { continue }

            if ($WhatIf) {
                $stats.junkRemoved++
                continue
            }
            Remove-Item -LiteralPath $file.FullName -Force
            $stats.junkRemoved++
        }
    }

    $zipArchive = Join-Path $RootPath $ZipArchiveName
    if (-not $WhatIf -and -not (Test-Path -LiteralPath $zipArchive)) {
        New-Item -ItemType Directory -Path $zipArchive -Force | Out-Null
    }

    foreach ($dir in @(Get-ChildItem -LiteralPath $RootPath -Directory)) {
        if (Test-SkipDir $dir.Name) { continue }

        $hasFiles = Get-ChildItem -LiteralPath $dir.FullName -Recurse -File -EA SilentlyContinue
        if ($hasFiles) { continue }

        if ($WhatIf) {
            $stats.emptyDirsRemoved++
            continue
        }
        Remove-Item -LiteralPath $dir.FullName -Recurse -Force
        $stats.emptyDirsRemoved++
    }

    foreach ($zip in @(Get-ChildItem -LiteralPath $RootPath -Filter "*.zip" -File)) {
        $dest = Join-Path $zipArchive $zip.Name
        if ($WhatIf) {
            $stats.zipsArchived++
            continue
        }
        Move-Item -LiteralPath $zip.FullName -Destination $dest -Force
        $stats.zipsArchived++
    }
}

$remaining = @(
    Get-ChildItem -LiteralPath $RootPath -File |
        Where-Object { $MediaExtensions -contains $_.Extension.ToLowerInvariant() }
).Count

Write-Host ""
Write-Host "=== Summary ==="
Write-Host "  extracted:           $($stats.extracted)"
Write-Host "  extract skipped:     $($stats.extractSkipped)"
Write-Host "  extract failed:      $($stats.extractFailed)"
Write-Host "  flattened:           $($stats.flattened)"
Write-Host "  flatten failed:      $($stats.flattenFailed)"
Write-Host "  deduped removed:     $($stats.deduped)"
Write-Host "  junk removed:        $($stats.junkRemoved)"
Write-Host "  empty dirs removed:  $($stats.emptyDirsRemoved)"
Write-Host "  zips archived:       $($stats.zipsArchived)"
Write-Host "  media in root:       $remaining"
Write-Host "  failed:              $($stats.failed)"

if ($stats.failed -gt 0) { exit 1 }
