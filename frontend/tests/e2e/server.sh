#!/usr/bin/env sh
# Start a throwaway OAK server for the end-to-end tests: fresh data directory, the Game Data
# test subset and the production frontend build. Run `npm run build` first.
set -eu

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
PYTHON="${OAK_E2E_PYTHON:-$ROOT/backend/.venv/bin/python}"
PORT="${OAK_E2E_PORT:-8091}"
DATA_DIR="$(mktemp -d)"

export OAK_DATA_DIR="$DATA_DIR"
export OAK_SECRET_KEY="e2e-only-secret-key-not-used-anywhere-else-0123456789"
export OAK_BASE_URL="http://127.0.0.1:$PORT"
export OAK_GAMEDATA_AUTO_UPDATE=false
export OAK_EVENTS_AUTO_UPDATE=false
export OAK_FRONTEND_DIR="$ROOT/frontend/dist"
export OAK_LOG_LEVEL=WARNING

"$PYTHON" "$ROOT/scripts/e2e_seed_gamedata.py"
cd "$ROOT/backend"
exec "$PYTHON" -m uvicorn --factory app.main:create_app --host 127.0.0.1 --port "$PORT" --no-access-log
