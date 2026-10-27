@echo off
rem Double-click to start the demo (API + UI + warm-up question). Stop with stop_demo.bat.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_demo.ps1" -Warmup
echo.
pause
