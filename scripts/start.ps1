$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Run .\scripts\setup.ps1 first."
}

$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCommand) {
    $npmFile = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS*\node-*-win-x64\npm.cmd" -ErrorAction SilentlyContinue | Select-Object -First 1
}
if (-not $npmCommand -and -not $npmFile) {
    $npmFile = Get-ChildItem "$projectRoot\tools\node\node-*-win-x64\npm.cmd" -ErrorAction SilentlyContinue | Select-Object -First 1
}
if (-not $npmCommand -and -not $npmFile) { throw "Node.js is missing. Run .\scripts\setup.ps1 first." }
$npmExecutable = if ($npmCommand) { $npmCommand.Source } else { $npmFile.FullName }
$nodeDirectory = Split-Path -Parent $npmExecutable
$env:Path = "$nodeDirectory;$env:Path"

$opaExecutable = Join-Path $projectRoot "tools\opa\opa.exe"
if (-not (Test-Path -LiteralPath $opaExecutable)) {
    throw "OPA is missing. Run .\scripts\setup-security.ps1 first."
}
$opaListener = Get-NetTCPConnection -LocalPort 8181 -State Listen -ErrorAction SilentlyContinue
if (-not $opaListener) {
    $opa = Start-Process -FilePath $opaExecutable -ArgumentList "run", "--server", "--addr=127.0.0.1:8181", "$projectRoot\security\opa" -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
}

$backend = Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "-m", "uvicorn", "backend.main:app", "--reload" -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
$frontend = Start-Process -FilePath $npmExecutable -ArgumentList "--prefix", "apps/web", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173", "--strictPort" -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru

Write-Host "Backend PID: $($backend.Id)  http://localhost:8000/docs"
Write-Host "Frontend PID: $($frontend.Id) http://localhost:5173"
if ($opa) { Write-Host "OPA PID: $($opa.Id)        http://localhost:8181" }
Write-Host "Use Stop-Process with the displayed process IDs to stop the services."
