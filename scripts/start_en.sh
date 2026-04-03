#!/bin/bash
# Unified Startup for English Notebook Services on Port 8000

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PORT=8000
FRONTEND_PORT=3000

cd "$PROJECT_ROOT"

# Cleanup
echo "Cleaning up processes on port $PORT and $FRONTEND_PORT..."
lsof -ti:$PORT | xargs kill -9 2>/dev/null
lsof -ti:$FRONTEND_PORT | xargs kill -9 2>/dev/null
pkill -9 -f "uvicorn fastapi_app.main:app" 2>/dev/null
pkill -9 -f "vite.*--port $FRONTEND_PORT" 2>/dev/null

# Activate conda and start backend
echo "Starting backend on port $PORT..."
source /home/navin/work/packages/miniconda3/bin/activate opennotebook
set -a
[ -f fastapi_app/.env ] && source fastapi_app/.env
set +a
nohup python -m uvicorn fastapi_app.main:app --host 0.0.0.0 --port $PORT > logs/backend.log 2>&1 &

# Start frontend
echo "Starting English frontend on port $FRONTEND_PORT..."
cd frontend_en
nohup npm run dev -- --port $FRONTEND_PORT --host 0.0.0.0 > ../logs/frontend.log 2>&1 &

echo "Services starting..."
sleep 5
echo "Backend: http://localhost:$PORT"
echo "Frontend: http://localhost:$FRONTEND_PORT"
