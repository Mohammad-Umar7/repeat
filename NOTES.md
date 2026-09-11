# NOTES

Things noticed while building that are out of scope for the hackathon prompt. Not built.

- **Persistent graph checkpoints.** Interrupts live in LangGraph's `MemorySaver`, so a
  backend restart cannot resume an in-flight run (it is marked stopped on boot; committed
  steps stay undoable). A SQLite checkpointer would make resume survive restarts.
- **Multiple workflows per email.** `/runs/match` tries workflows in order and returns the
  first match. With many workflows, a ranked chooser in the pill would be better.
- **Jira description as rich ADF.** The live client sends plain paragraphs. Bullet lists and
  code blocks from the email body could be preserved.
- **Gmail push trigger.** Live matching happens when the user opens a message (content
  script) or presses "Check inbox". Gmail Pub/Sub watch would let the pill appear before the
  email is opened.
- **Narration alignment.** Segments are attached to the nearest event within 8 s. Word-level
  timestamps from the transcription API would align phrases to individual fields.
- **Per-field ghost commit into host forms.** By decision, commits go through the APIs and
  the ghost never writes into host inputs. A "hand me the draft" mode that leaves the real
  form filled but unsubmitted could suit apps without an API.
- **Undo of external side effects.** Slack notifications already sent to phones cannot be
  unsent; the message is deleted. The risk summary could say so explicitly.
- **Windows reset script** uses PowerShell 5.1 friendly syntax on purpose; a `.cmd` wrapper
  would help people without PowerShell script execution enabled.
