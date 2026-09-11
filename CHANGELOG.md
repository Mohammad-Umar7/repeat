# Changelog

## 0.2.0 — 2026-09-11

Polish round after the first end-to-end build.

- Non-matching emails get a silent `no_match` status. They never bury the last real run in
  the panel, and the ghost stays quiet.
- Ghost overlay shows an error pill with Enter-to-retry when the backend is unreachable,
  instead of hanging on "Committing…".
- `prefers-reduced-motion` respected in the overlay and the panel.
- Cumulative time-saved counter on the Workflows view; Enter on the learned card.
- Ghost fills reposition on scroll without re-rendering; shortcut hints in pills are clickable.
- One log line per agent node transition, keyed by run id. Access log only in DEBUG.
- Backend port baked into the extension at build time (`REPEAT_PORT`).
- Ruff lint + format across the backend, `StrEnum` models, ruff in CI.
- 23 tests: run graph, teach graph, HTTP contract, fault injection, units.
- README: three-minute run guide for Windows and macOS/Linux.

## 0.1.0 — 2026-09-11

First working build: FastAPI + LangGraph backend with SQLite, Jira/Slack/Gmail clients and a
demo sandbox; MV3 extension with recorder, service worker, shadow-DOM ghost overlay and a
React side panel (Workflows, Live Run with undo slider, Teach with optional narration).
