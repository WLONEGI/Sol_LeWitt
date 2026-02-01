#!/bin/zsh

# AI Slide System Restart Script
# This script stops existing backend, frontend, and proxy processes and restarts them.

# Get the script's directory and project root
SCRIPT_DIR=$(cd $(dirname $0); pwd)
BACKEND_DIR=$(cd $SCRIPT_DIR/..; pwd)
PROJECT_ROOT=$(cd $BACKEND_DIR/..; pwd)
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# Load essential configuration from backend/.env
PROJECT_ID="aerobic-stream-483505-a0" # Fallback
if [ -f "$BACKEND_DIR/.env" ]; then
    # Extract VERTEX_PROJECT_ID if it exists
    EXTRACTED_ID=$(grep "^VERTEX_PROJECT_ID=" "$BACKEND_DIR/.env" | cut -d '=' -f2 | tr -d '"' | tr -d "'")
    if [ ! -z "$EXTRACTED_ID" ]; then
        PROJECT_ID=$EXTRACTED_ID
    fi
fi

# Configuration
DB_INSTANCE="langgraph-pg-core"
DB_REGION="asia-northeast1"
CONNECTION_NAME="$PROJECT_ID:$DB_REGION:$DB_INSTANCE"

echo "=== Restarting AI Slide Multi-Process Environment ==="
echo "Project ID: $PROJECT_ID"
echo "Connection: $CONNECTION_NAME"

# 1. Stopping existing processes
echo "[1/2] Stopping existing processes..."

# Kill Cloud SQL Proxy
pkill -f "cloud-sql-proxy" && echo "  - Stopped cloud-sql-proxy"

# Kill Backend (uv/uvicorn)
pkill -f "uvicorn.*app:app" && echo "  - Stopped backend (uvicorn)"
pkill -f "uv run uvicorn" && echo "  - Stopped backend (uv wrapper)"

# Kill Frontend (port 3000)
lsof -ti:3000 | xargs kill -9 2>/dev/null && echo "  - Stopped frontend on port 3000"
# Kill Backend port 8000
lsof -ti:8000 | xargs kill -9 2>/dev/null && echo "  - Stopped process on port 8000"

sleep 2

# 2. Starting processes
echo "[2/2] Starting services in background..."

# Start Cloud SQL Proxy
cd "$BACKEND_DIR"
if [ -f "./cloud-sql-proxy" ]; then
    nohup ./cloud-sql-proxy "$CONNECTION_NAME" > proxy.log 2>&1 &
    echo "  - Cloud SQL Proxy started (PID: $!). Logs: backend/proxy.log"
else
    echo "  - ⚠️ Error: cloud-sql-proxy binary not found in $BACKEND_DIR"
fi

# Start Backend
if [ -d ".venv" ]; then
    # Start uvicorn via uv in background
    nohup uv run uvicorn src.app.app:app --reload --port 8000 > backend.log 2>&1 &
    echo "  - Backend started (PID: $!). Logs: backend/backend.log"
else
    echo "  - ⚠️ Error: .venv not found in $BACKEND_DIR. Run uv sync first."
fi

# Start Frontend
cd "$FRONTEND_DIR"
if [ -d "node_modules" ]; then
    nohup npm run dev > frontend.log 2>&1 &
    echo "  - Frontend started (PID: $!). Logs: frontend/frontend.log"
else
    echo "  - ⚠️ Error: node_modules not found in $FRONTEND_DIR. Run npm install first."
fi

echo "===================================================="
echo "All services have been triggered to restart."
echo "Use the following commands to check logs:"
echo "  tail -f $BACKEND_DIR/backend.log"
echo "  tail -f $FRONTEND_DIR/frontend.log"
echo "  tail -f $BACKEND_DIR/proxy.log"
echo "===================================================="
