param([switch]$SkipModel)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python is not installed. Install free Python 3.12+ and run this script again."
}
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCommand) {
    $npmFile = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS*\node-*-win-x64\npm.cmd" -ErrorAction SilentlyContinue | Select-Object -First 1
}
if (-not $npmCommand -and -not $npmFile) { throw "Node.js is not installed. Install free Node.js 22+ and run this script again." }
$npmExecutable = if ($npmCommand) { $npmCommand.Source } else { $npmFile.FullName }
$nodeDirectory = Split-Path -Parent $npmExecutable
$env:Path = "$nodeDirectory;$env:Path"
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    throw "Ollama is not installed. Install free Ollama and run this script again."
}

if (-not (Test-Path ".venv")) { python -m venv .venv }
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -e ".[dev]"
& $npmExecutable --prefix apps/web install
& ".\scripts\setup-security.ps1" -NpmExecutable $npmExecutable
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
if (-not $SkipModel) { ollama pull qwen3.5:4b }

Write-Host "Setup complete. Run .\scripts\start.ps1" -ForegroundColor Green
