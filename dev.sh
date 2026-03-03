#!/usr/bin/env bash
set -e

cleanup() {
  echo ""
  echo "Shutting down..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null
  wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null
  exit 0
}
trap cleanup INT TERM

echo "Starting backend on http://localhost:8000 ..."
uv run uvicorn backend.main:app --reload --reload-dir backend --port 8000 &
BACKEND_PID=$!

echo "Starting frontend on http://localhost:3000 ..."
python3 -m http.server 3000 --directory frontend &
FRONTEND_PID=$!

echo "Ready. Press Ctrl+C to stop."
wait
