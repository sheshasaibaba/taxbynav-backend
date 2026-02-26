#!/bin/sh
set -e
# Run migrations when DATABASE_URL is set (Cloud Run / local)
if [ -n "$DATABASE_URL" ]; then
  echo "Running database migrations..."
  alembic upgrade head
fi
PORT="${PORT:-8080}"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
