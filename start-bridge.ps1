$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot 'backend')
if (!(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'backend\.venv-fastapi\Scripts\python.exe'))) {
    throw 'Python sanal ortami bulunamadi. docs/KURULUM.md adimlarini tamamlayin.'
}
if (!(Test-Path -LiteralPath 'hardware\.env')) {
    throw 'Arduino bridge ayarlari yok. Mevcut okuyucuyu register_usb_device.py ile kaydedin; gizli anahtari paylasmayin.'
}
& '.\.venv-fastapi\Scripts\python.exe' -u 'hardware\bridge.py'
exit $LASTEXITCODE
