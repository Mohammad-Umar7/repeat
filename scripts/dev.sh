#!/usr/bin/env bash
# One-command dev start: backend on :8765 and the extension build in watch mode.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -f "$ROOT/backend/.env" ] || { cp "$ROOT/.env.example" "$ROOT/backend/.env"; echo "created backend/.env from .env.example (demo mode)"; }
( cd "$ROOT/backend" && python -m repeat ) &
BACK=$!
trap 'kill $BACK 2>/dev/null || true' EXIT
( cd "$ROOT/extension" && [ -d node_modules ] || npm install ) 
( cd "$ROOT/extension" && npm run build )
echo
echo "Backend: http://127.0.0.1:8765/docs   Extension: load extension/dist unpacked in chrome://extensions"
echo "Ctrl+C stops the backend."
wait $BACK
