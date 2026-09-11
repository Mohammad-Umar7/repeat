// Service worker: message hub between the panel, the content scripts and the backend.
// Holds teach-session state in chrome.storage.session and steers the ghost between tabs.

import { api, ApiError, BACKEND_WS } from "@shared/api";
import { onMessage, sendToTab, type Msg, type TeachStatus } from "@shared/messages";
import type { EmailContext, RecordedEvent, Run, RunState } from "@shared/types";

// ── panel behaviour ──────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
});
void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });

// ── teach session ────────────────────────────────────────────────────────

interface TeachSession {
  status: TeachStatus;
  startedAt: number | null;
  events: RecordedEvent[];
  narration: RecordedEvent[];
}

const EMPTY: TeachSession = { status: "idle", startedAt: null, events: [], narration: [] };

async function getTeach(): Promise<TeachSession> {
  const { teach } = await chrome.storage.session.get("teach");
  return (teach as TeachSession) || EMPTY;
}

async function setTeach(t: TeachSession): Promise<void> {
  await chrome.storage.session.set({ teach: t });
  const state: Msg = { type: "teach.state", status: t.status, count: t.events.length, startedAt: t.startedAt };
  broadcast(state);
}

function broadcast(msg: Msg): void {
  chrome.runtime.sendMessage(msg, () => void chrome.runtime.lastError);
  chrome.tabs.query({}, (tabs) => {
    for (const t of tabs) if (t.id != null) void sendToTab(t.id, msg);
  });
}

// ── run steering ─────────────────────────────────────────────────────────

let ghostTabId: number | null = null;

const APP_URL_MATCH: Record<string, RegExp> = {
  jira: /^https:\/\/[^/]+\.atlassian\.net\//,
  slack: /^https:\/\/app\.slack\.com\//,
  gmail: /^https:\/\/mail\.google\.com\//,
};

/** Find an open tab for the app the next step targets; fall back to the current ghost tab. */
async function tabForStep(run: Run, senderTab?: number | null): Promise<number | null> {
  const step = run.steps[run.current_step];
  const app = step?.app;
  if (app && APP_URL_MATCH[app]) {
    const tabs = await chrome.tabs.query({});
    const hit = tabs.find((t) => t.url && APP_URL_MATCH[app].test(t.url));
    if (hit?.id != null) {
      if (!hit.active) await chrome.tabs.update(hit.id, { active: true });
      if (hit.windowId != null) await chrome.windows.update(hit.windowId, { focused: true });
      return hit.id;
    }
  }
  return senderTab ?? ghostTabId;
}

async function pushGhost(state: RunState, senderTab?: number | null): Promise<void> {
  broadcast({ type: "run.state", state });
  if (!state.run) return;
  const terminal = ["completed", "stopped", "failed", "reverted", "partially_reverted"].includes(state.run.status);
  const target = terminal ? senderTab ?? ghostTabId : await tabForStep(state.run, senderTab);
  if (target == null) return;
  ghostTabId = target;
  await sendToTab(target, { type: "ghost.show", run: state.run, interrupt: state.interrupt });
}

async function onEmailOpened(email: EmailContext, tabId: number | null, workflowId?: string): Promise<RunState | { error: string } | null> {
  try {
    const state = await api.match({ email, workflow_id: workflowId });
    if (!state.run || state.run.status === "no_match") return state; // no match: ghost stays silent
    await pushGhost(state, tabId);
    return state;
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null; // no workflows learned yet
    broadcast({ type: "backend.status", online: !(e instanceof ApiError && e.status === 0) });
    return { error: e instanceof Error ? e.message : String(e) };
  }
}

// ── backend live events ─────────────────────────────────────────────────

let ws: WebSocket | null = null;
let wsTimer: ReturnType<typeof setTimeout> | null = null;

function connectWs(): void {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  try {
    ws = new WebSocket(BACKEND_WS);
  } catch {
    scheduleReconnect();
    return;
  }
  ws.onopen = () => broadcast({ type: "backend.status", online: true });
  ws.onmessage = (ev) => {
    let event: { type: string; payload: Record<string, any> };
    try {
      event = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (event.type === "ping" || event.type === "hello") return;
    broadcast({ type: "backend.event", event });
  };
  ws.onclose = () => {
    broadcast({ type: "backend.status", online: false });
    scheduleReconnect();
  };
  ws.onerror = () => ws?.close();
}

function scheduleReconnect(): void {
  if (wsTimer) clearTimeout(wsTimer);
  wsTimer = setTimeout(connectWs, 3000);
}

connectWs();
chrome.alarms.create("repeat-keepalive", { periodInMinutes: 0.4 });
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === "repeat-keepalive") connectWs();
});

// ── messages ─────────────────────────────────────────────────────────────

onMessage(async (msg, sender) => {
  const tabId = sender.tab?.id ?? null;
  switch (msg.type) {
    case "teach.start": {
      await setTeach({ status: "recording", startedAt: Date.now(), events: [], narration: [] });
      return { ok: true };
    }
    case "teach.stop": {
      const t = await getTeach();
      await setTeach({ ...EMPTY });
      return { events: t.events, narration: t.narration, startedAt: t.startedAt };
    }
    case "teach.status": {
      const t = await getTeach();
      return { status: t.status, count: t.events.length, startedAt: t.startedAt };
    }
    case "teach.event": {
      const t = await getTeach();
      if (t.status !== "recording") return { ok: false };
      t.events.push(msg.event);
      await setTeach(t);
      return { ok: true, count: t.events.length };
    }
    case "teach.narration": {
      const t = await getTeach();
      if (t.status !== "recording") return { ok: false };
      t.narration.push(msg.event);
      await setTeach(t);
      return { ok: true };
    }
    case "email.opened": {
      return await onEmailOpened(msg.email, tabId, (msg as { workflowId?: string }).workflowId);
    }
    case "run.get": {
      try {
        return await api.latestRun();
      } catch {
        return { run: null, interrupt: null, finished: true } satisfies RunState;
      }
    }
    case "run.decide": {
      const state = await api.decide(msg.runId, msg.decision);
      await pushGhost(state, tabId);
      return state;
    }
    case "run.undo": {
      const run = await api.undo(msg.runId, msg.cursor);
      const state: RunState = { run, interrupt: null, finished: true };
      await pushGhost(state, tabId);
      return state;
    }
    case "run.undoOne": {
      const run = await api.undoOne(msg.runId);
      const state: RunState = { run, interrupt: null, finished: true };
      await pushGhost(state, tabId);
      return state;
    }
    case "panel.open": {
      const win = sender.tab?.windowId ?? (await chrome.windows.getCurrent()).id;
      if (win != null) await chrome.sidePanel.open({ windowId: win });
      return { ok: true };
    }
    default:
      return undefined;
  }
});
