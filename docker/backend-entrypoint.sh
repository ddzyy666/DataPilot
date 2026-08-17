#!/bin/sh
set -eu

echo "Initializing DataPilot database..."
python -m app.db.seed

echo "Starting DataPilot API..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
