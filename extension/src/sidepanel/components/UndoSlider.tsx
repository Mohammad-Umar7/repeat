import { useEffect, useState } from "react";
import type { Run } from "@shared/types";
import { Kbd } from "./ui";

interface Props {
  run: Run;
  busy: boolean;
  onUndoTo: (cursor: number) => void;
  onUndoOne: () => void;
}

/** Horizontal timeline slider. Dragging left reverts steps in reverse order through the APIs. */
export function UndoSlider({ run, busy, onUndoTo, onUndoOne }: Props) {
  const committed = run.steps.filter((s) => s.status === "done").length;
  const reverted = run.steps.filter((s) => s.status === "reverted").length;
  const max = committed + reverted; // total positions the slider can occupy
  const [value, setValue] = useState(committed);
  useEffect(() => setValue(committed), [committed]);

  if (max === 0) return null;
  const pct = `${(value / max) * 100}%`;
  const reverting = run.steps.some((s) => s.status === "reverting");

  const release = () => {
    if (value < committed) onUndoTo(value);
    else setValue(committed);
  };

  return (
    <section className="card undo" aria-label="Undo timeline">
      <div className="row">
        <h3 style={{ margin: 0 }}>Undo timeline</h3>
        <span className="grow" />
        {reverting ? (
          <span className="badge warn"><span className="spinner" style={{ width: 10, height: 10 }} /> reverting</span>
        ) : committed === 0 ? (
          <span className="badge warn">all reverted</span>
        ) : (
          <span className="badge ok">{committed} committed</span>
        )}
      </div>
      <div className="track" style={{ ["--pct" as string]: pct }}>
        <input
          type="range"
          min={0}
          max={max}
          step={1}
          value={value}
          disabled={busy || committed === 0}
          onChange={(e) => setValue(Math.min(Number(e.target.value), committed))}
          onMouseUp={release}
          onTouchEnd={release}
          onKeyUp={(e) => { if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) release(); }}
          aria-label={`Committed steps: ${value} of ${max}. Drag left to undo.`}
          aria-valuetext={value === 0 ? "everything reverted" : `${value} steps kept`}
        />
      </div>
      <div className="ticks" aria-hidden="true">
        <div className="tick"><b>0</b>start</div>
        {run.steps.filter((s) => s.status === "done" || s.status === "reverted" || s.status === "reverting").map((s, i) => (
          <div key={s.id} className="tick"><b>{i + 1}</b>{s.app}</div>
        ))}
      </div>
      <div className="row" style={{ marginTop: 12 }}>
        <span className="xs muted">Drag left to revert. Every revert is verified through the API.</span>
        <span className="grow" />
        <button className="btn sm" onClick={onUndoOne} disabled={busy || committed === 0} aria-label="Undo last step">
          Undo last <Kbd k="Ctrl+Z" />
        </button>
      </div>
    </section>
  );
}
