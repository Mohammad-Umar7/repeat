import { useEffect, useRef, useState } from "react";
import { api } from "@shared/api";
import { send } from "@shared/messages";
import type { RecordedEvent, TeachResult, Workflow } from "@shared/types";
import type { Backend } from "../hooks/useBackend";
import { WorkflowCard } from "../components/WorkflowCard";
import { AppTag, Banner, Kbd, Spinner } from "../components/ui";

interface Props {
  b: Backend;
  onLearned: () => void;
}

type Phase = "idle" | "recording" | "generalizing" | "learned" | "failed";

const KIND_ICON: Record<string, string> = { copy: "⎘", paste: "⇩", input: "⌨", click: "⌖", navigate: "→", narration: "🎙" };

function eventLine(e: RecordedEvent) {
  switch (e.kind) {
    case "copy": return <span className="v">“{e.text}”</span>;
    case "paste": return <span className="v"><span className="lab">{e.field_label ? `${e.field_label} ← ` : ""}</span>“{e.text}”</span>;
    case "input": return <span className="v"><span className="lab">{e.field_label}: </span>{e.value}</span>;
    case "click": return <span className="v"><span className="lab">click </span>{e.target_text}</span>;
    case "navigate": return <span className="v"><span className="lab">{e.title || e.url}</span></span>;
    case "narration": return <span className="v">“{e.transcript}”</span>;
  }
}

export function Teach({ b, onLearned }: Props) {
  const [phase, setPhase] = useState<Phase>(b.teach.status === "recording" ? "recording" : "idle");
  const [result, setResult] = useState<TeachResult | null>(null);
  const [learned, setLearned] = useState<Workflow | null>(null);
  const [narrate, setNarrate] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [level, setLevel] = useState(0);
  const recRef = useRef<{ stream: MediaStream; stop: () => void } | null>(null);
  const narrationOk = !!b.health?.narration_enabled;

  useEffect(() => {
    if (b.teach.status === "recording" && phase === "idle") setPhase("recording");
    if (b.teach.status === "idle" && phase === "recording") setPhase("idle");
  }, [b.teach.status, phase]);

  useEffect(() => {
    if (phase !== "recording" || !b.teach.startedAt) return;
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - (b.teach.startedAt || 0)) / 1000)), 500);
    return () => clearInterval(t);
  }, [phase, b.teach.startedAt]);

  // ── narration: 8 s segments, transcribed and time-aligned ────────────
  async function startNarration(startedAt: number) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx = new AudioContext();
      const src = ctx.createMediaStreamSource(stream);
      const an = ctx.createAnalyser();
      an.fftSize = 256;
      src.connect(an);
      const buf = new Uint8Array(an.frequencyBinCount);
      let alive = true;
      const meter = () => {
        if (!alive) return;
        an.getByteTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) sum += (v - 128) ** 2;
        setLevel(Math.min(1, Math.sqrt(sum / buf.length) / 40));
        requestAnimationFrame(meter);
      };
      meter();
      let segStart = Date.now();
      let rec: MediaRecorder | null = null;
      const startSeg = () => {
        rec = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
        const chunks: Blob[] = [];
        segStart = Date.now();
        rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
        rec.onstop = async () => {
          const blob = new Blob(chunks, { type: "audio/webm" });
          const ts = segStart;
          try {
            const text = await api.transcribe(blob);
            if (text) await send({ type: "teach.narration", event: { kind: "narration", ts, url: "", title: "", app: "unknown", transcript: text } });
          } catch (e) {
            setMicError(String((e as Error).message || e));
          }
        };
        rec.start();
      };
      startSeg();
      const timer = setInterval(() => { rec?.stop(); startSeg(); }, 8000);
      recRef.current = {
        stream,
        stop: () => {
          alive = false;
          clearInterval(timer);
          rec?.stop();
          stream.getTracks().forEach((t) => t.stop());
          void ctx.close();
          setLevel(0);
        },
      };
      void startedAt;
    } catch (e) {
      setMicError("Microphone unavailable. Recording continues without narration.");
      setNarrate(false);
    }
  }

  async function start() {
    setResult(null);
    setLearned(null);
    setMicError(null);
    b.setError(null);
    await send({ type: "teach.start" });
    setElapsed(0);
    setPhase("recording");
    if (narrate && narrationOk) void startNarration(Date.now());
  }

  async function done() {
    recRef.current?.stop();
    recRef.current = null;
    setPhase("generalizing");
    // give the last narration segment a moment to land
    await new Promise((r) => setTimeout(r, narrate ? 1200 : 0));
    const t = await send<{ events: RecordedEvent[]; narration: RecordedEvent[] }>({ type: "teach.stop" });
    try {
      const res = await api.teach(t?.events ?? [], t?.narration ?? []);
      handle(res);
    } catch (e) {
      b.setError(String((e as Error).message || e));
      setPhase("failed");
    }
  }

  function handle(res: TeachResult) {
    setResult(res);
    if (res.workflow) {
      setLearned(res.workflow);
      setPhase("learned");
      void b.refreshWorkflows();
    } else if (res.interrupt) {
      setPhase("failed");
    } else {
      setPhase("idle");
    }
  }

  async function decide(d: "retry" | "stop") {
    if (!result) return;
    setPhase("generalizing");
    try {
      handle(await api.decideTeach(result.demonstration_id, d));
    } catch (e) {
      b.setError(String((e as Error).message || e));
      setPhase("failed");
    }
  }

  async function cancel() {
    recRef.current?.stop();
    recRef.current = null;
    await send({ type: "teach.stop" });
    setPhase("idle");
  }

  // Enter starts / finishes when nothing is focused.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (document.activeElement?.tagName || "").toLowerCase();
      if (["input", "textarea", "button"].includes(tag)) return;
      if (e.key === "Enter") {
        e.preventDefault();
        if (phase === "idle") void start();
        else if (phase === "recording") void done();
        else if (phase === "learned") onLearned();
      }
      if (e.key === "Escape" && phase === "recording") { e.preventDefault(); void cancel(); }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, narrate]);

  const events = b.teach.events;
  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

  if (phase === "learned" && learned) {
    return (
      <>
        <Banner tone="ok">
          <b>Learned.</b> This is what REPEAT understood. Rename it if you like; it is saved already.
        </Banner>
        <WorkflowCard workflow={learned} onRename={(n) => { void b.renameWorkflow(learned.id, n); setLearned({ ...learned, name: n }); }} />
        <div className="row">
          <button className="btn primary" onClick={onLearned}>View in workflows <Kbd k="Enter" /></button>
          <button className="btn ghost" onClick={() => setPhase("idle")}>Teach another</button>
        </div>
      </>
    );
  }

  if (phase === "generalizing") {
    return (
      <section className="card">
        <div className="row"><Spinner /><div><b>Generalising your demonstration</b><div className="xs muted">Turning {events.length || "the"} events into a trigger, steps and variables.</div></div></div>
      </section>
    );
  }

  if (phase === "failed") {
    const intr = result?.interrupt;
    return (
      <Banner tone="bad">
        <div><b>Could not learn this yet.</b> {intr?.message || b.error || "Something went wrong while generalising."}</div>
        <div className="row" style={{ gap: 6, marginTop: 8 }}>
          {intr?.options.includes("retry") && <button className="btn primary sm" onClick={() => void decide("retry")}>Retry <Kbd k="Enter" /></button>}
          {intr && <button className="btn sm" onClick={() => void decide("stop")}>Discard</button>}
          {!intr && <button className="btn sm" onClick={() => setPhase("idle")}>Back</button>}
        </div>
      </Banner>
    );
  }

  if (phase === "recording") {
    return (
      <>
        <section className="card" aria-live="polite">
          <div className="row">
            <span className="rec"><span className="dot" aria-hidden="true" /><b>Recording</b><span className="time">{mm}:{ss}</span></span>
            <span className="grow" />
            <span className="badge accent">{events.length} events</span>
          </div>
          <p className="small muted" style={{ margin: "8px 0 0" }}>
            Do the task once in Gmail, Jira and Slack. Copies, pastes, typed fields, button clicks and page changes are captured. Nothing else.
          </p>
          {narrate && (
            <div style={{ marginTop: 10 }}>
              <div className="row xs muted" style={{ marginBottom: 4 }}>🎙 Narration on · say what each value means</div>
              <div className="meter" aria-hidden="true"><i style={{ width: `${Math.round(level * 100)}%` }} /></div>
            </div>
          )}
          {micError && <div className="xs bad" style={{ marginTop: 6 }}>{micError}</div>}
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn primary" onClick={() => void done()} disabled={events.length === 0}>Done <Kbd k="Enter" /></button>
            <button className="btn ghost" onClick={() => void cancel()}>Cancel <Kbd k="Esc" /></button>
          </div>
        </section>
        <section className="card tight">
          <h3>Captured</h3>
          {events.length === 0 ? (
            <div className="xs muted">Waiting for your first action…</div>
          ) : (
            <ul className="evlist">
              {[...events].reverse().slice(0, 40).map((e, i) => (
                <li key={`${e.ts}-${i}`} className="ev fade-in">
                  <AppTag app={e.app} />
                  <span className="k">{KIND_ICON[e.kind]} {e.kind}</span>
                  {eventLine(e)}
                </li>
              ))}
            </ul>
          )}
        </section>
      </>
    );
  }

  return (
    <>
      <section className="card">
        <h2 style={{ marginBottom: 4 }}>Teach a workflow</h2>
        <p className="small muted" style={{ margin: "0 0 12px" }}>
          Show it once. Start recording, then do the real task across your apps. When you press Done, REPEAT turns the demonstration into a trigger, ordered steps and variables you can review.
        </p>
        <ol className="small" style={{ margin: "0 0 12px", paddingLeft: 18, color: "var(--text-2)" }}>
          <li>Open the email that starts the task.</li>
          <li>Create the ticket, post the message, exactly as you normally would.</li>
          <li>Press Done. Review and rename the learned workflow.</li>
        </ol>
        <label className={`check ${narrationOk ? "" : "disabled"}`} title={narrationOk ? "" : "Set OPENAI_API_KEY in backend/.env to enable transcription"}>
          <input type="checkbox" checked={narrate && narrationOk} disabled={!narrationOk} onChange={(e) => setNarrate(e.target.checked)} />
          <span>Narrate while I demonstrate <span className="muted">(optional{narrationOk ? "" : ", needs OPENAI_API_KEY"})</span></span>
        </label>
        <div className="row" style={{ marginTop: 14 }}>
          <button className="btn primary" onClick={() => void start()} disabled={b.online === false}>Start teaching <Kbd k="Enter" /></button>
        </div>
      </section>
      {b.online === false && <Banner tone="bad">Backend offline. Recording still works, but generalising needs the local service.</Banner>}
    </>
  );
}
