$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $ProjectRoot "backend"
$FrontendDir = Join-Path $ProjectRoot "frontend"
$BackendVenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$BackendVenvActivate = Join-Path $BackendDir ".venv\Scripts\Activate.ps1"

function Test-NvidiaGpu {
    return $null -ne (Get-Command nvidia-smi -ErrorAction SilentlyContinue)
}

function Get-TorchRuntimeInfo {
    if (-not (Test-Path $BackendVenvPython)) {
        return $null
    }

    try {
        $json = & $BackendVenvPython -c "import json, torch; print(json.dumps({'version': torch.__version__, 'cuda_available': bool(torch.cuda.is_available()), 'cuda_version': torch.version.cuda}, ensure_ascii=True))"
        if (-not $json) {
            return $null
        }
        return $json | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Ensure-CudaTorch {
    if (-not (Test-NvidiaGpu)) {
        return
    }

    $torchInfo = Get-TorchRuntimeInfo
    if ($torchInfo -and $torchInfo.cuda_available) {
        Write-Host "PyTorch CUDA backend is already available ($($torchInfo.version))."
        return
    }

    Write-Host "NVIDIA GPU detected. Installing CUDA-enabled PyTorch for backend..."
    & $BackendVenvPython -m pip install --upgrade --index-url https://download.pytorch.org/whl/cu128 torch | Out-Host
}

if (-not (Test-Path $BackendDir)) {
    throw "Backend directory not found: $BackendDir"
}

if (-not (Test-Path $FrontendDir)) {
    throw "Frontend directory not found: $FrontendDir"
}

if (-not (Test-Path $BackendVenvPython)) {
    Write-Host "Creating backend virtual environment..."
    Push-Location $BackendDir
    python -m venv .venv
    Pop-Location
}

Write-Host "Installing/updating backend dependencies..."
& $BackendVenvPython -m pip install -r (Join-Path $BackendDir "requirements.txt") | Out-Host
Ensure-CudaTorch

if (-not (Test-Path (Join-Path $BackendDir ".env"))) {
    Copy-Item (Join-Path $BackendDir ".env.example") (Join-Path $BackendDir ".env")
}

if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Host "Installing frontend dependencies..."
    Push-Location $FrontendDir
    npm install | Out-Host
    Pop-Location
}

Write-Host "Starting backend in a new PowerShell window..."
Start-Process cmd.exe -ArgumentList "/k", "cd /d `"$BackendDir`" && call `"$BackendDir\.venv\Scripts\activate.bat`" && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

Write-Host "Waiting for backend health endpoint..."
$healthUrl = "http://127.0.0.1:8000/api/health"
$backendReady = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-WebRequest -UseBasicParsing $healthUrl
        if ($response.StatusCode -eq 200) {
            $backendReady = $true
            break
        }
    } catch {
    }
}

Write-Host "Starting frontend in a new PowerShell window..."
Start-Process cmd.exe -ArgumentList "/k", "cd /d `"$FrontendDir`" && npm run dev"

Write-Host ""
Write-Host "Application is starting."
if (-not $backendReady) {
    Write-Host "Warning: backend healthcheck did not respond before frontend start." -ForegroundColor Yellow
}
Write-Host "Frontend: http://localhost:5173"
Write-Host "Backend API: http://localhost:8000"
Write-Host "Backend docs: http://localhost:8000/docs"
Write-Host "Login: admin / admin"
