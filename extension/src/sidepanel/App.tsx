import { useEffect, useState } from "react";
import { useBackend } from "./hooks/useBackend";
import { Workflows } from "./views/Workflows";
import { LiveRun } from "./views/LiveRun";
import { Teach } from "./views/Teach";
import { Logo } from "./components/ui";

type View = "workflows" | "run" | "teach";

export function App() {
  const b = useBackend();
  const [view, setView] = useState<View>(() => {
    try {
      return (localStorage.getItem("repeat.view") as View) || "workflows";
    } catch {
      return "workflows";
    }
  });
  const go = (v: View) => {
    setView(v);
    try {
      localStorage.setItem("repeat.view", v);
    } catch {
      /* private mode */
    }
  };

  // A run that needs a decision pulls the panel to the Live Run view.
  const interruptType = b.runState.interrupt?.type;
  const runStatus = b.runState.run?.status;
  useEffect(() => {
    if (interruptType || runStatus === "running") setView((v) => (v === "teach" && b.teach.status === "recording" ? v : "run"));
  }, [interruptType, runStatus, b.teach.status]);

  const live = !!b.runState.interrupt || runStatus === "running" || runStatus === "paused";
  const recording = b.teach.status === "recording";

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <Logo />
          <b>REPEAT</b>
          <span
            className={`status-dot ${b.online === null ? "" : b.online ? "on" : "off"}`}
            title={b.online ? `Backend online${b.health?.demo_mode ? " · demo mode" : ""}` : b.online === false ? "Backend offline" : "Connecting"}
            role="img"
            aria-label={b.online ? "backend online" : b.online === false ? "backend offline" : "connecting"}
          />
        </div>
      </header>
      <nav className="top" style={{ paddingTop: 0 }} aria-label="Views">
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={view === "workflows"} className={`tab ${view === "workflows" ? "active" : ""}`} onClick={() => go("workflows")}>
            Workflows {b.workflows.length > 0 && <span className="n">{b.workflows.length}</span>}
          </button>
          <button role="tab" aria-selected={view === "run"} className={`tab ${view === "run" ? "active" : ""}`} onClick={() => go("run")}>
            Live Run {live && <span className="n live">●</span>}
          </button>
          <button role="tab" aria-selected={view === "teach"} className={`tab ${view === "teach" ? "active" : ""}`} onClick={() => go("teach")}>
            Teach {recording && <span className="n" style={{ background: "var(--bad-soft)", color: "var(--bad)" }}>REC</span>}
          </button>
        </div>
      </nav>

      <main className="main" role="tabpanel">
        {view === "workflows" && <Workflows b={b} onTeach={() => go("teach")} onRunStarted={() => go("run")} />}
        {view === "run" && <LiveRun b={b} onGoWorkflows={() => go("workflows")} />}
        {view === "teach" && <Teach b={b} onLearned={() => go("workflows")} />}
      </main>

      <footer className="foot">
        {b.health ? (
          <>
            <span title="Where commits go">{b.health.integrations.jira === "live" ? "Jira live" : "Jira sandbox"} · {b.health.integrations.slack === "live" ? "Slack live" : "Slack sandbox"} · {b.health.integrations.gmail === "live" ? "Gmail live" : "Gmail sandbox"}</span>
            <span className="spacer" />
            {b.health.demo_mode && (
              <button className="btn ghost sm" onClick={() => void b.resetDemo()} disabled={!!b.busy} title="Restore the seeded workflow and clear runs">
                Reset demo
              </button>
            )}
            <span className="mono">v{b.health.version}</span>
          </>
        ) : (
          <span>{b.online === false ? "Backend offline" : "Connecting to local backend…"}</span>
        )}
      </footer>
    </div>
  );
}
