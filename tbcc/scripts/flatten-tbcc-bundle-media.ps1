# Move (or copy) image/video files from bundle subfolders into the bundles root.
#
# Usage:
#   .\scripts\flatten-tbcc-bundle-media.ps1
#   .\scripts\flatten-tbcc-bundle-media.ps1 -RootPath "C:\path\to\TBCC BUNDLES"
#   .\scripts\flatten-tbcc-bundle-media.ps1 -Copy          # copy instead of move
#   .\scripts\flatten-tbcc-bundle-media.ps1 -WhatIf         # dry run

param(
    [string]$RootPath = "C:\Users\ianmp\Downloads\Porn\tbcc\AOF NETWORK\TBCC BUNDLES",
    [switch]$Copy,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

$MediaExtensions = @(
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif",
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".flv", ".mpeg", ".mpg", ".3gp"
)

function Get-UniqueRootPath {
    param(
        [string]$Directory,
        [string]$FileName
    )

    $candidate = Join-Path $Directory $FileName
    if (-not (Test-Path -LiteralPath $candidate)) {
        return $candidate
    }

    $base = [System.IO.Path]::GetFileNameWithoutExtension($FileName)
    $ext = [System.IO.Path]::GetExtension($FileName)
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
    if ([string]::IsNullOrWhiteSpace($safeFolder)) {
        $safeFolder = "bundle"
    }

    $prefixed = "{0}__{1}" -f $safeFolder, $FileName
    return Get-UniqueRootPath -Directory $Directory -FileName $prefixed
}

if (-not (Test-Path -LiteralPath $RootPath)) {
    Write-Error "Root path not found: $RootPath"
}

$subdirs = @(
    Get-ChildItem -LiteralPath $RootPath -Directory |
        Where-Object { $_.Name -ne "inbox" }
)

if ($subdirs.Count -eq 0) {
    Write-Host "No subfolders to scan in: $RootPath"
    exit 0
}

Write-Host "Scanning $($subdirs.Count) folder(s) under:"
Write-Host "  $RootPath"
Write-Host "Mode: $(if ($Copy) { 'copy' } else { 'move' })"
Write-Host ""

$moved = 0
$skipped = 0
$failed = 0

foreach ($dir in $subdirs) {
    $mediaFiles = @(
        Get-ChildItem -LiteralPath $dir.FullName -Recurse -File |
            Where-Object { $MediaExtensions -contains $_.Extension.ToLowerInvariant() }
    )

    if ($mediaFiles.Count -eq 0) {
        continue
    }

    Write-Host "[$($dir.Name)] $($mediaFiles.Count) media file(s)"

    foreach ($file in $mediaFiles) {
        $destPath = Get-UniqueRootPath -Directory $RootPath -FileName $file.Name
        if ($destPath -ne (Join-Path $RootPath $file.Name)) {
            # Name collision at root — prefix with source folder name.
            $destPath = Get-PrefixedRootPath -Directory $RootPath -FolderName $dir.Name -FileName $file.Name
        }

        if ($WhatIf) {
            Write-Host "  [whatif] $($file.FullName)"
            Write-Host "        -> $destPath"
            $moved++
            continue
        }

        try {
            if ($Copy) {
                Copy-Item -LiteralPath $file.FullName -Destination $destPath -Force
            }
            else {
                Move-Item -LiteralPath $file.FullName -Destination $destPath
            }
            $moved++
        }
        catch {
            Write-Warning "  [fail] $($file.FullName): $($_.Exception.Message)"
            $failed++
        }
    }
}

Write-Host ""
Write-Host "Done. $(if ($Copy) { 'copied' } else { 'moved' })=$moved skipped=$skipped failed=$failed"
if ($failed -gt 0) { exit 1 }
