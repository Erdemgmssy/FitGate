@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0FitGate-Launcher.ps1" -Mode Stop
if errorlevel 1 (
    echo.
    echo FitGate durdurma islemi tamamlanamadi. Yukaridaki mesaji kontrol edin.
    pause
    exit /b 1
)
exit /b 0
