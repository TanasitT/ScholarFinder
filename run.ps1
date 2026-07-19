# Starts the ReviewerFinder backend (uvicorn) and frontend (vite) together.
# Requires: backend/.venv already created with deps installed, frontend/node_modules installed,
# and a running local Ollama if you intend to use search/chat.
#
# Usage:  powershell -File run.ps1
# Stop:   Ctrl+C (stops both child processes)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

$backendPython = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $backendPython)) {
    throw "Backend venv not found at $backendPython. Create it first: cd backend; python -m pip install -e `".[dev,chatbot,api]`""
}

Write-Host "Starting backend (uvicorn) on http://127.0.0.1:8000 ..."
$backend = Start-Process -FilePath $backendPython `
    -ArgumentList "-m", "reviewerfinder.cli", "serve" `
    -WorkingDirectory (Join-Path $root "backend") `
    -PassThru -NoNewWindow

Write-Host "Starting frontend (vite) on http://localhost:5173 ..."
$frontend = Start-Process -FilePath "npm" `
    -ArgumentList "run", "dev" `
    -WorkingDirectory (Join-Path $root "frontend") `
    -PassThru -NoNewWindow

Write-Host ""
Write-Host "Backend PID:  $($backend.Id)"
Write-Host "Frontend PID: $($frontend.Id)"
Write-Host "Press Ctrl+C to stop both."

try {
    Wait-Process -Id $backend.Id, $frontend.Id
}
finally {
    Write-Host "Stopping backend and frontend..."
    Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue -Force
    Stop-Process -Id $frontend.Id -ErrorAction SilentlyContinue -Force
}
