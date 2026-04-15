$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $ProjectRoot "backend"
$FrontendDir = Join-Path $ProjectRoot "frontend"
$BackendVenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $BackendVenvPython)) {
    Write-Host "Creating backend virtual environment..."
    Push-Location $BackendDir
    python -m venv .venv
    Pop-Location
}

Write-Host "Installing backend dependencies..."
& $BackendVenvPython -m pip install -r (Join-Path $BackendDir "requirements.txt")

if (-not (Test-Path (Join-Path $BackendDir ".env"))) {
    Write-Host "Creating backend .env from template..."
    Copy-Item (Join-Path $BackendDir ".env.example") (Join-Path $BackendDir ".env")
}

Write-Host "Installing frontend dependencies..."
Push-Location $FrontendDir
npm install
Pop-Location

Write-Host ""
Write-Host "Setup complete."
Write-Host "Run the app with:"
Write-Host "  .\run-app.ps1"
