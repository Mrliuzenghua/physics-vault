@echo off
setlocal
set "PV_SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$base=$env:PV_SCRIPT_DIR; $name=([string][char]0x542F)+([char]0x52A8)+([char]0x9898)+([char]0x5E93)+'.ps1'; . (Join-Path $base $name)"
exit /b %errorlevel%
