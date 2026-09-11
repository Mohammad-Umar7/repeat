# Restores the demo state in one command (Windows).
# Usage: .\scripts\reset-demo.ps1
# If the backend is running it resets over HTTP (sub-second). Otherwise it
# seeds the SQLite store directly so the next boot starts clean.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$port = 8765
$envFile = Join-Path $root "backend\.env"
if (Test-Path $envFile) {
    $line = Get-Content $envFile | Where-Object { $_ -match '^\s*REPEAT_PORT\s*=' } | Select-Object -First 1
    if ($line) { $port = [int]($line -split '=', 2)[1].Trim() }
}

try {
    $res = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$port/demo/reset" -TimeoutSec 5
    Write-Host "Demo reset over HTTP. Workflow: $($res.workflow.name)  Store: $($res.stats | ConvertTo-Json -Compress)"
    exit 0
} catch {
    Write-Host "Backend not running on :$port, seeding SQLite directly..."
}

Push-Location (Join-Path $root "backend")
try {
    python -c "import asyncio, os; os.environ.setdefault('REPEAT_DEMO_MODE','true'); from repeat.bus import EventBus; from repeat.config import get_settings; from repeat.deps import Deps, set_deps; from repeat.integrations import get_integrations; from repeat.llm import get_llm; from repeat.store import Store; from repeat.seed import seed_demo
async def main():
    s = get_settings(); store = await Store(s.repeat_db_path).open()
    set_deps(Deps(settings=s, store=store, bus=EventBus(), integrations=get_integrations(), llm=get_llm()))
    r = await seed_demo(wipe=True); print('Seeded:', r['workflow']['name'], r['stats']); await store.close()
asyncio.run(main())"
} finally { Pop-Location }
