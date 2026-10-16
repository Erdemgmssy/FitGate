# Injected only into the temporary launcher copy. Never invokes a Docker executable.
function Invoke-Docker([string]$Arguments, [int]$TimeoutMilliseconds = 5000) {
    Add-Content -LiteralPath (Join-Path $PSScriptRoot 'docker-stub-calls.log') -Value $Arguments
    if ($Arguments -like 'context inspect*') { return @{ Code = 0; Text = 'npipe://fixture' } }
    $ready = Join-Path $PSScriptRoot 'fake-postgres-ready'
    if ($Arguments -like 'inspect *') {
        return @{ Code = 0; Text = (Test-Path -LiteralPath $ready).ToString().ToLowerInvariant() }
    }
    if ($Arguments -eq 'start fitgate-postgres') { [IO.File]::WriteAllText($ready, 'fixture') }
    return @{ Code = 0; Text = 'fixture' }
}
