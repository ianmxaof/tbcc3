# One-time cleanup for stale npm Claude Code staging dirs (.claude-code-*)
Get-Process claude -ErrorAction SilentlyContinue | Stop-Process -Force
$staging = Join-Path $env:APPDATA 'npm\node_modules\@anthropic-ai'
Get-ChildItem $staging -Directory -Filter '.claude-code-*' -ErrorAction SilentlyContinue | ForEach-Object {
  Write-Host "Removing $($_.FullName)"
  Remove-Item -Recurse -Force $_.FullName
}
$bin = Join-Path $env:APPDATA 'npm\node_modules\@anthropic-ai\claude-code\bin'
Write-Host '=== bin contents ==='
Get-ChildItem $bin -Force | Format-Table Name, Length, LastWriteTime -AutoSize
if (-not (Test-Path (Join-Path $bin 'claude.exe'))) {
  $old = Get-ChildItem (Join-Path $bin 'claude.exe.old.*') -ErrorAction SilentlyContinue |
    Sort-Object Length -Descending | Select-Object -First 1
  if ($old) {
    Move-Item $old.FullName (Join-Path $bin 'claude.exe') -Force
    Write-Host 'Recovered claude.exe from .old'
  }
}
Write-Host '=== remaining staging dirs ==='
Get-ChildItem $staging -Directory -Filter '.claude-code-*' -ErrorAction SilentlyContinue | Format-Table Name
if (Get-Command claude -ErrorAction SilentlyContinue) {
  claude --version
}
