#!/usr/bin/env bash
# One-command launch: backend (FastAPI, port 8765) + frontend (Vite, port 5180). Ctrl-C stops both.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [ ! -x .venv/bin/python ]; then
  echo "Creating Python 3.11 venv…"; (command -v uv >/dev/null && uv venv --python 3.11 .venv) || python3.11 -m venv .venv
  .venv/bin/python -m pip install -q -r backend/requirements.txt 2>/dev/null || uv pip install --python .venv/bin/python -r backend/requirements.txt
fi
if [ ! -d frontend/node_modules ]; then (cd frontend && npm install --no-audit --no-fund); fi
export WINDTUNNEL_ENGINE="${WINDTUNNEL_ENGINE:-heuristic}"   # heuristic | laya | needle
export WINDTUNNEL_TEMPLATE="${WINDTUNNEL_TEMPLATE:-prototype}" # prototype | charity500
export WINDTUNNEL_SEED="${WINDTUNNEL_SEED:-7}"
mkdir -p data
(cd backend && exec "$ROOT/.venv/bin/python" -m uvicorn windtunnel.server:app --host 127.0.0.1 --port 8765 --log-level warning) &
BACK=$!
trap 'kill $BACK 2>/dev/null; exit 0' INT TERM EXIT
echo "backend  → http://127.0.0.1:8765  (engine=$WINDTUNNEL_ENGINE template=$WINDTUNNEL_TEMPLATE seed=$WINDTUNNEL_SEED)"
echo "frontend → http://127.0.0.1:5180"
cd frontend && exec npx vite --port 5180 --strictPort
