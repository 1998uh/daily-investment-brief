param(
    [switch]$InstallPlaywright
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvDir = Join-Path $RepoRoot ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found on PATH. Install Python 3.10+ first."
}

if (-not (Test-Path $PythonExe)) {
    Write-Host "[info] Creating local virtual environment: $VenvDir"
    python -m venv $VenvDir
}

Write-Host "[info] Upgrading pip"
& $PythonExe -m pip install -U pip

Push-Location $RepoRoot
try {
    if ($InstallPlaywright) {
        Write-Host "[info] Installing project dependencies with collector extras"
        & $PythonExe -m pip install -e ".[collect]"
        Write-Host "[info] Installing Playwright Chromium"
        & $PythonExe -m playwright install chromium
    }
    else {
        Write-Host "[info] Installing project dependencies"
        & $PythonExe -m pip install -e .
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "[ok] Dependencies are installed in .venv"
Write-Host "Activate it with:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host ""
Write-Host "Then run:"
Write-Host "  daily-brief --help"
