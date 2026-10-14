#!/bin/sh
set -e
DB_URL="${DATABASE_URL:-$database_url}"
if [ -n "$DB_URL" ]; then
  echo "Running database migrations..."
  DATABASE_URL="$DB_URL" alembic upgrade head || true
fi
PORT="${PORT:-8080}"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
