$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
function Run-Step([scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw 'Adim basarisiz; mevcut dosyalar silinmedi. Hata nedenini kontrol edin.' }
}
try {
    foreach ($name in @('DATABASE_URL', 'SECRET_KEY', 'ENVIRONMENT', 'DEMO_MODE')) {
        if (Test-Path "Env:$name") { throw "Ortam degiskeni $name kurulum ayarlarini gecersiz kilabilir. Temiz terminalde tekrar deneyin." }
    }
    foreach ($tool in @('python.exe', 'node.exe', 'npm.cmd', 'git.exe', 'docker.exe')) {
        if (!(Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Gereksinim eksik: $tool" }
    }
    Run-Step { python.exe -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" }
    Run-Step { node.exe -e "const [a,b]=process.versions.node.split('.').map(Number); process.exit((a===20&&b>=19)||(a===22&&b>=12)||a>22?0:1)" }
    # Existing installations are intentionally not migrated or seeded by this installer.
    if ((Test-Path backend/.env.fastapi) -or (Test-Path backend/backups/postgres-docker.env)) {
        throw 'Mevcut yapilandirma bulundu. Kurulum durdu; FitGate-Baslat.bat kullanin. Eksik kurulum icin docs/KURULUM.md belgesine bakin.'
    }
    Run-Step { python.exe -c "from backend.tools.local_postgres import preflight, ROOT; preflight(ROOT)" }
    $choice = Read-Host 'Kurulum: 1 = bos, 2 = demo (yeni fitgate_demo veritabani)'
    if ($choice -notin @('1','2')) { throw 'Gecersiz secim; hicbir kurulum yapilmadi.' }
    if (!(Test-Path backend/.venv-fastapi/Scripts/python.exe)) {
        Run-Step { python.exe -m venv backend/.venv-fastapi }
    }
    $python = Join-Path $PSScriptRoot 'backend/.venv-fastapi/Scripts/python.exe'
    Run-Step { & $python -m pip install -r backend/requirements-fastapi.lock.txt }
    Push-Location frontend
    try { Run-Step { npm.cmd ci } } finally { Pop-Location }
    Push-Location backend
    try {
        if ($choice -eq '2') { Run-Step { & $python tools/local_postgres.py --demo } }
        else { Run-Step { & $python tools/local_postgres.py } }
        Run-Step { & $python -m alembic upgrade head }
        if ($choice -eq '2') { Run-Step { & $python tools/install_demo.py --local-demo-accounts } }
        else { Run-Step { & $python tools/create_admin.py } }
    } finally { Pop-Location }
    Write-Host 'Kurulum tamamlandi. FitGate-Baslat.bat ile baslatin.'
} catch { Write-Host "HATA: $($_.Exception.Message)" -ForegroundColor Red; exit 1 }
