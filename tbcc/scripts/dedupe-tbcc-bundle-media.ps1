# Dedupe media by content hash and clean TBCC bundles folder layout.
#
# Usage:
#   .\scripts\dedupe-tbcc-bundle-media.ps1
#   .\scripts\dedupe-tbcc-bundle-media.ps1 -RootPath "C:\path\to\TBCC BUNDLES"
#   .\scripts\dedupe-tbcc-bundle-media.ps1 -WhatIf

param(
    [string]$RootPath = "C:\Users\ianmp\Downloads\Porn\tbcc\AOF NETWORK\TBCC BUNDLES",
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

$MediaExtensions = @(
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif",
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".flv", ".mpeg", ".mpg", ".3gp"
)

$SkipDirNames = @('_zips')

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

function Get-UniqueRootPath {
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

if (-not (Test-Path -LiteralPath $RootPath)) {
    Write-Error "Root path not found: $RootPath"
}

# Pull stray media from subfolders into root first.
$movedIn = 0
foreach ($dir in @(Get-ChildItem -LiteralPath $RootPath -Directory)) {
    if ($SkipDirNames -contains $dir.Name) { continue }

    foreach ($file in @(Get-ChildItem -LiteralPath $dir.FullName -Recurse -File -EA SilentlyContinue)) {
        if ($MediaExtensions -notcontains $file.Extension.ToLowerInvariant()) { continue }

        $dest = Get-UniqueRootPath -Directory $RootPath -FileName $file.Name
        if ($WhatIf) {
            Write-Host "[whatif] move to root: $($file.FullName)"
        }
        else {
            Move-Item -LiteralPath $file.FullName -Destination $dest
        }
        $movedIn++
    }
}

$mediaFiles = @(
    Get-ChildItem -LiteralPath $RootPath -File |
        Where-Object { $MediaExtensions -contains $_.Extension.ToLowerInvariant() }
)

Write-Host "Hashing $($mediaFiles.Count) media file(s) in root..."
Write-Host "  $RootPath"
Write-Host ""

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
$toDelete = @()
foreach ($group in $duplicateGroups) {
    $keeper = Pick-Keeper -Files $group.Value
    foreach ($file in $group.Value) {
        if ($file.FullName -ne $keeper.FullName) {
            $toDelete += $file
        }
    }
}

Write-Host "Duplicate groups: $($duplicateGroups.Count)"
Write-Host "Files to remove:  $($toDelete.Count)"
Write-Host ""

$removed = 0
$failed = 0
foreach ($file in $toDelete) {
    if ($WhatIf) {
        Write-Host "[whatif] delete duplicate: $($file.Name)"
        $removed++
        continue
    }
    try {
        Remove-Item -LiteralPath $file.FullName -Force
        $removed++
    }
    catch {
        Write-Warning "[fail] $($file.FullName): $($_.Exception.Message)"
        $failed++
    }
}

# Remove TBCC sidecar/meta clutter and duplicate readme files outside _zips.
$junkRemoved = 0
foreach ($dir in @(Get-ChildItem -LiteralPath $RootPath -Directory)) {
    if ($SkipDirNames -contains $dir.Name) { continue }

    foreach ($file in @(Get-ChildItem -LiteralPath $dir.FullName -Recurse -File -EA SilentlyContinue)) {
        $remove = $false
        if ($file.Name -like '*tbcc-meta*.json') { $remove = $true }
        if ($file.Name -like 'TBCC_README*.txt') { $remove = $true }

        if (-not $remove) { continue }

        if ($WhatIf) {
            Write-Host "[whatif] delete junk: $($file.FullName)"
        }
        else {
            Remove-Item -LiteralPath $file.FullName -Force
        }
        $junkRemoved++
    }
}

$zipArchive = Join-Path $RootPath "_zips"
if (-not $WhatIf) {
    if (-not (Test-Path -LiteralPath $zipArchive)) {
        New-Item -ItemType Directory -Path $zipArchive -Force | Out-Null
    }
}

$removedDirs = 0
foreach ($dir in @(Get-ChildItem -LiteralPath $RootPath -Directory)) {
    if ($SkipDirNames -contains $dir.Name) { continue }

    $hasFiles = Get-ChildItem -LiteralPath $dir.FullName -Recurse -File -EA SilentlyContinue
    if ($hasFiles) { continue }

    if ($WhatIf) {
        Write-Host "[whatif] remove empty folder: $($dir.Name)"
    }
    else {
        Remove-Item -LiteralPath $dir.FullName -Recurse -Force
    }
    $removedDirs++
}

$movedZips = 0
foreach ($zip in @(Get-ChildItem -LiteralPath $RootPath -Filter "*.zip" -File)) {
    $dest = Join-Path $zipArchive $zip.Name
    if ($WhatIf) {
        Write-Host "[whatif] move zip -> _zips\$($zip.Name)"
    }
    else {
        Move-Item -LiteralPath $zip.FullName -Destination $dest -Force
    }
    $movedZips++
}

$remaining = @(
    Get-ChildItem -LiteralPath $RootPath -File |
        Where-Object { $MediaExtensions -contains $_.Extension.ToLowerInvariant() }
).Count

Write-Host ""
Write-Host "Done."
Write-Host "  moved into root: $movedIn"
Write-Host "  deduped removed: $removed"
Write-Host "  junk removed: $junkRemoved"
Write-Host "  empty folders removed: $removedDirs"
Write-Host "  zips archived: $movedZips"
Write-Host "  media remaining in root: $remaining"
Write-Host "  failed: $failed"
if ($failed -gt 0) { exit 1 }
