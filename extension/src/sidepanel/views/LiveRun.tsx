import { useEffect } from "react";
import type { RunStep } from "@shared/types";
import type { Backend } from "../hooks/useBackend";
import { UndoSlider } from "../components/UndoSlider";
import { AppTag, Banner, EmptyState, Kbd, Spinner, fmtDuration, relTime } from "../components/ui";

interface Props {
  b: Backend;
  onGoWorkflows: () => void;
}

const STATUS_LABEL: Record<string, string> = {
  matched: "Matched",
  planned: "Planned",
  awaiting_approval: "Awaiting approval",
  running: "Running",
  paused: "Paused",
  completed: "Completed",
  stopped: "Stopped",
  failed: "Failed",
  reverted: "Reverted",
  partially_reverted: "Partially reverted",
};

const STATUS_TONE: Record<string, string> = {
  awaiting_approval: "accent",
  running: "accent",
  paused: "bad",
  completed: "ok",
  failed: "bad",
  reverted: "warn",
  partially_reverted: "warn",
};

function NodeGlyph({ s, i }: { s: RunStep; i: number }) {
  switch (s.status) {
    case "done": return <>✓</>;
    case "running":
    case "verifying":
    case "reverting": return <span className="spinner" style={{ width: 10, height: 10 }} />;
    case "failed":
    case "revert_failed": return <>!</>;
    case "skipped": return <>–</>;
    case "reverted": return <>↺</>;
    default: return <>{i + 1}</>;
  }
}

function stepSub(s: RunStep): string {
  switch (s.status) {
    case "planned": return "Planned";
    case "previewing": return "Previewing in grey. Tab to commit.";
    case "running": return s.attempts > 1 ? `Running (attempt ${s.attempts})` : "Running through the API";
    case "verifying": return "Verifying the result exists";
    case "done": return s.verification?.detail ? `Verified: ${s.verification.detail}` : "Done";
    case "failed": return s.error || "Failed";
    case "skipped": return "Skipped by you";
    case "reverting": return "Reverting";
    case "reverted": return s.verification?.detail || "Reverted and confirmed";
    case "revert_failed": return s.error || "Revert failed";
  }
}

export function LiveRun({ b, onGoWorkflows }: Props) {
  const { run, interrupt } = b.runState;

  // Keyboard: Tab accept, Esc dismiss/stop, Enter retry, S skip, Ctrl/Cmd+Z undo one.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!run) return;
      const tag = (document.activeElement?.tagName || "").toLowerCase();
      const typing = tag === "input" || tag === "textarea";
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !typing) {
        e.preventDefault();
        if (!b.busy) void b.undoOne();
        return;
      }
      if (!interrupt || typing) return;
      const t = interrupt.type;
      if (e.key === "Tab") {
        e.preventDefault();
        if (t === "approval") void b.decide(e.shiftKey ? "all" : "step");
        else if (t === "step_gate") void b.decide(e.shiftKey ? "all" : "commit");
      } else if (e.key === "Escape") {
        e.preventDefault();
        void b.decide(t === "approval" ? "dismiss" : "stop");
      } else if (t === "failure") {
        if (e.key === "Enter" && interrupt.options.includes("retry")) { e.preventDefault(); void b.decide("retry"); }
        if (e.key.toLowerCase() === "s" && interrupt.options.includes("skip")) { e.preventDefault(); void b.decide("skip"); }
      }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [run, interrupt, b]);

  if (!run) {
    return (
      <EmptyState
        title="No run yet"
        body="Open an email that matches a learned workflow and the ghost cursor will offer to finish it. Or fetch the newest email from the Workflows tab."
        action={<button className="btn" onClick={onGoWorkflows}>Go to workflows</button>}
      />
    );
  }

  const tone = STATUS_TONE[run.status] ?? "";
  const busy = !!b.busy;
  const committed = run.steps.filter((s) => s.status === "done").length;
  const showUndo = committed > 0 || run.steps.some((s) => s.status === "reverted" || s.status === "reverting");

  return (
    <>
      {b.error && <Banner tone="bad" action={<button className="btn sm" onClick={() => b.setError(null)}>Dismiss</button>}>{b.error}</Banner>}

      <header className="card tight">
        <div className="row">
          <div className="grow">
            <div className="eyebrow">Live run · {relTime(run.created_at)}</div>
            <h2 className="ellipsis" title={run.workflow_name}>{run.workflow_name}</h2>
          </div>
          <span className={`badge ${tone}`}>{STATUS_LABEL[run.status] ?? run.status}</span>
        </div>
        <div className="row small" style={{ marginTop: 8, alignItems: "flex-start" }}>
          <AppTag app="gmail" />
          <div className="grow">
            <div className="ellipsis" title={run.email.subject}><b>{run.email.subject}</b></div>
            <div className="xs muted ellipsis">{run.email.sender_name || run.email.sender} · match {Math.round(run.match_confidence * 100)}% · {run.match_reason}</div>
          </div>
        </div>
      </header>

      {/* ── approval ───────────────────────────────────────────── */}
      {interrupt?.type === "approval" && run.risk && (
        <section className="card fade-in" aria-label="Risk summary">
          <div className="row">
            <h3 style={{ margin: 0 }}>Before the first commit</h3>
            <span className="grow" />
            <span className={`badge ${run.risk.level === "low" ? "ok" : run.risk.level === "medium" ? "warn" : "bad"}`}>{run.risk.level} risk</span>
          </div>
          <p style={{ margin: "8px 0 0" }}>{run.risk.blast_radius}</p>
          <div className="risk-stats">
            <div className="s"><b>{run.risk.records_created}</b><span>created</span></div>
            <div className="s"><b>{run.risk.external_messages}</b><span>messages</span></div>
            <div className="s"><b>{run.risk.records_modified}</b><span>modified</span></div>
            <div className="s"><b>{run.risk.records_deleted}</b><span>deleted</span></div>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button className="btn primary" disabled={busy} onClick={() => void b.decide("step")}>Step by step <Kbd k="Tab" /></button>
            <button className="btn" disabled={busy} onClick={() => void b.decide("all")}>Run all <Kbd k="⇧Tab" /></button>
            <span className="grow" />
            <button className="btn ghost" disabled={busy} onClick={() => void b.decide("dismiss")}>Dismiss <Kbd k="Esc" /></button>
          </div>
        </section>
      )}

      {/* ── paused ─────────────────────────────────────────────── */}
      {interrupt?.type === "failure" && (
        <Banner tone="bad">
          <div><b>Paused.</b> {interrupt.message}</div>
          <div className="row" style={{ gap: 6, marginTop: 8 }}>
            {interrupt.options.includes("retry") && <button className="btn primary sm" disabled={busy} onClick={() => void b.decide("retry")}>Retry <Kbd k="Enter" /></button>}
            {interrupt.options.includes("skip") && <button className="btn sm" disabled={busy} onClick={() => void b.decide("skip")}>Skip <Kbd k="S" /></button>}
            <button className="btn sm danger" disabled={busy} onClick={() => void b.decide("stop")}>Stop <Kbd k="Esc" /></button>
          </div>
        </Banner>
      )}
      {run.status === "paused" && !interrupt && run.pause_reason && (
        <Banner tone="bad" action={<button className="btn sm" onClick={() => void b.refreshRun(run.id)}>Refresh</button>}>
          <b>Paused.</b> {run.pause_reason}
        </Banner>
      )}

      {/* ── completed ──────────────────────────────────────────── */}
      {run.status === "completed" && (
        <section className="card fade-in">
          <div className="row">
            <div className="grow">
              <h3>Time saved</h3>
              <div className="saved"><b className="ok">{fmtDuration(run.seconds_saved)}</b><span className="muted small">vs. doing it by hand</span></div>
            </div>
            <span className="badge ok">✓ all steps verified</span>
          </div>
        </section>
      )}

      {/* ── timeline ───────────────────────────────────────────── */}
      <section className="card" aria-label="Timeline">
        <div className="row" style={{ marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}>Timeline</h3>
          <span className="grow" />
          {interrupt?.type === "step_gate" && (
            <span className="row" style={{ gap: 6 }}>
              <button className="btn primary sm" disabled={busy} onClick={() => void b.decide("commit")}>Commit step <Kbd k="Tab" /></button>
              <button className="btn sm" disabled={busy} onClick={() => void b.decide("all")}>Run all</button>
              <button className="btn ghost sm" disabled={busy} onClick={() => void b.decide("stop")}>Stop <Kbd k="Esc" /></button>
            </span>
          )}
        </div>
        <ol className="timeline">
          {run.steps.map((s, i) => (
            <li key={s.id} className={`tl ${s.status}`}>
              <div className="node" aria-hidden="true"><NodeGlyph s={s} i={i} /></div>
              <div className="body">
                <div className="title"><AppTag app={s.app} /><span className="ellipsis">{s.title}</span>
                  {s.status === "reverted" && <span className="badge warn">reverted</span>}
                  {s.status === "skipped" && <span className="badge">skipped</span>}
                </div>
                <div className={`sub ${s.status === "failed" || s.status === "revert_failed" ? "bad" : ""}`}>{stepSub(s)}</div>
                {s.status === "previewing" && (
                  <div className="preview" aria-label="Ghost preview">
                    {Object.entries(s.inputs).filter(([k]) => !["project", "issue_type"].includes(k)).map(([k, v]) => (
                      <div key={k}><span className="k">{k}</span>{v}</div>
                    ))}
                  </div>
                )}
                {(s.status === "done" || s.status === "reverted") && (s.outputs.issue_key || s.outputs.slack_ts || s.outputs.label) ? (
                  <div className="result">
                    {s.outputs.issue_key ? <code>{String(s.outputs.issue_key)}</code> : null}
                    {s.outputs.slack_ts ? <code>ts {String(s.outputs.slack_ts).slice(0, 10)}</code> : null}
                    {s.outputs.label ? <code>{String(s.outputs.label)}</code> : null}
                    {s.result_url && s.status === "done" && <a href={s.result_url} target="_blank" rel="noreferrer">open ↗</a>}
                    {s.status === "reverted" && <span className="muted">deleted · confirmed</span>}
                  </div>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      </section>

      {showUndo && <UndoSlider run={run} busy={busy} onUndoTo={(c) => void b.undoTo(c)} onUndoOne={() => void b.undoOne()} />}

      {(run.status === "stopped") && (
        <Banner>
          <b>Stopped.</b> {run.pause_reason || "Nothing else was changed."}
          {committed > 0 && " Committed steps can still be undone above."}
        </Banner>
      )}
      {(run.status === "running" && !interrupt) && (
        <div className="row small muted"><Spinner /> Working through the API. Every step is verified before the next.</div>
      )}
    </>
  );
}
