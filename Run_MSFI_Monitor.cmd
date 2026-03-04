@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run_MSFI_Monitor.ps1" -LanAccess
endlocal
