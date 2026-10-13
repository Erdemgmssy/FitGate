@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0FitGate-Launcher.ps1" -Mode Start
if errorlevel 1 (
    echo.
    echo FitGate baslatilamadi. Yukaridaki hata mesajini kontrol edin.
    pause
    exit /b 1
)
exit /b 0
