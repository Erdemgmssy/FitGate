$ErrorActionPreference = 'Stop'
& $env:FITGATE_LAUNCHER_TEST_PYTHON (Join-Path $PSScriptRoot 'fake-service.py') frontend 15174
