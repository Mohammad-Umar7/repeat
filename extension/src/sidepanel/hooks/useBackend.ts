// Single source of truth for the panel: health, workflows, the live run and teach state.
// Live updates arrive over the backend WebSocket; decisions are routed through the
// service worker so the in-page ghost stays in sync with the panel.

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, BACKEND_WS } from "@shared/api";
import { onMessage, send, type TeachStatus } from "@shared/messages";
import type { EmailContext, Health, RecordedEvent, RunDecision, RunState, Workflow } from "@shared/types";

export interface TeachState {
  status: TeachStatus;
  startedAt: number | null;
  events: RecordedEvent[];
  narration: RecordedEvent[];
}

const IDLE: TeachState = { status: "idle", startedAt: null, events: [], narration: [] };

export function useBackend() {
  const [health, setHealth] = useState<Health | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [runState, setRunState] = useState<RunState>({ run: null, interrupt: null, finished: true });
  const [teach, setTeach] = useState<TeachState>(IDLE);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fail = useCallback((e: unknown) => {
    const msg = e instanceof ApiError ? e.message : String((e as Error)?.message ?? e);
    setError(msg);
    if (e instanceof ApiError && e.status === 0) setOnline(false);
  }, []);

  const refreshHealth = useCallback(async () => {
    try {
      const h = await api.health();
      setHealth(h);
      setOnline(true);
      setError(null);
    } catch (e) {
      fail(e);
    }
  }, [fail]);

  const refreshWorkflows = useCallback(async () => {
    try {
      setWorkflows(await api.workflows());
    } catch (e) {
      fail(e);
    }
  }, [fail]);

  const refreshRun = useCallback(
    async (id?: string) => {
      try {
        const s = id ? await api.run(id) : await api.latestRun();
        setRunState(s);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) setRunState({ run: null, interrupt: null, finished: true });
        else fail(e);
      }
    },
    [fail],
  );

  const refreshTeach = useCallback(async () => {
    const { teach: t } = await chrome.storage.session.get("teach");
    setTeach((t as TeachState) || IDLE);
  }, []);

  // initial load
  useEffect(() => {
    void refreshHealth();
    void refreshWorkflows();
    void refreshRun();
    void refreshTeach();
  }, [refreshHealth, refreshWorkflows, refreshRun, refreshTeach]);

  // teach session mirror
  useEffect(() => {
    const onChange = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      if (area === "session" && changes.teach) setTeach((changes.teach.newValue as TeachState) || IDLE);
    };
    chrome.storage.onChanged.addListener(onChange);
    return () => chrome.storage.onChanged.removeListener(onChange);
  }, []);

  // runtime messages from the service worker
  useEffect(() => {
    onMessage((msg) => {
      if (msg.type === "run.state") setRunState(msg.state);
      if (msg.type === "backend.status") setOnline(msg.online);
      return undefined;
    });
  }, []);

  // live events straight from the backend
  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | null = null;
    const connect = () => {
      if (closed) return;
      try {
        ws = new WebSocket(BACKEND_WS);
      } catch {
        retry = setTimeout(connect, 3000);
        return;
      }
      ws.onopen = () => {
        setOnline(true);
        void refreshHealth();
        void refreshWorkflows();
        void refreshRun();
      };
      ws.onmessage = (ev) => {
        let e: { type: string; payload: Record<string, any> };
        try {
          e = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (e.type.startsWith("workflow.") || e.type === "demo.reset") void refreshWorkflows();
        if (e.type === "demo.reset") setRunState({ run: null, interrupt: null, finished: true });
        if (e.type.startsWith("run.") || e.type.startsWith("step.")) {
          const run = e.payload.run;
          if (run) {
            // show the fresh run immediately, then fetch the authoritative interrupt
            setRunState((prev) => ({ ...prev, run, finished: prev.run?.id === run.id ? prev.finished : false }));
            if (refreshTimer.current) clearTimeout(refreshTimer.current);
            refreshTimer.current = setTimeout(() => void refreshRun(run.id), 120);
          }
        }
      };
      ws.onclose = () => {
        setOnline(false);
        retry = setTimeout(connect, 3000);
      };
      ws.onerror = () => ws?.close();
    };
    connect();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      ws?.close();
    };
  }, [refreshHealth, refreshWorkflows, refreshRun]);

  // ── actions ─────────────────────────────────────────────────────────
  const wrap = useCallback(
    async <T,>(label: string, fn: () => Promise<T>): Promise<T | undefined> => {
      setBusy(label);
      setError(null);
      try {
        return await fn();
      } catch (e) {
        fail(e);
        return undefined;
      } finally {
        setBusy(null);
      }
    },
    [fail],
  );

  const decide = useCallback(
    (decision: RunDecision) => {
      const id = runState.run?.id;
      if (!id) return Promise.resolve(undefined);
      return wrap(`decide:${decision}`, async () => {
        const s = await send<RunState | { error: string }>({ type: "run.decide", runId: id, decision });
        if (s && "error" in s) throw new ApiError(500, s.error);
        if (s) setRunState(s as RunState);
        return s as RunState;
      });
    },
    [runState.run?.id, wrap],
  );

  const undoTo = useCallback(
    (cursor: number) => {
      const id = runState.run?.id;
      if (!id) return Promise.resolve(undefined);
      return wrap("undo", async () => {
        const s = await send<RunState | { error: string }>({ type: "run.undo", runId: id, cursor });
        if (s && "error" in s) throw new ApiError(500, s.error);
        if (s) setRunState(s as RunState);
        return s as RunState;
      });
    },
    [runState.run?.id, wrap],
  );

  const undoOne = useCallback(() => {
    const id = runState.run?.id;
    if (!id) return Promise.resolve(undefined);
    return wrap("undo", async () => {
      const s = await send<RunState | { error: string }>({ type: "run.undoOne", runId: id });
      if (s && "error" in s) throw new ApiError(500, s.error);
      if (s) setRunState(s as RunState);
      return s as RunState;
    });
  }, [runState.run?.id, wrap]);

  /** Fallback trigger: fetch the newest inbox email and offer it to the agent. */
  const checkInbox = useCallback(
    (workflowId?: string) =>
      wrap("inbox", async () => {
        const email: EmailContext = await api.latestEmail();
        const s = await send<RunState | { error: string } | null>({ type: "email.opened", email, workflowId });
        if (s && "error" in s) throw new ApiError(500, s.error);
        const state = (s as RunState) ?? (await api.latestRun());
        setRunState(state);
        return state;
      }),
    [wrap],
  );

  const renameWorkflow = useCallback(
    (id: string, name: string) =>
      wrap("rename", async () => {
        const wf = await api.renameWorkflow(id, name);
        setWorkflows((ws) => ws.map((w) => (w.id === id ? wf : w)));
        return wf;
      }),
    [wrap],
  );

  const deleteWorkflow = useCallback(
    (id: string) =>
      wrap("delete", async () => {
        await api.deleteWorkflow(id);
        setWorkflows((ws) => ws.filter((w) => w.id !== id));
      }),
    [wrap],
  );

  const resetDemo = useCallback(
    () =>
      wrap("reset", async () => {
        await api.resetDemo();
        await Promise.all([refreshWorkflows(), refreshHealth()]);
        setRunState({ run: null, interrupt: null, finished: true });
      }),
    [wrap, refreshWorkflows, refreshHealth],
  );

  return {
    health, online, workflows, runState, teach, busy, error,
    setError, setRunState,
    refreshHealth, refreshWorkflows, refreshRun, refreshTeach,
    decide, undoTo, undoOne, checkInbox, renameWorkflow, deleteWorkflow, resetDemo,
  };
}

export type Backend = ReturnType<typeof useBackend>;
