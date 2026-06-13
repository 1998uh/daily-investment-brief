#!/usr/bin/env bash
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8080}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
MAX_RETRIES=30
SLEEP=2

echo "Waiting for backend health..."
for i in $(seq 1 $MAX_RETRIES); do
    if curl -sf "http://localhost:${BACKEND_PORT}/api/health" > /dev/null 2>&1; then
        echo "Backend healthy"
        break
    fi
    if [ $i -eq $MAX_RETRIES ]; then
        echo "Backend failed to start after ${MAX_RETRIES} retries"
        exit 1
    fi
    sleep $SLEEP
done

echo "Waiting for frontend health..."
for i in $(seq 1 $MAX_RETRIES); do
    if curl -sf "http://localhost:${FRONTEND_PORT}/" > /dev/null 2>&1; then
        echo "Frontend healthy"
        break
    fi
    if [ $i -eq $MAX_RETRIES ]; then
        echo "Frontend failed to start after ${MAX_RETRIES} retries"
        exit 1
    fi
    sleep $SLEEP
done

echo ""
echo "All services healthy!"
echo "Open: http://localhost:${FRONTEND_PORT}"
