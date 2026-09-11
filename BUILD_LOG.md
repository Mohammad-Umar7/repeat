# BUILD_LOG

All times are local (Asia/Karachi, UTC+5). Net-new build; nothing imported from earlier repos.

## 2026-09-11

- 10:05 Repo initialised. Skeleton: .gitignore, README stub, BUILD_LOG, .env.example.
- 10:20 DOM spike (Jira Cloud create dialog + Slack composer), 30 min box.
  - Jira: summary input is a plain `<input>` (`#summary-field`) and fills fine.
    Description is a ProseMirror editor; setting text needs `execCommand('insertText')`
    which works but is fragile across Jira releases. Modal only exists after the
    user clicks "Create", so the ghost cannot fill before the dialog is open.
  - Slack: composer is a Quill `contenteditable` (`.ql-editor`). `insertText`
    works reliably; DOM is stable.
  - DECISION: hybrid. Ghost fill in-page when the known field is present within
    1.5 s, otherwise render the ghost preview card in the shadow-DOM overlay.
    Commits ALWAYS go through the official APIs, never through the host form.
    This keeps the demo deterministic whether or not the Jira modal is open.
- 10:25 `.env.example` documented (server, demo mode, LLM, Jira, Slack, Gmail, narration).
- 11:40 Backend Phase 1 complete: models, SQLite store, LLM seam (OpenAI structured
  outputs + deterministic mock), prompts v1, Jira/Slack/Gmail live clients, demo sandbox,
  LangGraph teach + run graphs (observe, generalize, match, plan, assess_risk,
  await_approval, execute, verify, record) with `interrupt()` for approval, per-step
  Tab gates and failure gates (retry / skip / stop). Real undo in reverse order with
  verification. 6 end-to-end tests green. HTTP + WebSocket API. `scripts/reset-demo`.
  - DECISION: match/plan/assess_risk run the mock provider when no OPENAI_API_KEY is
    set, so the demo path has zero network dependency. With a key, OpenAI is used.
- 13:30 Extension Phase 1+2: MV3 scaffold (esbuild for worker/content scripts, Vite for
  the panel), recorder content script (copy/paste/input/click/navigate + Gmail open
  detection), service worker hub (teach session, match on email open, ghost steering
  between tabs, WS relay), shadow-DOM ghost overlay (cursor glide 200ms, pill, risk card
  shown once per run for 2 s, ghost fills with 60 ms stagger, 120 ms commit settle,
  preview-card fallback, Tab/⇧Tab/Esc/Enter/S keys), React side panel with exactly
  three views. Verified the full demo path in a chrome-shim harness: approval → step
  previews (Slack draft shows the real DEMO-142 key) → completed + time saved → slider
  undo with verified reverted badges → teach → learned card.
  - FIX: runs left in-flight when the backend restarts are marked stopped on boot
    (graph state is in memory); committed steps stay undoable.
  - FIX: step previews now re-fill templates with variables produced by earlier steps.
- 14:40 Tests: 15 green (run graph, teach graph incl. failure gate + retry, HTTP contract,
  fault injection → paused state). GitHub Actions CI runs pytest, tsc and the extension build.
- 14:50 DECISION (Phase 3, CopilotKit): time-boxed and cut. The panel already has a working
  human-in-the-loop approval via LangGraph `interrupt()` surfaced over HTTP/WS, and
  routing that through CopilotKit's CoAgent runtime would add a Node runtime process and a
  second transport to the demo path without changing what the judges see. Plain React panel
  talking to FastAPI over HTTP + WebSocket ships instead, as the prompt allows.
- 14:55 Ghost overlay verified on a light host page (fake Jira create dialog harness):
  ghost fills over Summary and Description, pill anchored below the field, approval pill,
  risk card. Added adaptive text contrast for light surfaces.
