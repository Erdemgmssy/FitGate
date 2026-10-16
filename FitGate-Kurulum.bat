@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0FitGate-Kurulum.ps1"
if errorlevel 1 (
    echo Kurulum tamamlanamadi. Mevcut dosyalari ve volume verilerini koruyun.
    pause
    exit /b 1
)
exit /b 0
