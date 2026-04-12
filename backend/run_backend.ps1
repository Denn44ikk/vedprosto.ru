$ErrorActionPreference = "Stop"

$backendDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$systemPython = "C:\Python314\python.exe"

if (-not (Test-Path $systemPython)) {
    throw "System Python not found: $systemPython"
}

Write-Host "Using system Python: $systemPython"
Set-Location $backendDir
& $systemPython -m uvicorn app.main:app --host 127.0.0.1 --port 8011
