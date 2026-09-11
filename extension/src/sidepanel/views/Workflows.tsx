import { useEffect } from "react";
import type { Backend } from "../hooks/useBackend";
import { WorkflowCard } from "../components/WorkflowCard";
import { Banner, EmptyState, Kbd } from "../components/ui";

interface Props {
  b: Backend;
  onTeach: () => void;
  onRunStarted: () => void;
}

export function Workflows({ b, onTeach, onRunStarted }: Props) {
  const run = async (id: string) => {
    const s = await b.checkInbox(id);
    if (s?.run) onRunStarted();
  };

  // Enter runs the first workflow when nothing else has focus.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (document.activeElement?.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "button") return;
      if (e.key === "Enter" && b.workflows[0] && !b.busy) {
        e.preventDefault();
        void run(b.workflows[0].id);
      }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [b.workflows, b.busy]);

  if (b.online === false) {
    return (
      <Banner tone="bad" action={<button className="btn sm" onClick={() => void b.refreshHealth()}>Retry</button>}>
        <b>Backend offline.</b> Start it with <code className="mono">python -m repeat</code> in <code className="mono">backend/</code>.
      </Banner>
    );
  }

  if (b.workflows.length === 0) {
    return (
      <EmptyState
        title="No workflows yet"
        body="Teach REPEAT once by doing the task yourself. It will offer to repeat it the next time a matching email arrives."
        action={
          <button className="btn primary" onClick={onTeach}>
            Teach a workflow <Kbd k="Enter" />
          </button>
        }
      />
    );
  }

  return (
    <>
      {b.error && <Banner tone="bad" action={<button className="btn sm" onClick={() => b.setError(null)}>Dismiss</button>}>{b.error}</Banner>}
      {b.workflows.map((wf, i) => (
        <WorkflowCard
          key={wf.id}
          workflow={wf}
          primary={i === 0}
          busy={!!b.busy}
          onRename={(n) => void b.renameWorkflow(wf.id, n)}
          onRun={() => void run(wf.id)}
          onDelete={() => void b.deleteWorkflow(wf.id)}
        />
      ))}
      <p className="xs muted" style={{ margin: 0, textAlign: "center" }}>
        Open a matching email in Gmail and the ghost cursor will offer to run it. <br />
        “Check inbox” fetches the newest email instead.
      </p>
    </>
  );
}
