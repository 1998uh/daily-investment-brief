#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Check .env exists
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found. Copy .env.example and fill in values:"
    echo "  cp .env.example .env"
    exit 1
fi

# Check required env vars
source .env
if [ -z "${AGENT_JWT_SECRET:-}" ]; then
    echo "ERROR: AGENT_JWT_SECRET must be set in .env"
    echo "  Generate one: python -c \"import secrets; print(secrets.token_hex(32))\""
    exit 1
fi

# Create memory directory if needed
mkdir -p "${MEMORY_DIR:-./memory}"

echo "Building and starting services..."
docker compose up --build -d

echo ""
echo "Services started:"
echo "  Backend:  http://localhost:${BACKEND_PORT:-8080}"
echo "  Frontend: http://localhost:${FRONTEND_PORT:-3000}"
echo ""
echo "To view logs: docker compose logs -f"
echo "To stop:      docker compose down"
