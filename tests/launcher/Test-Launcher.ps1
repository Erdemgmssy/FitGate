$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$exe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$env:FITGATE_LAUNCHER_TEST_PYTHON = Join-Path $root 'backend\.venv-fastapi\Scripts\python.exe'
$fixture = Join-Path $root ('work\fitgate-launcher-tests\FitGate QA space ' + [guid]::NewGuid())
[void][IO.Directory]::CreateDirectory($fixture)
Copy-Item -LiteralPath (Join-Path $root 'FitGate-Launcher.ps1') -Destination $fixture
Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'fixtures') -File | Copy-Item -Destination $fixture
$helper = Join-Path $fixture 'FitGate-Launcher.ps1'
# Replace Docker access in the fixture copy before any launcher process starts.
$source = [IO.File]::ReadAllText($helper)
$dockerStart = $source.IndexOf('function Invoke-Docker(')
$dockerEnd = $source.IndexOf('function Wait-Postgres')
if ($dockerStart -lt 0 -or $dockerEnd -le $dockerStart) { throw 'Cannot isolate Docker access; no launcher test was started.' }
$stub = [IO.File]::ReadAllText((Join-Path $fixture 'docker-stub.ps1'))
[IO.File]::WriteAllText($helper, $source.Substring(0, $dockerStart) + $stub + "`r`n" + $source.Substring($dockerEnd))
$sentinel = Start-Process -FilePath $env:FITGATE_LAUNCHER_TEST_PYTHON -ArgumentList '-c "import time; time.sleep(300)"' -WindowStyle Hidden -PassThru
$unrelated = $null; $unrelatedChildren = @()

function Assert-True($Value, $Message) { if (!$Value) { throw "TEST FAILED: $Message" } }
function Start-Fixture {
    & $exe -NoProfile -ExecutionPolicy Bypass -File $helper -Mode Start -NoBrowser -BackendPort 18001 -FrontendPort 15174 -ReadyTimeoutSeconds 8
    Assert-True ($LASTEXITCODE -eq 0) 'Both owned services should become ready'
}
function Stop-Fixture {
    & $exe -NoProfile -ExecutionPolicy Bypass -File $helper -Mode Stop
    Assert-True ($LASTEXITCODE -eq 0) 'Stop should succeed'
}
function Fixture-Pids {
    $backend = Invoke-RestMethod http://127.0.0.1:18001/test/fixture
    $frontend = Invoke-RestMethod http://127.0.0.1:15174/test/fixture
    return @($backend.pid, $backend.child, $frontend.pid, $frontend.child)
}

try {
    $listeners = [Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    Assert-True (@($listeners | Where-Object { $_.Port -in 18001,15174 }).Count -eq 0) 'Test ports must be free; existing applications must not be touched'
    & $exe -NoProfile -ExecutionPolicy Bypass -Command "& { . '$helper' -Mode Load -BackendPort 18001 -FrontendPort 15174 -ReadyTimeoutSeconds 8; [void](Start-ServiceSupervisor 'backend'); [void](Start-ServiceSupervisor 'frontend'); if (@(`$NewServices).Count -ne 2) { throw 'Both supervisors must remain in an array' } }"
    Assert-True ($LASTEXITCODE -eq 0) 'Load mode must track two sequential service starts'
    Start-Fixture
    $first = Fixture-Pids
    Start-Fixture
    Assert-True (($first -join ',') -eq ((Fixture-Pids) -join ',')) 'Repeated start must preserve process identities'

    $statePath = Join-Path $fixture 'work\fitgate-launcher\backend.json'
    $original = [IO.File]::ReadAllText($statePath)
    $stale = $original | ConvertFrom-Json
    $stale.SupervisorStartedUtc = '2000-01-01T00:00:00Z'
    [IO.File]::WriteAllText($statePath, ($stale | ConvertTo-Json))
    Stop-Fixture
    Assert-True ($null -ne (Get-Process -Id $first[0] -ErrorAction SilentlyContinue)) 'A stale/reused PID must not be stopped'
    [IO.File]::WriteAllText($statePath, $original)
    Stop-Fixture
    Start-Sleep -Milliseconds 300
    foreach ($processId in $first) { Assert-True ($null -eq (Get-Process -Id $processId -ErrorAction SilentlyContinue)) 'All owned descendants must stop' }
    Assert-True (!$sentinel.HasExited) 'Unrelated Python process must remain running'
    Stop-Fixture

    # The optional USB bridge stays owned even when hardware is disconnected.
    $hardwareDir = Join-Path $fixture 'backend\hardware'
    [void][IO.Directory]::CreateDirectory($hardwareDir)
    Copy-Item -LiteralPath (Join-Path $fixture 'bridge-enabled.env') -Destination (Join-Path $hardwareDir '.env')
    Start-Fixture
    $bridgeStatePath = Join-Path $fixture 'work\fitgate-launcher\bridge.json'
    $bridgeState = Get-Content -LiteralPath $bridgeStatePath -Raw | ConvertFrom-Json
    $bridgeInfo = Invoke-RestMethod http://127.0.0.1:18106/test/fixture
    Start-Fixture
    Assert-True ((Get-Content -LiteralPath $bridgeStatePath -Raw | ConvertFrom-Json).Token -eq $bridgeState.Token) 'Repeated start must reuse the owned bridge'
    Stop-Fixture
    foreach ($processId in @($bridgeInfo.pid,$bridgeInfo.child)) { Assert-True ($null -eq (Get-Process -Id $processId -ErrorAction SilentlyContinue)) 'Owned bridge descendants must stop' }
    Assert-True (!$sentinel.HasExited) 'Bridge stop must preserve unrelated Python'
    [IO.File]::WriteAllText((Join-Path $fixture 'start-bridge.ps1'), "throw 'Expected optional bridge failure'")
    Start-Fixture
    Assert-True ((Invoke-RestMethod http://127.0.0.1:18001/api/v1/health/).status -eq 'ready') 'Bridge failure must not stop API'
    Stop-Fixture
    Move-Item -LiteralPath (Join-Path $hardwareDir '.env') -Destination (Join-Path $hardwareDir 'disabled.env')

    # A later service failure must roll back only newly owned jobs.
    [IO.File]::WriteAllText((Join-Path $fixture 'start-frontend.ps1'), "throw 'Expected fixture failure'")
    & $exe -NoProfile -ExecutionPolicy Bypass -File $helper -Mode Start -NoBrowser -BackendPort 18001 -FrontendPort 15174 -ReadyTimeoutSeconds 8
    Assert-True ($LASTEXITCODE -eq 1) 'Startup failure should return a nonzero exit code'
    $listeners = [Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    Assert-True (@($listeners | Where-Object { $_.Port -in 18001,15174 }).Count -eq 0) 'Failed startup should clean newly started services'
    Assert-True (!$sentinel.HasExited) 'Failure rollback must preserve unrelated processes'
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'fixtures\start-frontend.ps1') -Destination $fixture -Force

    $env:FITGATE_LAUNCHER_TEST_DELAY = '2'
    $args = "-NoProfile -ExecutionPolicy Bypass -File `"$helper`" -Mode Start -NoBrowser -BackendPort 18001 -FrontendPort 15174 -ReadyTimeoutSeconds 12"
    $parallel = Start-Process -FilePath $exe -ArgumentList $args -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $fixture 'parallel.log')
    [void]$parallel.Handle
    $deadline = [datetime]::UtcNow.AddSeconds(20)
    while (!(Test-Path -LiteralPath $statePath) -and !$parallel.HasExited -and [datetime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 100 }
    Assert-True (Test-Path -LiteralPath $statePath) 'The first concurrent start should own the startup lock'
    & $exe -NoProfile -ExecutionPolicy Bypass -File $helper -Mode Start -NoBrowser -BackendPort 18001 -FrontendPort 15174 -ReadyTimeoutSeconds 8
    Assert-True ($LASTEXITCODE -eq 1) 'Concurrent start must not create a second owner'
    Assert-True ($parallel.WaitForExit(30000)) 'The original concurrent start should complete'
    Assert-True ((Get-Content -LiteralPath (Join-Path $fixture 'parallel.log') -Raw) -match 'FitGate hazir:') 'The original concurrent start should succeed'
    Stop-Fixture
    Remove-Item Env:FITGATE_LAUNCHER_TEST_DELAY

    $pythonArgs = "`"$(Join-Path $fixture 'fake-service.py')`" unrelated 18001"
    $unrelated = Start-Process -FilePath $env:FITGATE_LAUNCHER_TEST_PYTHON -ArgumentList $pythonArgs -WindowStyle Hidden -PassThru
    $deadline = [datetime]::UtcNow.AddSeconds(10)
    do {
        try { $unrelatedInfo = Invoke-RestMethod http://127.0.0.1:18001/test/fixture -TimeoutSec 1; break } catch { Start-Sleep -Milliseconds 100 }
    } while ([datetime]::UtcNow -lt $deadline)
    Assert-True ($null -ne $unrelatedInfo) 'Unrelated test server should be ready'
    $unrelatedChildren = @($unrelatedInfo.pid,$unrelatedInfo.child) | ForEach-Object { Get-Process -Id $_ }
    & $exe -NoProfile -ExecutionPolicy Bypass -File $helper -Mode Start -NoBrowser -BackendPort 18001 -FrontendPort 15174 -ReadyTimeoutSeconds 5
    Assert-True ($LASTEXITCODE -eq 1) 'An occupied non-FitGate port should fail clearly'
    Assert-True (!$unrelated.HasExited) 'A conflicting unowned service must never be stopped'
    Write-Host 'PASS: Windows PowerShell 5.1; spaced paths; native stderr; readiness; repeated/concurrent start; optional bridge reuse/stop/failure; PID-age protection; owned descendants; unrelated processes; repeat stop; failure rollback; occupied foreign port.'
} finally {
    try { Stop-Fixture } catch { Write-Warning $_.Exception.Message }
    if (!$sentinel.HasExited) { $sentinel.Kill(); $sentinel.WaitForExit() }
    foreach ($process in $unrelatedChildren) { if (!$process.HasExited) { $process.Kill(); $process.WaitForExit() } }
    if ($unrelated -and !$unrelated.HasExited) { $unrelated.Kill(); $unrelated.WaitForExit() }
    Remove-Item Env:FITGATE_LAUNCHER_TEST_PYTHON -ErrorAction SilentlyContinue
    Remove-Item Env:FITGATE_LAUNCHER_TEST_DELAY -ErrorAction SilentlyContinue
}
