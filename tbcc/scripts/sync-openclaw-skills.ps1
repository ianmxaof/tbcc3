$src = Join-Path (Split-Path $PSScriptRoot -Parent) "docs\openclaw-skill"
$dst = Join-Path $env:USERPROFILE ".openclaw\workspace\skills"
foreach ($name in @('tbcc-aof-network', 'tbcc-failure-modes', 'tbcc-growth-signals')) {
  Copy-Item -Recurse -Force (Join-Path $src $name) (Join-Path $dst $name)
  Write-Host "OK $name"
}
$mc = Join-Path $env:USERPROFILE ".openclaw\config\mcporter.json"
$ws = Join-Path $env:USERPROFILE "clawd\config"
New-Item -ItemType Directory -Force -Path $ws | Out-Null
Copy-Item -Force $mc (Join-Path $ws "mcporter.json")
Write-Host "OK mcporter sync"
