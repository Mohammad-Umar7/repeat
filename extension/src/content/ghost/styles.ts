// Overlay styles. Lives in a closed shadow root: nothing leaks in, nothing leaks out.
// One accent (cyan) reserved for the cursor, ghost text and primary actions.

export const GHOST_CSS = `
:host{all:initial}
*{box-sizing:border-box;margin:0;padding:0}
.layer{position:fixed;inset:0;pointer-events:none;z-index:2147483647;
  font-family:Inter,-apple-system,Segoe UI,Roboto,system-ui,sans-serif;color:#e7e8ea;
  --accent:#22d3ee;--bg:#141518;--bg2:#1b1d21;--line:#2a2c31;--muted:#8b8f98;--ok:#34d399;--bad:#f87171}

/* ghost cursor: glides 200ms ease-out, never bounces */
.cursor{position:fixed;left:0;top:0;width:22px;height:22px;opacity:0;
  transition:transform 200ms cubic-bezier(.2,.7,.2,1),opacity 160ms ease-out;will-change:transform}
.cursor svg{display:block;filter:drop-shadow(0 0 6px rgba(34,211,238,.55))}
.cursor.on{opacity:1}

/* pill: the one-line offer/status */
.pill{position:fixed;left:0;top:0;transform:translate(0,0);pointer-events:auto;
  display:flex;align-items:center;gap:10px;padding:8px 10px 8px 12px;border-radius:12px;
  background:var(--bg);border:1px solid var(--line);box-shadow:0 12px 32px rgba(0,0,0,.45);
  font-size:12.5px;line-height:1.3;white-space:nowrap;opacity:0;
  transition:transform 200ms cubic-bezier(.2,.7,.2,1),opacity 160ms ease-out;max-width:min(520px,calc(100vw - 24px))}
.pill.on{opacity:1}
.pill .msg{overflow:hidden;text-overflow:ellipsis}
.pill .brand{color:var(--accent);font-weight:600;letter-spacing:.06em;font-size:10.5px;margin-right:2px}
.keys{display:inline-flex;align-items:center;gap:6px;margin-left:2px;pointer-events:auto;background:none;border:0;padding:0;cursor:pointer;font:inherit;color:inherit}
.keys:hover kbd{border-color:#4a4e57;color:#fff}
.keys:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:6px}
kbd{font:600 10.5px/1 ui-monospace,Menlo,Consolas,monospace;color:#c9ccd2;background:var(--bg2);
  border:1px solid var(--line);border-bottom-width:2px;border-radius:6px;padding:4px 6px}
.kbd-lab{color:var(--muted);font-size:11px;margin-left:2px}
.btn{pointer-events:auto;cursor:pointer;display:inline-flex;align-items:center;gap:6px;height:26px;
  padding:0 10px;border-radius:8px;border:1px solid var(--line);background:var(--bg2);color:#e7e8ea;
  font:500 12px/1 inherit}
.btn:hover{border-color:#3a3d44}
.btn:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#06181c;font-weight:600}
.btn.primary:hover{filter:brightness(1.06)}
.spin{width:12px;height:12px;border-radius:50%;border:2px solid #3a3d44;border-top-color:var(--accent);
  animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.ok{color:var(--ok);font-weight:600}
.bad{color:var(--bad)}

/* risk summary card, shown once per run */
.card{position:fixed;left:0;top:0;pointer-events:auto;width:360px;max-width:calc(100vw - 24px);
  background:var(--bg);border:1px solid var(--line);border-radius:12px;box-shadow:0 16px 40px rgba(0,0,0,.5);
  padding:12px 14px 12px;opacity:0;transform:translateY(4px);transition:opacity 160ms ease-out,transform 200ms cubic-bezier(.2,.7,.2,1)}
.card.on{opacity:1;transform:translateY(0)}
.card h3{font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-bottom:8px}
.card .blast{font-size:13px;line-height:1.45;color:#e7e8ea;margin-bottom:10px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:10px}
.stat{background:var(--bg2);border:1px solid var(--line);border-radius:8px;padding:6px 8px}
.stat b{display:block;font-size:15px;font-weight:600;font-variant-numeric:tabular-nums}
.stat span{font-size:10px;color:var(--muted);letter-spacing:.02em}
.level{display:inline-block;font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:6px;margin-left:auto}
.level.low{background:rgba(52,211,153,.12);color:var(--ok)}
.level.medium{background:rgba(251,191,36,.14);color:#fbbf24}
.level.high{background:rgba(248,113,113,.14);color:var(--bad)}
.row{display:flex;align-items:center;gap:8px}
.card .actions{display:flex;gap:8px;justify-content:flex-end;margin-top:4px}

/* ghost fill inside a real field: grey, glowing, obviously uncommitted */
.fill{position:fixed;pointer-events:none;overflow:hidden;display:flex;align-items:flex-start;
  padding:6px 8px;font-size:13px;line-height:1.4;color:#a7abb4;white-space:pre-wrap;word-break:break-word;
  border-radius:6px;box-shadow:inset 0 0 0 1px rgba(34,211,238,.45),0 0 14px rgba(34,211,238,.18);
  background:rgba(34,211,238,.05);opacity:0;transition:opacity 180ms ease-out,color 120ms ease-out,box-shadow 120ms ease-out}
.fill.on{opacity:1}
.fill.light{color:#6b7280;background:rgba(34,211,238,.08)}
.fill.commit{color:#e7e8ea;box-shadow:inset 0 0 0 1px rgba(34,211,238,.9),0 0 18px rgba(34,211,238,.35)}
.fill.light.commit{color:#111827}
.fill.out{opacity:0}

/* preview card when the app's DOM is not fillable: same ghost styling, rendered in the overlay */
.preview{position:fixed;pointer-events:auto;width:380px;max-width:calc(100vw - 24px);background:var(--bg);
  border:1px solid var(--line);border-radius:12px;box-shadow:0 16px 40px rgba(0,0,0,.5);padding:10px 12px 12px;
  opacity:0;transform:translateY(4px);transition:opacity 160ms ease-out,transform 200ms cubic-bezier(.2,.7,.2,1)}
.preview.on{opacity:1;transform:translateY(0)}
.preview .head{display:flex;align-items:center;gap:8px;margin-bottom:8px;font-size:12px;color:var(--muted)}
.preview .head b{color:#e7e8ea;font-weight:600}
.app{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:5px;
  font:700 9.5px/1 inherit;letter-spacing:.02em;background:var(--bg2);border:1px solid var(--line);color:#c9ccd2}
.field{margin-top:6px}
.field .lab{font-size:10.5px;color:var(--muted);letter-spacing:.04em;text-transform:uppercase;margin-bottom:3px}
.field .val{font-size:12.5px;line-height:1.4;color:#a7abb4;white-space:pre-wrap;word-break:break-word;max-height:96px;overflow:hidden;
  padding:6px 8px;border-radius:6px;background:rgba(34,211,238,.05);box-shadow:inset 0 0 0 1px rgba(34,211,238,.35);
  opacity:0;transform:translateY(2px);transition:opacity 180ms ease-out,transform 180ms ease-out,color 120ms,box-shadow 120ms}
.field .val.on{opacity:1;transform:none}
.field .val.commit{color:#e7e8ea;box-shadow:inset 0 0 0 1px rgba(34,211,238,.9)}
.preview .foot{display:flex;align-items:center;gap:8px;margin-top:10px;font-size:11.5px;color:var(--muted)}
.preview .foot .keys{margin-left:auto}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
`;

export const CURSOR_SVG = `<svg width="22" height="22" viewBox="0 0 22 22" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
<path d="M4 2.5L4 17.5L8.1 13.6L11 20L13.6 18.9L10.8 12.6L16.5 12.4L4 2.5Z" fill="#22d3ee" stroke="#0b0c0e" stroke-width="1.2" stroke-linejoin="round"/></svg>`;
