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
