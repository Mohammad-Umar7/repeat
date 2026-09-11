// Teach-mode recorder. Captures a clean semantic event stream (not a screen recording)
// while the panel says we are recording, and shows a small in-page recording badge.

import { detectApp, labelFor, readOpenGmailMessage } from "@shared/apps";
import { onMessage, send } from "@shared/messages";
import type { RecordedEvent, EventKind } from "@shared/types";

(() => {
  if ((window as any).__repeatRecorder) return;
  (window as any).__repeatRecorder = true;

  let recording = false;
  const app = detectApp();

  // ── badge (shadow DOM so host styles never leak either way) ──────────
  const host = document.createElement("repeat-recorder");
  host.style.cssText = "position:fixed;top:12px;right:12px;z-index:2147483646;pointer-events:none;";
  const shadow = host.attachShadow({ mode: "closed" });
  shadow.innerHTML = `
    <style>
      :host{all:initial}
      .badge{display:none;align-items:center;gap:8px;padding:6px 10px 6px 8px;border-radius:8px;
        background:#141518;border:1px solid #2a2c31;color:#e7e8ea;font:500 12px/1 Inter,system-ui,sans-serif;
        box-shadow:0 8px 24px rgba(0,0,0,.4);letter-spacing:.01em}
      .badge.on{display:inline-flex}
      .dot{width:8px;height:8px;border-radius:50%;background:#ef4444;box-shadow:0 0 0 3px rgba(239,68,68,.25)}
      .n{color:#8b8f98;font-variant-numeric:tabular-nums}
    </style>
    <div class="badge" role="status" aria-live="polite"><span class="dot"></span><span>Recording</span><span class="n">0</span></div>`;
  const badge = shadow.querySelector(".badge") as HTMLElement;
  const counter = shadow.querySelector(".n") as HTMLElement;
  const mount = () => document.documentElement.appendChild(host);
  if (document.documentElement) mount();
  else document.addEventListener("DOMContentLoaded", mount, { once: true });

  function setRecording(on: boolean, count = 0): void {
    recording = on;
    badge.classList.toggle("on", on);
    counter.textContent = String(count);
  }

  // ── emit ─────────────────────────────────────────────────────────────
  function base(kind: EventKind): RecordedEvent {
    return { kind, ts: Date.now(), url: location.href, title: document.title, app };
  }

  async function emit(ev: RecordedEvent): Promise<void> {
    if (!recording) return;
    const res = await send<{ ok: boolean; count?: number }>({ type: "teach.event", event: ev });
    if (res?.count != null) counter.textContent = String(res.count);
  }

  // ── listeners ────────────────────────────────────────────────────────
  document.addEventListener(
    "copy",
    () => {
      const text = String(getSelection() || "").trim();
      if (!text) return;
      void emit({ ...base("copy"), text: text.slice(0, 2000) });
    },
    true,
  );

  document.addEventListener(
    "paste",
    (e) => {
      const text = (e.clipboardData?.getData("text/plain") || "").trim();
      const target = e.target as HTMLElement | null;
      void emit({
        ...base("paste"),
        text: text.slice(0, 2000),
        field_label: target ? labelFor(target) : undefined,
      });
    },
    true,
  );

  const debounce = new Map<HTMLElement, ReturnType<typeof setTimeout>>();
  document.addEventListener(
    "input",
    (e) => {
      const el = e.target as HTMLElement | null;
      if (!el || !recording) return;
      const tag = el.tagName;
      const isField = tag === "INPUT" || tag === "TEXTAREA" || el.isContentEditable;
      if (!isField) return;
      if ((el as HTMLInputElement).type === "password") return;
      const existing = debounce.get(el);
      if (existing) clearTimeout(existing);
      debounce.set(
        el,
        setTimeout(() => {
          debounce.delete(el);
          const value = el.isContentEditable ? (el.innerText || "").trim() : (el as HTMLInputElement).value;
          if (!value) return;
          void emit({
            ...base("input"),
            field_label: labelFor(el),
            field_name: el.getAttribute("name") || el.id || undefined,
            value: value.slice(0, 2000),
          });
        }, 700),
      );
    },
    true,
  );

  document.addEventListener(
    "click",
    (e) => {
      if (!recording) return;
      const el = (e.target as HTMLElement | null)?.closest<HTMLElement>(
        'button,[role="button"],a[href],input[type="submit"],[role="menuitem"],[role="tab"]',
      );
      if (!el) return;
      const label = (el.getAttribute("aria-label") || el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
      if (!label) return;
      void emit({ ...base("click"), target_text: label.slice(0, 120), target_role: el.getAttribute("role") || el.tagName.toLowerCase() });
    },
    true,
  );

  // Navigation: SPA-aware via URL polling (Gmail/Jira/Slack are all client-routed).
  let lastUrl = location.href;
  let lastGmailId: string | null = null;
  setInterval(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      void emit({ ...base("navigate") });
    }
    if (app === "gmail") {
      // Ghost trigger: a message was opened.
      const email = readOpenGmailMessage();
      const id = email?.id ?? null;
      if (id && id !== lastGmailId) {
        lastGmailId = id;
        void send({ type: "email.opened", email: email! });
      } else if (!id) {
        lastGmailId = null;
      }
    }
  }, 500);

  // ── state sync ───────────────────────────────────────────────────────
  onMessage((msg) => {
    if (msg.type === "teach.state") setRecording(msg.status === "recording", msg.count);
  });
  void send<{ status: string; count: number }>({ type: "teach.status" }).then((s) => {
    if (s) setRecording(s.status === "recording", s.count);
  });
})();
