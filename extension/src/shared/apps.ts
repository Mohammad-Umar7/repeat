// Host-app knowledge in one place: which app a URL is, how to read an open Gmail
// message, and where the ghost can fill in Jira and Slack. Content scripts only.

import type { AppName, EmailContext, StepAction } from "./types";

export function detectApp(url: string = location.href): AppName {
  if (/^https:\/\/mail\.google\.com\//.test(url)) return "gmail";
  if (/^https:\/\/[^/]+\.atlassian\.net\//.test(url)) return "jira";
  if (/^https:\/\/([^/]+\.)?slack\.com\//.test(url)) return "slack";
  return "unknown";
}

export const APP_LABEL: Record<AppName, string> = {
  gmail: "Gmail",
  jira: "Jira",
  slack: "Slack",
  unknown: "Browser",
};

// ── Gmail: read the currently open message ─────────────────────────────

function text(el: Element | null): string {
  return (el?.textContent || "").replace(/\s+/g, " ").trim();
}

/** Returns the open Gmail message, or null on list/other views. */
export function readOpenGmailMessage(): EmailContext | null {
  const hash = location.hash; // #inbox/FMfcgz...  or #label/x/FMfc...
  const m = hash.match(/\/([A-Za-z0-9_-]{12,})$/);
  const messageId = m?.[1];
  if (!messageId) return null;
  const subjectEl = document.querySelector("h2[data-thread-perm-id], h2.hP");
  const subject = text(subjectEl);
  if (!subject) return null;
  // Take the last message in the thread as the "new" one.
  const senders = document.querySelectorAll("span.gD[email], span[email][name]");
  const senderEl = senders[senders.length - 1] as HTMLElement | undefined;
  const sender = senderEl?.getAttribute("email") || "";
  const senderName = senderEl?.getAttribute("name") || text(senderEl) || null;
  const bodies = document.querySelectorAll("div.a3s.aiL, div.a3s");
  const bodyEl = bodies[bodies.length - 1];
  const body = (bodyEl?.textContent || "").replace(/\r/g, "").replace(/\n{3,}/g, "\n\n").trim();
  if (!sender && !body) return null;
  return {
    id: messageId,
    thread_id: subjectEl?.getAttribute("data-thread-perm-id") || messageId,
    subject,
    sender,
    sender_name: senderName,
    body,
    received_at: null,
    labels: [],
  };
}

// ── Ghost fill targets ───────────────────────────────────────────────────

export interface FillTarget {
  key: string; // step input key
  label: string; // human label for the preview card
  selectors: string[]; // tried in order; first visible match wins
  kind: "input" | "contenteditable";
}

/** Fields the ghost can fill in-page for each action, in fill order. */
export const FILL_TARGETS: Record<StepAction, FillTarget[]> = {
  "jira.create_issue": [
    {
      key: "summary",
      label: "Summary",
      selectors: ['#summary-field', 'input[name="summary"]', '[data-testid="issue-create.ui.modal.create-form"] input[type="text"]'],
      kind: "input",
    },
    {
      key: "description",
      label: "Description",
      selectors: [
        '[data-testid="issue-create.ui.modal.create-form"] .ProseMirror',
        '#ak-editor-textarea',
        'div[aria-label="Description"] .ProseMirror',
        '.ProseMirror[contenteditable="true"]',
      ],
      kind: "contenteditable",
    },
  ],
  "slack.post_message": [
    {
      key: "text",
      label: "Message",
      selectors: ['[data-qa="message_input"] .ql-editor', '.ql-editor[contenteditable="true"]', 'div[role="textbox"][contenteditable="true"]'],
      kind: "contenteditable",
    },
  ],
  "gmail.apply_label": [],
};

export function isVisible(el: Element): boolean {
  const r = (el as HTMLElement).getBoundingClientRect();
  const cs = getComputedStyle(el as HTMLElement);
  return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none";
}

export function findTarget(t: FillTarget): HTMLElement | null {
  for (const sel of t.selectors) {
    const els = Array.from(document.querySelectorAll<HTMLElement>(sel));
    const hit = els.find(isVisible);
    if (hit) return hit;
  }
  return null;
}

/** Best-effort visible label for a form control, for the recorder. */
export function labelFor(el: HTMLElement): string {
  const aria = el.getAttribute("aria-label");
  if (aria) return aria.trim();
  const labelledBy = el.getAttribute("aria-labelledby");
  if (labelledBy) {
    const t = labelledBy
      .split(/\s+/)
      .map((id) => text(document.getElementById(id)))
      .filter(Boolean)
      .join(" ");
    if (t) return t;
  }
  const id = el.id;
  if (id) {
    const lab = document.querySelector(`label[for="${CSS.escape(id)}"]`);
    if (lab) return text(lab);
  }
  const wrap = el.closest("label");
  if (wrap) return text(wrap);
  const ph = el.getAttribute("placeholder") || el.getAttribute("data-placeholder");
  if (ph) return ph.trim();
  const name = el.getAttribute("name");
  if (name) return name;
  return el.tagName.toLowerCase();
}

export function stepUrlHint(app: string): string {
  switch (app) {
    case "jira":
      return "https://*.atlassian.net";
    case "slack":
      return "https://app.slack.com";
    case "gmail":
      return "https://mail.google.com";
    default:
      return "";
  }
}
