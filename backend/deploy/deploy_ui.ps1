$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$agentUiRoot = Resolve-Path (Join-Path $scriptDir "..\..")
$venvPython = Join-Path $agentUiRoot ".venv\Scripts\python.exe"
$pythonCmd = if (Test-Path $venvPython) { $venvPython } else { "python" }

Write-Host "Using Python: $pythonCmd"
& $pythonCmd -m pip install -r (Join-Path $scriptDir "deploy_requirements.txt")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
& $pythonCmd (Join-Path $scriptDir "deploy_ui.py") @args
exit $LASTEXITCODE
