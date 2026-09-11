// Message protocol between content scripts, the service worker and the side panel.
// Every message has a `type`; payloads are typed by the discriminated union below.

import type { EmailContext, Interrupt, RecordedEvent, Run, RunDecision, RunState } from "./types";

export type TeachStatus = "idle" | "recording";

export interface GhostFillField {
  key: string;
  label: string;
  value: string;
}

export type Msg =
  // ── teach ────────────────────────────────────────────────────────────
  | { type: "teach.start" }
  | { type: "teach.stop" }
  | { type: "teach.status" }
  | { type: "teach.event"; event: RecordedEvent }
  | { type: "teach.narration"; event: RecordedEvent }
  | { type: "teach.state"; status: TeachStatus; count: number; startedAt: number | null }
  // ── ghost / runs ─────────────────────────────────────────────────────
  | { type: "email.opened"; email: EmailContext; workflowId?: string }
  | { type: "run.state"; state: RunState }
  | { type: "run.decide"; runId: string; decision: RunDecision }
  | { type: "run.get" }
  | { type: "run.undo"; runId: string; cursor: number }
  | { type: "run.undoOne"; runId: string }
  | { type: "ghost.show"; run: Run; interrupt: Interrupt | null }
  | { type: "ghost.hide" }
  // ── panel ────────────────────────────────────────────────────────────
  | { type: "panel.open" }
  | { type: "panel.setView"; view: "workflows" | "run" | "teach" }
  | { type: "backend.status"; online: boolean }
  | { type: "backend.event"; event: { type: string; payload: Record<string, any> } };

export type MsgOf<T extends Msg["type"]> = Extract<Msg, { type: T }>;

export function send<R = unknown>(msg: Msg): Promise<R> {
  return new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage(msg, (res) => {
        // Reading lastError clears "receiving end does not exist" noise when no listener is open.
        void chrome.runtime.lastError;
        resolve(res as R);
      });
    } catch {
      resolve(undefined as R);
    }
  });
}

export function sendToTab<R = unknown>(tabId: number, msg: Msg): Promise<R | undefined> {
  return new Promise((resolve) => {
    try {
      chrome.tabs.sendMessage(tabId, msg, (res) => {
        void chrome.runtime.lastError;
        resolve(res as R);
      });
    } catch {
      resolve(undefined);
    }
  });
}

export function onMessage(
  handler: (msg: Msg, sender: chrome.runtime.MessageSender) => Promise<unknown> | unknown | void,
): void {
  chrome.runtime.onMessage.addListener((msg: Msg, sender, sendResponse) => {
    let result: unknown;
    try {
      result = handler(msg, sender);
    } catch (e) {
      sendResponse({ error: String(e) });
      return true;
    }
    // Every page with a listener receives every message. A handler that returns undefined
    // is saying "not mine": stay silent so the listener that owns this message answers it.
    // Answering with undefined here would race, and win, against the service worker.
    if (result === undefined) return false;
    if (result instanceof Promise) {
      result.then(sendResponse, (e) => sendResponse({ error: String(e) }));
      return true; // keep the channel open for the async response
    }
    sendResponse(result);
    return true;
  });
}
