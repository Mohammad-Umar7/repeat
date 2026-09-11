#!/usr/bin/env bash
# Restores the demo state in one command (macOS / Linux / Git Bash).
# Usage: ./scripts/reset-demo.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${REPEAT_PORT:-$(grep -E '^\s*REPEAT_PORT\s*=' "$ROOT/backend/.env" 2>/dev/null | head -1 | cut -d= -f2 | tr -d ' \r' || true)}"
PORT="${PORT:-8765}"

if OUT="$(curl -fsS -m 5 -X POST "http://127.0.0.1:${PORT}/demo/reset" 2>/dev/null)"; then
  echo "$OUT" | python -c 'import json,sys;d=json.load(sys.stdin);print("Demo reset over HTTP:", d["workflow"]["name"], d["stats"])'
  exit 0
fi

echo "Backend not running on :${PORT}, seeding SQLite directly..."
cd "$ROOT/backend"
REPEAT_DEMO_MODE="${REPEAT_DEMO_MODE:-true}" python - <<'PY'
import asyncio
from repeat.bus import EventBus
from repeat.config import get_settings
from repeat.deps import Deps, set_deps
from repeat.integrations import get_integrations
from repeat.llm import get_llm
from repeat.seed import seed_demo
from repeat.store import Store

async def main():
    s = get_settings()
    store = await Store(s.repeat_db_path).open()
    set_deps(Deps(settings=s, store=store, bus=EventBus(), integrations=get_integrations(), llm=get_llm()))
    r = await seed_demo(wipe=True)
    print("Seeded:", r["workflow"]["name"], r["stats"])
    await store.close()

asyncio.run(main())
PY
