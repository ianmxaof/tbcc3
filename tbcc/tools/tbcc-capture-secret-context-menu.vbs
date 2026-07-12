' Silent launcher for desktop context menu - no cmd/PowerShell flash.
' WindowStyle 0 = hidden. STA PowerShell for clipboard + WinForms picker.
Option Explicit
Dim sh, toolsDir, ps1, cmd, psExe
Set sh = CreateObject("WScript.Shell")
toolsDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
ps1 = toolsDir & "\..\scripts\tbcc-capture-secret.ps1"
psExe = sh.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\WindowsPowerShell\v1.0\powershell.exe"
cmd = """" & psExe & """ -NoProfile -Sta -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1 & """ -FromClipboard -Quiet"
sh.Run cmd, 0, False
