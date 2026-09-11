# Demo checklist (30 seconds before you go on)

1. `./scripts/reset-demo.sh` (or `.\scripts\reset-demo.ps1`). Expect: `Demo reset over HTTP: Bug email to Jira and Slack {'demonstrations': 1, 'workflows': 1, 'runs': 0}`.
2. Side panel open on **Workflows**. Footer reads `Jira sandbox · Slack sandbox · Gmail sandbox` (or `live` where configured) and the status dot is green.
3. Tabs open, left to right: Gmail (a bug-report email in the inbox), Jira board, Slack `#product-updates`.
4. Mouse near the middle of the Gmail message so the ghost pill appears where the camera looks.
5. Keys you will press, in order: **Tab** (offer) → wait 2 s (risk card) → **Tab** (commit Jira) → **Tab** (commit Slack) → **Tab** (label) → drag slider to 0 → **Teach** → **Enter** → a few clicks → **Esc**.
6. If anything pauses: read the one-line reason on the pill, press **Enter** to retry. The paused state is a feature; say so.
7. To show the paused state on purpose, before step 5 run:
   `curl -X POST http://127.0.0.1:8765/demo/fault -H 'content-type: application/json' -d '{"app":"jira"}'`
8. After the run, `./scripts/reset-demo.sh` again. Under a second.
