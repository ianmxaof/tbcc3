# Remove TBCC menu accidentally registered under Microsoft.PowerShell (first-run $ShellId bug).
$paths = @(
  "HKCU:\Software\Classes\Directory\Background\shell\Microsoft.PowerShell",
  "HKCU:\Software\Classes\Directory\shell\Microsoft.PowerShell",
  "HKCU:\Software\Classes\DesktopBackground\shell\Microsoft.PowerShell"
)
foreach ($p in $paths) {
  if (-not (Test-Path -LiteralPath $p)) { continue }
  $title = (Get-ItemProperty -LiteralPath $p -Name "(default)" -ErrorAction SilentlyContinue)."(default)"
  if ($title -like "TBCC:*") {
    Remove-Item -LiteralPath $p -Recurse -Force
    Write-Host "Removed hijacked: $p"
  }
}
