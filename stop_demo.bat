@echo off
rem Double-click to stop the demo started by start_demo.bat.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop_demo.ps1"
echo.
pause
