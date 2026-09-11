"""SQLite store. Local-first: this file is the only place REPEAT persists anything.

Three tables, as promised: demonstrations, workflows, runs. Rich structure lives
in JSON columns so the schema never has to chase the models.
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite

from .models import Demonstration, Run, RunStatus, StepStatus, Workflow

SCHEMA = """
CREATE TABLE IF NOT EXISTS demonstrations (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    workflow_id TEXT,
    payload     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflows (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    run_count   INTEGER NOT NULL DEFAULT 0,
    payload     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    status      TEXT NOT NULL,
    payload     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS runs_created ON runs(created_at DESC);
"""


class Store:
    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> "Store":
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        return self

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "Store.open() was not awaited"
        return self._db

    # ── demonstrations ────────────────────────────────────────────────

    async def save_demonstration(self, demo: Demonstration) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO demonstrations(id, created_at, workflow_id, payload)"
            " VALUES (?,?,?,?)",
            (demo.id, demo.created_at, demo.workflow_id, demo.model_dump_json()),
        )
        await self.db.commit()

    async def get_demonstration(self, demo_id: str) -> Demonstration | None:
        cur = await self.db.execute("SELECT payload FROM demonstrations WHERE id=?", (demo_id,))
        row = await cur.fetchone()
        return Demonstration.model_validate_json(row["payload"]) if row else None

    # ── workflows ─────────────────────────────────────────────────────

    async def save_workflow(self, wf: Workflow) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO workflows(id, name, created_at, run_count, payload)"
            " VALUES (?,?,?,?,?)",
            (wf.id, wf.name, wf.created_at, wf.run_count, wf.model_dump_json()),
        )
        await self.db.commit()

    async def get_workflow(self, wf_id: str) -> Workflow | None:
        cur = await self.db.execute("SELECT payload FROM workflows WHERE id=?", (wf_id,))
        row = await cur.fetchone()
        return Workflow.model_validate_json(row["payload"]) if row else None

    async def list_workflows(self) -> list[Workflow]:
        cur = await self.db.execute("SELECT payload FROM workflows ORDER BY created_at DESC")
        return [Workflow.model_validate_json(r["payload"]) for r in await cur.fetchall()]

    async def delete_workflow(self, wf_id: str) -> bool:
        cur = await self.db.execute("DELETE FROM workflows WHERE id=?", (wf_id,))
        await self.db.commit()
        return cur.rowcount > 0

    # ── runs ──────────────────────────────────────────────────────────

    async def save_run(self, run: Run) -> None:
        run.touch()
        await self.db.execute(
            "INSERT OR REPLACE INTO runs(id, workflow_id, created_at, updated_at, status, payload)"
            " VALUES (?,?,?,?,?,?)",
            (
                run.id,
                run.workflow_id,
                run.created_at,
                run.updated_at,
                run.status.value,
                run.model_dump_json(),
            ),
        )
        await self.db.commit()

    async def get_run(self, run_id: str) -> Run | None:
        cur = await self.db.execute("SELECT payload FROM runs WHERE id=?", (run_id,))
        row = await cur.fetchone()
        return Run.model_validate_json(row["payload"]) if row else None

    async def list_runs(self, limit: int = 20) -> list[Run]:
        cur = await self.db.execute(
            "SELECT payload FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [Run.model_validate_json(r["payload"]) for r in await cur.fetchall()]

    async def latest_run(self) -> Run | None:
        runs = await self.list_runs(limit=1)
        return runs[0] if runs else None

    async def find_run_for_email(self, email_id: str) -> Run | None:
        """Prevents the ghost pill from re-offering an email that already has a live run."""
        cur = await self.db.execute(
            "SELECT payload FROM runs WHERE status NOT IN ('stopped','failed','reverted')"
            " ORDER BY created_at DESC LIMIT 50"
        )
        for r in await cur.fetchall():
            run = Run.model_validate_json(r["payload"])
            if run.email.id == email_id:
                return run
        return None

    async def stop_orphaned_runs(self, reason: str) -> int:
        """Graph state lives in memory; after a restart, in-flight runs can no longer be
        resumed. Mark them stopped so the panel never shows a dead 'running' state.
        Committed steps keep their undo tokens and remain reversible."""
        cur = await self.db.execute(
            "SELECT payload FROM runs WHERE status IN"
            " ('matched','planned','awaiting_approval','running','paused')"
        )
        n = 0
        for r in await cur.fetchall():
            run = Run.model_validate_json(r["payload"])
            for step in run.steps:
                if step.status.value in ("previewing", "running", "verifying"):
                    step.status = StepStatus.planned
            run.status = RunStatus.stopped
            run.pause_reason = reason
            await self.save_run(run)
            n += 1
        return n

    # ── demo reset ────────────────────────────────────────────────────

    async def wipe(self) -> None:
        for table in ("runs", "workflows", "demonstrations"):
            await self.db.execute(f"DELETE FROM {table}")
        await self.db.commit()

    async def stats(self) -> dict:
        out = {}
        for table in ("demonstrations", "workflows", "runs"):
            cur = await self.db.execute(f"SELECT COUNT(*) AS n FROM {table}")
            out[table] = (await cur.fetchone())["n"]
        return out
