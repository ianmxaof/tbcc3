# Sync dashboard + aof-forum sources to the VPS for compose profile `ui` builds.
#
#   .\scripts\revenue-island\sync-island-ui.ps1 -HostName root@203.0.113.10

param(
  [Parameter(Mandatory = $true)][string]$HostName,
  [string]$TbccRemote = "/opt/tbcc",
  [string]$ForumRemote = "/opt/aof-forum"
)

$ErrorActionPreference = "Stop"
$tbccRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$forumRoot = (Resolve-Path (Join-Path $tbccRoot "..\aof-forum")).Path
$dashRoot = Join-Path $tbccRoot "dashboard"

function Sync-TreeTar {
  param([string]$LocalDir, [string]$RemoteDir, [string[]]$Exclude)
  $tar = Get-Command tar -ErrorAction SilentlyContinue
  if (-not $tar) { throw "tar.exe required (Windows 10+ / Git)." }
  $excludeArgs = @()
  foreach ($e in $Exclude) { $excludeArgs += @("--exclude=$e") }
  Push-Location $LocalDir
  try {
    $remoteCmd = "mkdir -p $RemoteDir && tar -xf - -C $RemoteDir"
    & tar @excludeArgs -cf - . | & ssh $HostName $remoteCmd
    if ($LASTEXITCODE -ne 0) { throw "tar|ssh failed for $LocalDir" }
  } finally {
    Pop-Location
  }
}

Write-Host "mkdir remotes on $HostName ..." -ForegroundColor DarkCyan
& ssh $HostName "mkdir -p $TbccRemote/dashboard $TbccRemote/infra $TbccRemote/scripts/revenue-island $TbccRemote/docs $ForumRemote"

Write-Host "scp compose + ui script + docs ..." -ForegroundColor DarkGray
& scp (Join-Path $tbccRoot "infra\docker-compose.revenue-island.yml") "${HostName}:$TbccRemote/infra/"
& scp (Join-Path $tbccRoot "infra\env.revenue-island.example") "${HostName}:$TbccRemote/infra/"
& scp (Join-Path $PSScriptRoot "up-island-ui.sh") "${HostName}:$TbccRemote/scripts/revenue-island/"
& scp (Join-Path $tbccRoot "docs\ISLAND_UI_SURFACES.md") "${HostName}:$TbccRemote/docs/"

Write-Host "sync dashboard → $TbccRemote/dashboard ..." -ForegroundColor DarkGray
Sync-TreeTar -LocalDir $dashRoot -RemoteDir "$TbccRemote/dashboard" -Exclude @("node_modules", "dist", ".git")

Write-Host "sync aof-forum → $ForumRemote ..." -ForegroundColor DarkGray
Sync-TreeTar -LocalDir $forumRoot -RemoteDir $ForumRemote -Exclude @("node_modules", ".next", ".git", ".tmp")

& ssh $HostName @"
chmod +x $TbccRemote/scripts/revenue-island/up-island-ui.sh
sed -i 's/\r`$//' $TbccRemote/scripts/revenue-island/up-island-ui.sh 2>/dev/null || true
grep -q '^AOF_FORUM_BUILD_CONTEXT=' $TbccRemote/infra/.env.revenue-island 2>/dev/null \
  || echo 'AOF_FORUM_BUILD_CONTEXT=$ForumRemote' >> $TbccRemote/infra/.env.revenue-island
"@

Write-Host "Synced. On VPS:" -ForegroundColor Green
Write-Host "  nano $TbccRemote/infra/.env.revenue-island   # Supabase + bridge + public URLs" -ForegroundColor DarkGray
Write-Host "  bash $TbccRemote/scripts/revenue-island/up-island-ui.sh" -ForegroundColor DarkGray
Write-Host "  # route dash.* + forum.* via cloudflared - docs/ISLAND_UI_SURFACES.md" -ForegroundColor DarkGray
