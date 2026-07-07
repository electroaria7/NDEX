@echo off
cd /d "%~dp0"
echo === NDEX release build starting ===
powershell -ExecutionPolicy Bypass -File "%~dp0build_all.ps1"
echo.
echo === Exit code: %ERRORLEVEL% ===
pause
