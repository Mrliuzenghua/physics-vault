Option Explicit

' The desktop shortcut targets this script so the launch process never opens
' a Command Prompt or Windows Terminal window.
Dim shell, fileSystem, scriptPath, command
Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

scriptPath = fileSystem.BuildPath(fileSystem.GetParentFolderName(WScript.ScriptFullName), "start-physics-vault.ps1")
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & scriptPath & """ -Silent"
shell.Run command, 0, False
