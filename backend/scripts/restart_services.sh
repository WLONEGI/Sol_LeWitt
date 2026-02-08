#!/bin/zsh

# AI Slide System Restart Script
# This script stops existing backend, frontend, and proxy processes and restarts them.

# Get the script's directory and project root
SCRIPT_DIR=$(cd $(dirname $0); pwd)
BACKEND_DIR=$(cd $SCRIPT_DIR/..; pwd)
PROJECT_ROOT=$(cd $BACKEND_DIR/..; pwd)
FRONTEND_DIR="$PROJECT_ROOT/frontend"
LOG_DIR="$PROJECT_ROOT/logs"

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

# Clean up log files
mkdir -p "$LOG_DIR"
rm -f "$LOG_DIR/backend.log" "$LOG_DIR/proxy.log" "$LOG_DIR/frontend.log" "$LOG_DIR/frontend_event.log"
touch "$LOG_DIR/backend.log" "$LOG_DIR/proxy.log" "$LOG_DIR/frontend.log" "$LOG_DIR/frontend_event.log"
echo "  - Cleaned up and recreated log files (logs/backend.log, logs/proxy.log, logs/frontend.log, logs/frontend_event.log)"

sleep 2

# 2. Starting processes
echo "[2/2] Starting services in background..."

# Start Cloud SQL Proxy
cd "$BACKEND_DIR"
if [ -f "./cloud-sql-proxy" ]; then
    nohup ./cloud-sql-proxy "$CONNECTION_NAME" --debug-logs > "$LOG_DIR/proxy.log" 2>&1 &
    echo "  - Cloud SQL Proxy started (PID: $!). Logs: logs/proxy.log"
else
    echo "  - ⚠️ Error: cloud-sql-proxy binary not found in $BACKEND_DIR"
fi

# Start Backend
if [ -d ".venv" ]; then
    # Start uvicorn via uv in background
    nohup uv run uvicorn src.app.app:app --reload --port 8000 --log-level debug > "$LOG_DIR/backend.log" 2>&1 &
    echo "  - Backend started (PID: $!). Logs: logs/backend.log"
else
    echo "  - ⚠️ Error: .venv not found in $BACKEND_DIR. Run uv sync first."
fi

# Wait for Backend to be ready
echo "Waiting for backend to be ready on port 8000..."
MAX_RETRIES=30
COUNT=0
while ! curl -s http://localhost:8000 > /dev/null; do
    sleep 1
    COUNT=$((COUNT+1))
    if [ $COUNT -ge $MAX_RETRIES ]; then
        echo "  - ⚠️ Timeout waiting for backend to start."
        break
    fi
    echo -n "."
done
echo ""
echo "  - Backend is ready."

# Start Frontend
cd "$FRONTEND_DIR"
if [ -d "node_modules" ]; then
    nohup npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
    echo "  - Frontend started (PID: $!). Logs: logs/frontend.log"
else
    echo "  - ⚠️ Error: node_modules not found in $FRONTEND_DIR. Run npm install first."
fi

echo "===================================================="
echo "All services have been triggered to restart."
echo "Use the following commands to check logs:"
echo "  tail -f $LOG_DIR/backend.log"
echo "  tail -f $LOG_DIR/frontend.log"
echo "  tail -f $LOG_DIR/frontend_event.log"
echo "  tail -f $LOG_DIR/proxy.log"
echo "===================================================="
