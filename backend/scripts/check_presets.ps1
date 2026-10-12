# Run all displayed preset checks without database or model access.
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Project Python environment missing. Install project dependencies first.'
}
$taskPreviousPythonPath = $env:PYTHONPATH
$taskExitCode = 1
try {
    $env:PYTHONPATH = Join-Path $taskRoot 'backend'
    Push-Location $taskRoot
    try {
        & $taskPython -B -m unittest -v backend.scripts.test_knowledge_presets
        $taskExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
} finally {
    $env:PYTHONPATH = $taskPreviousPythonPath
}
exit $taskExitCode
