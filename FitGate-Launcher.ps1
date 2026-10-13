param(
    [ValidateSet('Start', 'Stop', 'Service', 'Run', 'Load')][string]$Mode = 'Start',
    [ValidateSet('backend', 'frontend', 'bridge')][string]$Service,
    [string]$Token,
    [switch]$NoBrowser,
    [ValidateRange(5, 300)][int]$ReadyTimeoutSeconds = 120,
    [ValidateRange(5, 300)][int]$DockerTimeoutSeconds = 120,
    [ValidateRange(1024, 65535)][int]$BackendPort = 8001,
    [ValidateRange(1024, 65535)][int]$FrontendPort = 5174
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$RuntimeDir = Join-Path $ProjectRoot 'work\fitgate-launcher'
$HelperPath = Join-Path $ProjectRoot 'FitGate-Launcher.ps1'
$PowerShellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$script:NewServices = @()
$hash = [Security.Cryptography.SHA256]::Create()
try { $ProjectKey = ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($ProjectRoot.ToLowerInvariant())))).Replace('-', '').Substring(0, 24) }
finally { $hash.Dispose() }

# Each hidden supervisor owns a Windows job. Only its suspended child and that
# child's descendants enter the job; closing/terminating it cannot hit other apps.
function Initialize-JobApi {
    if ('FitGateJobs' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
public static class FitGateJobs {
    [StructLayout(LayoutKind.Sequential)] struct BASIC {
        public long PerProcessUserTimeLimit, PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass, SchedulingClass;
    }
    [StructLayout(LayoutKind.Sequential)] struct IO {
        public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount;
        public ulong ReadTransferCount, WriteTransferCount, OtherTransferCount;
    }
    [StructLayout(LayoutKind.Sequential)] struct EXTENDED {
        public BASIC BasicLimitInformation;
        public IO IoInfo;
        public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
    }
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct STARTUP {
        public uint cb; public string reserved, desktop, title;
        public uint x, y, xSize, ySize, xCountChars, yCountChars, fillAttribute, flags;
        public ushort showWindow, reserved2Size; public IntPtr reserved2, input, output, error;
    }
    [StructLayout(LayoutKind.Sequential)] struct PROCESS {
        public IntPtr process, thread; public uint processId, threadId;
    }
    [StructLayout(LayoutKind.Sequential)] struct SECURITY {
        public uint length; public IntPtr descriptor;
        [MarshalAs(UnmanagedType.Bool)] public bool inherit;
    }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr CreateFile(string path, uint access, uint share, ref SECURITY security, uint disposition, uint flags, IntPtr template);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr CreateJobObject(IntPtr attributes, string name);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job, int type, ref EXTENDED info, uint size);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool CreateProcess(string app, StringBuilder command, IntPtr pa, IntPtr ta, bool inherit, uint flags, IntPtr env, string cwd, ref STARTUP startup, out PROCESS process);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll", SetLastError=true)] static extern uint ResumeThread(IntPtr thread);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool TerminateProcess(IntPtr process, uint code);
    [DllImport("kernel32.dll", SetLastError=true)] static extern uint WaitForSingleObject(IntPtr handle, uint ms);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetExitCodeProcess(IntPtr process, out uint code);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr OpenJobObject(uint access, bool inherit, string name);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool TerminateJobObject(IntPtr job, uint code);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    public sealed class Child : IDisposable {
        IntPtr job, process; public uint Id;
        public Child(string name, string exe, string arguments, string cwd, string log) {
            job=CreateJobObject(IntPtr.Zero,name);
            if(job==IntPtr.Zero) throw new Win32Exception();
            try {
                EXTENDED limit=new EXTENDED(); limit.BasicLimitInformation.LimitFlags=0x2000;
                if(!SetInformationJobObject(job,9,ref limit,(uint)Marshal.SizeOf(typeof(EXTENDED)))) throw new Win32Exception();
                SECURITY security=new SECURITY(); security.length=(uint)Marshal.SizeOf(typeof(SECURITY)); security.inherit=true;
                IntPtr output=CreateFile(log,0x40000000,3,ref security,2,0x80,IntPtr.Zero);
                if(output==new IntPtr(-1)) throw new Win32Exception();
                IntPtr input=CreateFile("NUL",0x80000000,3,ref security,3,0x80,IntPtr.Zero);
                if(input==new IntPtr(-1)) { CloseHandle(output); throw new Win32Exception(); }
                PROCESS child;
                try {
                    STARTUP startup=new STARTUP(); startup.cb=(uint)Marshal.SizeOf(typeof(STARTUP));
                    startup.flags=0x100; startup.input=input; startup.output=output; startup.error=output;
                    if(!CreateProcess(exe,new StringBuilder("\""+exe+"\" "+arguments),IntPtr.Zero,IntPtr.Zero,true,0x08000004,IntPtr.Zero,cwd,ref startup,out child)) throw new Win32Exception();
                } finally { CloseHandle(input); CloseHandle(output); }
                process=child.process; Id=child.processId;
                try {
                    if(!AssignProcessToJobObject(job,process)) { TerminateProcess(process,1); throw new Win32Exception(); }
                    if(ResumeThread(child.thread)==0xffffffff) throw new Win32Exception();
                } finally { CloseHandle(child.thread); }
            } catch { Dispose(); throw; }
        }
        public int Wait() {
            if(WaitForSingleObject(process,0xffffffff)!=0) throw new Win32Exception();
            uint code; if(!GetExitCodeProcess(process,out code)) throw new Win32Exception();
            return unchecked((int)code);
        }
        public void Dispose() {
            if(job!=IntPtr.Zero) { CloseHandle(job); job=IntPtr.Zero; }
            if(process!=IntPtr.Zero) { CloseHandle(process); process=IntPtr.Zero; }
        }
    }
    public static bool Stop(string name) {
        IntPtr job=OpenJobObject(8,false,name);
        if(job==IntPtr.Zero) {
            int error=Marshal.GetLastWin32Error();
            if(error==2) return false;
            throw new Win32Exception(error);
        }
        try { if(!TerminateJobObject(job,0)) throw new Win32Exception(); return true; }
        finally { CloseHandle(job); }
    }
}
'@
}

function Get-StatePath([string]$Name) { Join-Path $RuntimeDir "$Name.json" }
function Read-ServiceState([string]$Name) {
    $path = Get-StatePath $Name
    if (!(Test-Path -LiteralPath $path)) { return $null }
    try { return Get-Content -LiteralPath $path -Raw | ConvertFrom-Json }
    catch { Write-Warning "$Name takip kaydi okunamadi; guvenlik nedeniyle bu kayittan surec durdurulmayacak."; return $null }
}

function Test-OwnedState($State, [string]$Name) {
    if (!$State -or $State.ProjectRoot -ne $ProjectRoot -or $State.Service -ne $Name) { return $false }
    $guid = [guid]::Empty
    if (![guid]::TryParse([string]$State.Token, [ref]$guid)) { return $false }
    if ($State.JobName -ne "Local\FitGate-$ProjectKey-$Name-$guid") { return $false }
    try {
        $process = Get-Process -Id ([int]$State.SupervisorPid) -ErrorAction Stop
        if ($process.StartTime.ToUniversalTime().Ticks -ne [datetime]::Parse($State.SupervisorStartedUtc).ToUniversalTime().Ticks) { return $false }
        $record = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.Id)"
        return $record.CommandLine -and $record.CommandLine.IndexOf($HelperPath, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
            $record.CommandLine -match '(?i)\s-Mode\s+Service\s' -and $record.CommandLine.Contains([string]$guid)
    } catch { return $false }
}

function Stop-OwnedService([string]$Name, [string]$ExpectedToken = '') {
    $state = Read-ServiceState $Name
    if (!$state) { Write-Host "${Name}: Bu baslaticiya ait takip edilen servis yok."; return }
    if ($ExpectedToken -and $state.Token -ne $ExpectedToken) { return }
    if (!(Test-OwnedState $state $Name)) {
        Write-Host "${Name}: Aktif surec sahipligi dogrulanamadi; hicbir surece dokunulmadi."
        return
    }
    Initialize-JobApi
    [void][FitGateJobs]::Stop($state.JobName)
    $deadline = [datetime]::UtcNow.AddSeconds(10)
    while ((Test-OwnedState $state $Name) -and [datetime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 150 }
    if (Test-OwnedState $state $Name) { throw "$Name servis sorumlusu henuz kapanmadi. Durdur dosyasini tekrar calistirin." }
    Write-Host "${Name}: Yalnizca FitGate baslaticisinin actigi surecler durduruldu."
}

function Invoke-Docker([string]$Arguments, [int]$TimeoutMilliseconds = 5000) {
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $DockerExe; $info.Arguments = $Arguments
    $info.UseShellExecute = $false; $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    try {
        [void]$process.Start()
        $output = $process.StandardOutput.ReadToEndAsync(); $errorOutput = $process.StandardError.ReadToEndAsync()
        if (!$process.WaitForExit($TimeoutMilliseconds)) { $process.Kill(); $process.WaitForExit(); return @{ Code = -1; Text = '' } }
        return @{ Code = $process.ExitCode; Text = $output.Result.Trim() }
    } finally { $process.Dispose() }
}

function Wait-Postgres {
    $command = Get-Command docker.exe -ErrorAction SilentlyContinue
    if (!$command) { throw 'Docker Desktop bulunamadi. Docker Desktop kurulumunu kontrol edin.' }
    $script:DockerExe = $command.Source
    if ($env:DOCKER_HOST -and $env:DOCKER_HOST -notmatch '^npipe://') { throw 'Docker baglantisi yerel Docker Desktop olmali. Uzak Docker sunucusuna dokunulmadi.' }
    $context = Invoke-Docker 'context inspect --format {{.Endpoints.docker.Host}}'
    if ($context.Code -ne 0 -or $context.Text -notmatch '^npipe://') { throw 'Yerel Docker Desktop baglantisi bulunamadi. Docker context ayarini kontrol edin.' }
    $ready = Invoke-Docker 'version --format {{.Server.Version}}'
    if ($ready.Code -ne 0) {
        $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
        if (!(Test-Path -LiteralPath $desktop)) { throw 'Docker Desktop baslatilamadi. Uygulamayi elle acip tekrar deneyin.' }
        Write-Host 'Docker Desktop baslatiliyor; motorun hazir olmasi bekleniyor...'
        Start-Process -FilePath $desktop -WindowStyle Hidden
        $deadline = [datetime]::UtcNow.AddSeconds($DockerTimeoutSeconds)
        do {
            Start-Sleep -Seconds 2
            $ready = Invoke-Docker 'version --format {{.Server.Version}}'
        } while ($ready.Code -ne 0 -and [datetime]::UtcNow -lt $deadline)
        if ($ready.Code -ne 0) { throw 'Docker motoru hazir olmadi. Docker Desktop hata/WSL ekranini kontrol edip tekrar deneyin.' }
    }
    Write-Host 'Docker hazir.'
    $container = Invoke-Docker 'inspect --format {{.State.Running}} fitgate-postgres'
    if ($container.Code -ne 0) { throw 'fitgate-postgres konteyneri bulunamadi. Mevcut PostgreSQL kurulumunu kontrol edin; yeni/verisiz konteyner olusturulmadi.' }
    if ($container.Text -ne 'true') {
        Write-Host 'PostgreSQL konteyneri baslatiliyor...'
        $start = Invoke-Docker 'start fitgate-postgres' 15000
        if ($start.Code -ne 0) { throw 'PostgreSQL konteyneri baslatilamadi. Docker Desktop konteyner durumunu kontrol edin.' }
    }
    $deadline = [datetime]::UtcNow.AddSeconds($ReadyTimeoutSeconds)
    do {
        $result = Invoke-Docker 'exec fitgate-postgres pg_isready -q'
        if ($result.Code -eq 0) { Write-Host 'PostgreSQL hazir.'; return }
        Start-Sleep -Seconds 1
    } while ([datetime]::UtcNow -lt $deadline)
    throw 'PostgreSQL zamaninda hazir olmadi. Konteyner gunluklerini kontrol edin; veriler silinmedi.'
}

function Test-ServiceReady([string]$Name) {
    try {
        if ($Name -eq 'bridge') { return (Test-OwnedState (Read-ServiceState 'bridge') 'bridge') }
        if ($Name -eq 'backend') {
            $health = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$BackendPort/api/v1/health/" -TimeoutSec 2
            $body = $health.Content | ConvertFrom-Json
            if ($body.status -ne 'ready' -or $body.database -ne 'postgresql') { return $false }
            $schema = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$BackendPort/openapi.json" -TimeoutSec 2
            return ($schema.Content | ConvertFrom-Json).info.title -eq 'FitGate API'
        }
        $html = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$FrontendPort/" -TimeoutSec 2
        return $html.StatusCode -eq 200 -and $html.Content -match '<title>Spor Salonu Gecis Kontrol</title>' -and $html.Content -match '/src/main.jsx'
    } catch { return $false }
}

function Test-PortOccupied([int]$Port) {
    return @([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object { $_.Port -eq $Port }).Count -gt 0
}

function Wait-Service([string]$Name, $State = $null) {
    $deadline = [datetime]::UtcNow.AddSeconds($ReadyTimeoutSeconds)
    do {
        if (Test-ServiceReady $Name) { return }
        if ($State -and !(Test-OwnedState $State $Name)) { throw "$Name baslatilamadi. Gunluk: $(Join-Path $RuntimeDir "$Name.log")" }
        Start-Sleep -Milliseconds 500
    } while ([datetime]::UtcNow -lt $deadline)
    throw "$Name hazir olmadi veya port baska uygulamaya ait. Gunluk: $(Join-Path $RuntimeDir "$Name.log")"
}

function Start-ServiceSupervisor([string]$Name) {
    if (Test-ServiceReady $Name) { Write-Host "$Name zaten hazir; ikinci kez baslatilmadi."; return $null }
    $state = Read-ServiceState $Name
    if (Test-OwnedState $state $Name) { Write-Host "$Name zaten baslatiliyor; hazir olmasi bekleniyor..."; Wait-Service $Name $state; return $null }
    $port = if ($Name -eq 'backend') { $BackendPort } else { $FrontendPort }
    if ($Name -ne 'bridge' -and (Test-PortOccupied $port)) { Write-Host "$port portu kullanimda; mevcut servisin hazirligi kontrol ediliyor..."; Wait-Service $Name; return $null }
    $scriptPath = Join-Path $ProjectRoot "start-$Name.ps1"
    if (!(Test-Path -LiteralPath $scriptPath)) { throw "$scriptPath bulunamadi." }
    $tokenValue = [guid]::NewGuid().ToString()
    $args = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$HelperPath`" -Mode Service -Service $Name -Token $tokenValue"
    $supervisor = Start-Process -FilePath $PowerShellExe -ArgumentList $args -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
    [void]$supervisor.Handle
    $entry = @{ Service = $Name; Token = $tokenValue; Process = $supervisor; StartedUtc = $supervisor.StartTime.ToUniversalTime() }
    $script:NewServices += $entry
    Write-Host "$Name baslatiliyor..."
    $deadline = [datetime]::UtcNow.AddSeconds(20)
    do {
        $state = Read-ServiceState $Name
        if ($state -and $state.Token -eq $tokenValue -and (Test-OwnedState $state $Name)) {
            if ($Name -eq 'bridge') {
                Start-Sleep -Seconds 2
                if (!(Test-OwnedState (Read-ServiceState $Name) $Name)) { throw 'USB bridge baslatilamadi; COM portu baska bridge tarafindan kullaniliyor olabilir. bridge.log dosyasini kontrol edin.' }
            } else { Wait-Service $Name $state }
            Write-Host "$Name hazir."; return $entry
        }
        if ($supervisor.HasExited) { throw "$Name baslaticisi acilamadi. Gunluk: $(Join-Path $RuntimeDir "$Name-launcher.log")" }
        Start-Sleep -Milliseconds 150
    } while ([datetime]::UtcNow -lt $deadline)
    throw "$Name surec takibi zamaninda hazir olmadi. Gunlukleri kontrol edin."
}

function Run-ServiceSupervisor {
    $guid = [guid]::Empty
    if (!$Service -or ![guid]::TryParse($Token, [ref]$guid)) { throw 'Servis takip anahtari gecersiz.' }
    Initialize-JobApi
    $child = $null; $exitCode = 1
    $statePath = Get-StatePath $Service
    try {
        $jobName = "Local\FitGate-$ProjectKey-$Service-$guid"
        $args = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$HelperPath`" -Mode Run -Service $Service -Token $guid"
        $child = New-Object -TypeName 'FitGateJobs+Child' -ArgumentList @($jobName, $PowerShellExe, $args, $ProjectRoot, (Join-Path $RuntimeDir "$Service.log"))
        $state = @{ ProjectRoot = $ProjectRoot; Service = $Service; Token = $guid.ToString(); JobName = $jobName; SupervisorPid = $PID; SupervisorStartedUtc = (Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o'); ChildPid = $child.Id }
        $temporary = Join-Path $RuntimeDir "$Service-$guid.tmp"
        [IO.File]::WriteAllText($temporary, ($state | ConvertTo-Json), [Text.Encoding]::UTF8)
        Move-Item -LiteralPath $temporary -Destination $statePath -Force
        $exitCode = $child.Wait()
    } finally {
        if ($child) { $child.Dispose() }
        $current = Read-ServiceState $Service
        if ($current -and $current.Token -eq [string]$guid) { Remove-Item -LiteralPath $statePath -ErrorAction SilentlyContinue }
    }
    return $exitCode
}

if ($Mode -eq 'Load') { return }
try { [void][IO.Directory]::CreateDirectory($RuntimeDir) }
catch { Write-Host 'HATA: FitGate gunluk/takip klasoru olusturulamadi. Proje klasoru yazma izinlerini kontrol edin.' -ForegroundColor Red; exit 1 }
if ($Mode -eq 'Run') {
    if (!$Service) { exit 1 }
    $log = Join-Path $RuntimeDir "$Service.log"
    try {
        & (Join-Path $ProjectRoot "start-$Service.ps1")
        if ($LASTEXITCODE) { exit $LASTEXITCODE }
        exit 0
    } catch { [Console]::Error.WriteLine($_.ToString()); exit 1 }
}
if ($Mode -eq 'Service') {
    try { exit (Run-ServiceSupervisor) }
    catch { $_ | Out-String | Add-Content -LiteralPath (Join-Path $RuntimeDir "$Service-launcher.log"); exit 1 }
}

$mutex = New-Object Threading.Mutex($false, "Local\FitGate-Launcher-$ProjectKey")
$locked = $false; $exitCode = 0
try {
    try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
    if (!$locked) { throw 'Baska bir FitGate baslatma/durdurma islemi devam ediyor. Biraz bekleyip tekrar deneyin.' }
    if ($Mode -eq 'Stop') {
        Stop-OwnedService 'bridge'
        Stop-OwnedService 'frontend'
        Stop-OwnedService 'backend'
        Write-Host 'Docker ve PostgreSQL durdurulmadi. Onceden acik/diger uygulama sureclerine dokunulmadi.'
    } else {
        Wait-Postgres
        [void](Start-ServiceSupervisor 'backend')
        [void](Start-ServiceSupervisor 'frontend')
        if (Test-Path -LiteralPath (Join-Path $ProjectRoot 'backend\hardware\.env')) {
            try { [void](Start-ServiceSupervisor 'bridge') }
            catch { Write-Warning "Arduino bridge: $($_.Exception.Message) FastAPI ve React acik kalacak." }
        }
        if (!(Test-ServiceReady 'backend') -or !(Test-ServiceReady 'frontend')) { throw 'Servislerden biri kapanmis; FitGate tam olarak hazir degil.' }
        if (!$NoBrowser) {
            try { Start-Process "http://127.0.0.1:$FrontendPort/" }
            catch { Write-Warning "FitGate hazir, ancak tarayici otomatik acilamadi. http://127.0.0.1:$FrontendPort/ adresini elle acin." }
        }
        Write-Host "FitGate hazir: http://127.0.0.1:$FrontendPort/"
    }
} catch {
    Write-Host "HATA: $($_.Exception.Message)" -ForegroundColor Red
    if ($Mode -eq 'Start') {
        foreach ($entry in @($NewServices)) {
            try { Stop-OwnedService $entry.Service $entry.Token } catch { Write-Warning $_.Exception.Message }
            # A supervisor that failed before writing its state still belongs to
            # this invocation; killing it closes only its own job handle.
            if (!$entry.Process.HasExited -and $entry.Process.StartTime.ToUniversalTime() -eq $entry.StartedUtc) { $entry.Process.Kill() }
        }
    }
    $exitCode = 1
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
exit $exitCode
