$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot 'frontend')
if (!(Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Node.js/npm bulunamadi. docs/KURULUM.md gereksinimlerini kontrol edin.' }
if (!(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'frontend\node_modules\.bin\vite.cmd'))) {
    throw 'Frontend bagimliliklari bulunamadi. frontend klasorunde npm ci calistirin.'
}
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
