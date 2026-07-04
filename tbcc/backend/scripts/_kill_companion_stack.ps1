$killed = @()
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ForEach-Object {
    $cmd = $_.CommandLine
    if ($null -eq $cmd) { return }
    if ($cmd -match 'companion_bot') {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        $killed += $_.ProcessId
    }
}
Get-Process -Name ngrok -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Output "killed_pids=$($killed -join ',')"
$listen8000 = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
$listen4040 = Get-NetTCPConnection -LocalPort 4040 -State Listen -ErrorAction SilentlyContinue
Write-Output "port_8000=$($listen8000.OwningProcess -join ',')"
Write-Output "port_4040=$($listen4040.OwningProcess -join ',')"
