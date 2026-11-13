param([string]$NpmExecutable = "")

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$downloadDirectory = Join-Path $projectRoot "tools\downloads"
$opaDirectory = Join-Path $projectRoot "tools\opa"
$opaExecutable = Join-Path $opaDirectory "opa.exe"
New-Item -ItemType Directory -Force -Path $downloadDirectory, $opaDirectory | Out-Null

if (-not (Test-Path -LiteralPath $opaExecutable)) {
    $version = "v1.11.0"
    $binaryUrl = "https://openpolicyagent.org/downloads/$version/opa_windows_amd64.exe"
    $checksumUrl = "$binaryUrl.sha256"
    $checksumPath = Join-Path $downloadDirectory "opa.sha256"
    Invoke-WebRequest -Uri $binaryUrl -OutFile $opaExecutable
    Invoke-WebRequest -Uri $checksumUrl -OutFile $checksumPath
    $expected = ((Get-Content -Raw -LiteralPath $checksumPath).Trim() -split "\s+")[0]
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $opaExecutable).Hash
    if ($actual.ToLowerInvariant() -ne $expected.ToLowerInvariant()) {
        throw "OPA checksum verification failed."
    }
}

& $opaExecutable test (Join-Path $projectRoot "security\opa") -v

if (-not $NpmExecutable) {
    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($npmCommand) { $NpmExecutable = $npmCommand.Source }
}
if (-not $NpmExecutable) {
    $npmFile = Get-ChildItem "$projectRoot\tools\node\node-*-win-x64\npm.cmd" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($npmFile) { $NpmExecutable = $npmFile.FullName }
}
if (-not $NpmExecutable) { throw "Node.js/npm is required for Promptfoo." }
$nodeDirectory = Split-Path -Parent $NpmExecutable
$env:Path = "$nodeDirectory;$env:Path"
& $NpmExecutable --prefix (Join-Path $projectRoot "security\promptfoo") install
& $NpmExecutable --prefix (Join-Path $projectRoot "security\promptfoo") audit --audit-level=high

Write-Host "Security tooling verified: OPA policy tests and Promptfoo dependency audit passed." -ForegroundColor Green
