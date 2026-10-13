$ErrorActionPreference = 'Stop'
if (!(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'backend\.venv-fastapi\Scripts\python.exe'))) {
    throw 'Python sanal ortami bulunamadi. docs/KURULUM.md adimlarini tamamlayin.'
}
. (Join-Path $PSScriptRoot 'FitGate-Launcher.ps1') -Mode Load
Wait-Postgres
Set-Location (Join-Path $PSScriptRoot 'backend')
& .\.venv-fastapi\Scripts\python.exe -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Migration basarisiz; API baslatilmadi.' }
& .\.venv-fastapi\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
