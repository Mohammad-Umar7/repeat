import { useEffect, useState } from "react";
import type { Workflow } from "@shared/types";
import { AppTag, Kbd, Template, fmtDuration } from "./ui";

interface Props {
  workflow: Workflow;
  onRename: (name: string) => void;
  onRun?: () => void;
  onDelete?: () => void;
  busy?: boolean;
  primary?: boolean;
  compact?: boolean;
}

export function WorkflowCard({ workflow: wf, onRename, onRun, onDelete, busy, primary, compact }: Props) {
  const [name, setName] = useState(wf.name);
  const [confirm, setConfirm] = useState(false);
  useEffect(() => setName(wf.name), [wf.name]);

  const commit = () => {
    const n = name.trim();
    if (n && n !== wf.name) onRename(n);
    else setName(wf.name);
  };

  return (
    <article className="card fade-in" aria-label={`Workflow ${wf.name}`}>
      <div className="row" style={{ alignItems: "flex-start" }}>
        <div className="grow">
          <input
            className="wf-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") (e.target as HTMLInputElement).blur();
              if (e.key === "Escape") { setName(wf.name); (e.target as HTMLInputElement).blur(); }
            }}
            aria-label="Workflow name (click to rename)"
            title="Click to rename"
            maxLength={80}
          />
          <div className="row xs muted" style={{ marginTop: 2, gap: 6 }}>
            <span>{wf.steps.length} steps</span>
            <span aria-hidden="true">·</span>
            <span>{wf.variables.length} variables</span>
            <span aria-hidden="true">·</span>
            <span>~{fmtDuration(wf.estimated_manual_seconds)} by hand</span>
            {wf.run_count > 0 && (
              <>
                <span aria-hidden="true">·</span>
                <span>run {wf.run_count}×</span>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="divider" style={{ margin: "12px 0" }} />

      <div className="stack" style={{ gap: 12 }}>
        <section>
          <h3>Trigger</h3>
          <div className="trigger">
            <AppTag app="gmail" />
            <div>
              <div>{wf.trigger.description}</div>
              {!compact && wf.trigger.subject_keywords.length > 0 && (
                <div className="row wrap" style={{ gap: 4, marginTop: 6 }}>
                  {wf.trigger.subject_keywords.slice(0, 6).map((k) => (
                    <span key={k} className="chip">{k}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>

        <section>
          <h3>Steps</h3>
          <ol className="steps">
            {wf.steps.map((s, i) => (
              <li key={s.id} className="step">
                <AppTag app={s.app} />
                <div>
                  <div className="t">{i + 1}. {s.title}</div>
                  {!compact && (
                    <div className="tpl">
                      {Object.entries(s.fields)
                        .filter(([k]) => !["project", "issue_type", "channel"].includes(k))
                        .slice(0, 3)
                        .map(([k, v]) => (
                          <div key={k} className="ellipsis" title={v}>
                            <span className="muted">{k}: </span>
                            <Template text={v} />
                          </div>
                        ))}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </section>

        {!compact && (
          <section>
            <h3>Variables</h3>
            <div className="row wrap" style={{ gap: 6 }}>
              {wf.variables.map((v) => (
                <span key={v.name} className="chip" title={v.description}>
                  <b>{`{${v.name}}`}</b>
                  <span className="src">← {v.source}</span>
                </span>
              ))}
            </div>
          </section>
        )}
      </div>

      {(onRun || onDelete) && (
        <div className="row" style={{ marginTop: 14, gap: 8 }}>
          {onRun && (
            <button className={`btn ${primary ? "primary" : ""}`} onClick={onRun} disabled={busy} aria-label="Check inbox and run">
              Check inbox & run {primary && <Kbd k="Enter" />}
            </button>
          )}
          <span className="grow" />
          {onDelete && !confirm && (
            <button className="btn ghost sm" onClick={() => setConfirm(true)} aria-label="Forget this workflow">
              Forget
            </button>
          )}
          {onDelete && confirm && (
            <span className="row" style={{ gap: 6 }}>
              <span className="xs muted">Forget this workflow?</span>
              <button className="btn danger sm" onClick={onDelete}>Yes, forget</button>
              <button className="btn sm" onClick={() => setConfirm(false)}>Keep</button>
            </span>
          )}
        </div>
      )}
    </article>
  );
}
