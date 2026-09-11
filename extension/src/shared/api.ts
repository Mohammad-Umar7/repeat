// Typed client for the local FastAPI service. Used by the service worker and the panel.

import type {
  EmailContext,
  Health,
  RecordedEvent,
  Run,
  RunDecision,
  RunState,
  TeachResult,
  Workflow,
} from "./types";

export const BACKEND_URL = "http://127.0.0.1:8765";
export const BACKEND_WS = "ws://127.0.0.1:8765/ws";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BACKEND_URL + path, {
      ...init,
      headers: { "content-type": "application/json", ...(init?.headers || {}) },
    });
  } catch {
    throw new ApiError(0, "REPEAT backend is offline. Start it with `python -m repeat` in backend/.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* non-json error body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => req<Health>("/health"),

  workflows: () => req<Workflow[]>("/workflows"),
  workflow: (id: string) => req<Workflow>(`/workflows/${id}`),
  renameWorkflow: (id: string, name: string) =>
    req<Workflow>(`/workflows/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  deleteWorkflow: (id: string) => req<{ ok: boolean }>(`/workflows/${id}`, { method: "DELETE" }),

  teach: (events: RecordedEvent[], narration: RecordedEvent[]) =>
    req<TeachResult>("/demonstrations", json({ events, narration })),
  decideTeach: (demoId: string, decision: "retry" | "stop") =>
    req<TeachResult>(`/demonstrations/${demoId}/decide`, json({ decision })),
  transcribe: async (blob: Blob): Promise<string> => {
    const fd = new FormData();
    fd.append("audio", blob, "narration.webm");
    let res: Response;
    try {
      res = await fetch(BACKEND_URL + "/narration/transcribe", { method: "POST", body: fd });
    } catch {
      throw new ApiError(0, "REPEAT backend is offline.");
    }
    if (!res.ok) throw new ApiError(res.status, (await res.json()).detail ?? res.statusText);
    return ((await res.json()) as { text: string }).text;
  },

  latestEmail: () => req<EmailContext>("/inbox/latest"),
  email: (id: string) => req<EmailContext>(`/inbox/${id}`),

  match: (body: { email?: EmailContext; email_id?: string; workflow_id?: string }) =>
    req<RunState>("/runs/match", json(body)),
  runs: (limit = 20) => req<Run[]>(`/runs?limit=${limit}`),
  latestRun: () => req<RunState>("/runs/latest"),
  run: (id: string) => req<RunState>(`/runs/${id}`),
  decide: (id: string, decision: RunDecision) => req<RunState>(`/runs/${id}/decide`, json({ decision })),
  undo: (id: string, cursor: number) => req<Run>(`/runs/${id}/undo`, json({ cursor })),
  undoOne: (id: string) => req<Run>(`/runs/${id}/undo_one`, { method: "POST" }),

  resetDemo: () => req<{ workflow: Workflow }>("/demo/reset", { method: "POST" }),
  armFault: (app: "jira" | "slack") => req<{ ok: boolean }>("/demo/fault", json({ app })),
};
