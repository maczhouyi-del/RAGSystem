param(
    [switch]$Json,
    [ValidateRange(1, 65535)][int]$Port = 8000,
    [ValidateRange(1, 65535)][int]$WebPort = 8080,
    [switch]$TestModel
)
$ErrorActionPreference = 'Stop'
$diagnosticRoot = Split-Path -Parent $PSScriptRoot
$diagnosticPython = $null
foreach ($candidate in @((Join-Path $diagnosticRoot '.venv/Scripts/python.exe'), 'python', 'python3', 'py')) {
    if (Test-Path $candidate) { $resolved = $candidate }
    else {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $command) { continue }
        $resolved = $command.Source
    }
    try {
        & $resolved -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { $diagnosticPython = $resolved; break }
    } catch { continue }
}
if (-not $diagnosticPython) {
    Write-Output 'python: missing - Install Python 3.11+ or create the project .venv; no files were modified.'
    exit 2
}
$diagnosticArguments = @((Join-Path $PSScriptRoot 'diagnose.py'), '--port', "$Port", '--web-port', "$WebPort")
if ($Json) { $diagnosticArguments += '--json' }
if ($TestModel) { $diagnosticArguments += '--test-model' }
$diagnosticEncoding = [Console]::OutputEncoding
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
    & $diagnosticPython @diagnosticArguments
    $diagnosticExitCode = $LASTEXITCODE
} finally {
    [Console]::OutputEncoding = $diagnosticEncoding
}
exit $diagnosticExitCode
