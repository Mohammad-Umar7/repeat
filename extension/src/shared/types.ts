// Mirrors backend/repeat/models.py. Keep the two in sync by hand; both are small.

export type AppName = "gmail" | "jira" | "slack" | "unknown";

export type EventKind = "copy" | "paste" | "input" | "click" | "navigate" | "narration";

export interface RecordedEvent {
  kind: EventKind;
  ts: number;
  url: string;
  title: string;
  app: AppName;
  text?: string;
  field_label?: string;
  field_name?: string;
  value?: string;
  target_text?: string;
  target_role?: string;
  transcript?: string;
}

export interface Trigger {
  app: "gmail";
  description: string;
  subject_keywords: string[];
  body_keywords: string[];
  sender_pattern?: string | null;
}

export interface Variable {
  name: string;
  source: string;
  description: string;
}

export type StepAction = "jira.create_issue" | "slack.post_message" | "gmail.apply_label";

export interface WorkflowStep {
  id: string;
  action: StepAction;
  app: "jira" | "slack" | "gmail";
  title: string;
  fields: Record<string, string>;
  produces: string[];
}

export interface Workflow {
  id: string;
  name: string;
  created_at: string;
  demonstration_id?: string | null;
  trigger: Trigger;
  variables: Variable[];
  steps: WorkflowStep[];
  estimated_manual_seconds: number;
  run_count: number;
}

export interface EmailContext {
  id: string;
  thread_id?: string | null;
  subject: string;
  sender: string;
  sender_name?: string | null;
  body: string;
  received_at?: string | null;
  labels: string[];
}

export type StepStatus =
  | "planned"
  | "previewing"
  | "running"
  | "verifying"
  | "done"
  | "failed"
  | "skipped"
  | "reverting"
  | "reverted"
  | "revert_failed";

export interface UndoToken {
  kind: "jira_issue" | "slack_message" | "gmail_label";
  ref: Record<string, unknown>;
}

export interface RunStep {
  id: string;
  workflow_step_id: string;
  action: StepAction;
  app: string;
  title: string;
  status: StepStatus;
  inputs: Record<string, string>;
  outputs: Record<string, unknown>;
  verification?: { ok: boolean; detail: string; evidence?: Record<string, unknown> } | null;
  undo_token?: UndoToken | null;
  error?: string | null;
  attempts: number;
  started_at?: string | null;
  finished_at?: string | null;
  reverted_at?: string | null;
  result_url?: string | null;
}

export interface RiskSummary {
  external_messages: number;
  records_created: number;
  records_modified: number;
  records_deleted: number;
  blast_radius: string;
  level: "low" | "medium" | "high";
}

export type RunStatus =
  | "no_match"
  | "matched"
  | "planned"
  | "awaiting_approval"
  | "running"
  | "paused"
  | "completed"
  | "stopped"
  | "failed"
  | "reverted"
  | "partially_reverted";

export interface Run {
  id: string;
  workflow_id: string;
  workflow_name: string;
  created_at: string;
  updated_at: string;
  status: RunStatus;
  email: EmailContext;
  match_confidence: number;
  match_reason: string;
  variables: Record<string, unknown>;
  risk?: RiskSummary | null;
  steps: RunStep[];
  current_step: number;
  pause_reason?: string | null;
  seconds_saved: number;
  undo_cursor: number;
}

export type InterruptType = "approval" | "step_gate" | "failure";

export interface Interrupt {
  type: InterruptType;
  run_id?: string;
  step_index?: number;
  step?: RunStep;
  node?: string;
  message?: string;
  risk?: RiskSummary | null;
  options: string[];
}

export interface RunState {
  run: Run | null;
  interrupt: Interrupt | null;
  finished: boolean;
}

export type RunDecision = "step" | "all" | "dismiss" | "commit" | "retry" | "skip" | "stop";

export interface Health {
  ok: boolean;
  version: string;
  demo_mode: boolean;
  llm: string;
  integrations: Record<"jira" | "slack" | "gmail", "sandbox" | "live">;
  checks: Record<string, { ok: boolean; detail: string }>;
  narration_enabled: boolean;
  slack_channel: string;
  jira_project: string;
  store: Record<string, number>;
}

export interface TeachResult {
  demonstration_id: string;
  workflow: Workflow | null;
  interrupt: Interrupt | null;
  stopped: boolean;
}

export interface BusEvent {
  type: string;
  payload: Record<string, any>;
}
