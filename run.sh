#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Check virtualenv
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r backend/requirements.txt
    python -m playwright install chromium
else
    source venv/bin/activate
fi

PORT=${PORT:-8050}
HOST=${HOST:-0.0.0.0}

echo "🐕 Starting Renfe Dog Spot Checker on http://localhost:${PORT}"
exec python -m uvicorn backend.src.main:app --host "$HOST" --port "$PORT" --reload
