# Changelog

## 0.2.1 — 2026-09-11

Four real bugs found by driving the built extension in a live browser rather than a harness.
Teach mode and the ghost cursor did not work at all outside the harness before this.

- **Message listeners answered messages they did not handle.** Every extension page receives
  every runtime message, and the wrapper replied `undefined` even when the handler declined.
  That empty reply raced and beat the service worker's real one, so the recorder's
  "am I recording?" query came back empty and a tab opened after Start never recorded.
  Handlers that decline now stay silent, and the recorder retries for an idle worker.
- **Ghost steering never matched apex app domains.** The manifest injects on
  `https://*.slack.com/*`, which Chrome expands to include `slack.com` itself, but the
  steering regex demanded a subdomain, so the ghost could not reach that tab.
- **Side-panel messages carried the panel's own tab id**, sending the ghost into a window
  nobody looks at. Only content scripts on host pages now count as the user's location.
- **A run started from the panel had no tab to steer to** and showed nothing. It now falls
  back to the active page the content scripts run on.
- The sandbox adopts emails opened in a real Gmail tab, so labelling and undo work when the
  backend is sandboxed but Gmail is real.
- The service worker logs its ghost steering decision.

Note for development: Chrome keeps a registered service worker across launches when the
profile persists, so after `npm run build` you must reload the extension in
`chrome://extensions` or you will keep running stale worker code.

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
