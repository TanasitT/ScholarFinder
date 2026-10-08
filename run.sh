#!/usr/bin/env bash
# Starts the ScholarFinder backend (uvicorn) and frontend (vite) together on macOS/Linux.
# Windows users: use run.ps1 instead.
#
# Requires: backend/.venv already created with deps installed, frontend/node_modules installed,
# and a running local Ollama if you intend to use search/chat.
#
# Usage:  ./run.sh
# Stop:   Ctrl+C (stops both child processes)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PYTHON="$ROOT/backend/.venv/bin/python"

if [ ! -x "$BACKEND_PYTHON" ]; then
  echo "Backend venv not found at $BACKEND_PYTHON." >&2
  echo "Create it first:  cd backend && python3 -m venv .venv && .venv/bin/python -m pip install -e \".[dev,chatbot,api]\"" >&2
  exit 1
fi

if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "frontend/node_modules not found. Run:  cd frontend && npm install" >&2
  exit 1
fi

# All children share this script's process group, so `kill 0` stops the backend,
# npm and the Vite process it spawns, without leaving orphans behind.
trap 'trap - INT TERM EXIT; echo; echo "Stopping backend and frontend..."; kill 0' INT TERM EXIT

echo "Starting backend (uvicorn) on http://127.0.0.1:8000 ..."
( cd "$ROOT/backend" && exec "$BACKEND_PYTHON" -m reviewerfinder.cli serve ) &
BACKEND_PID=$!

echo "Starting frontend (vite) on http://localhost:5173 ..."
( cd "$ROOT/frontend" && exec npm run dev ) &
FRONTEND_PID=$!

echo
echo "Backend PID:  $BACKEND_PID"
echo "Frontend PID: $FRONTEND_PID"
echo "Press Ctrl+C to stop both."

wait
