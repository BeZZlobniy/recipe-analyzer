$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $ProjectRoot "backend"
$FrontendDir = Join-Path $ProjectRoot "frontend"
$BackendVenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"

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

if (-not (Test-Path $BackendVenvPython)) {
    Write-Host "Creating backend virtual environment..."
    Push-Location $BackendDir
    python -m venv .venv
    Pop-Location
}

Write-Host "Installing backend dependencies..."
& $BackendVenvPython -m pip install -r (Join-Path $BackendDir "requirements.txt")
Ensure-CudaTorch

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
