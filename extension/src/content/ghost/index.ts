// Ghost overlay: the cursor, the pill, the risk card, and grey ghost fills.
// Everything is inside a closed shadow root and never touches host DOM or styles.
// Commits go through the backend APIs; the page reflects real results afterwards.

import { APP_LABEL, FILL_TARGETS, findTarget, type FillTarget } from "@shared/apps";
import { onMessage, send } from "@shared/messages";
import type { Interrupt, Run, RunDecision, RunState, RunStep } from "@shared/types";
import { CURSOR_SVG, GHOST_CSS } from "./styles";

(() => {
  if ((window as any).__repeatGhost) return;
  (window as any).__repeatGhost = true;

  // ── mount ──────────────────────────────────────────────────────────
  const host = document.createElement("repeat-ghost");
  const shadow = host.attachShadow({ mode: "closed" });
  const style = document.createElement("style");
  style.textContent = GHOST_CSS;
  const layer = document.createElement("div");
  layer.className = "layer";
  layer.setAttribute("aria-live", "polite");
  shadow.append(style, layer);
  const mount = () => document.documentElement.appendChild(host);
  if (document.documentElement) mount();
  else document.addEventListener("DOMContentLoaded", mount, { once: true });

  const cursor = el("div", "cursor");
  cursor.innerHTML = CURSOR_SVG;
  const pill = el("div", "pill");
  pill.setAttribute("role", "status");
  const card = el("div", "card");
  card.setAttribute("role", "dialog");
  card.setAttribute("aria-label", "Risk summary");
  const preview = el("div", "preview");
  preview.setAttribute("role", "dialog");
  preview.setAttribute("aria-label", "Ghost preview");
  const fillsRoot = el("div", "fills");
  layer.append(cursor, fillsRoot, preview, card, pill);

  function el(tag: string, cls: string): HTMLElement {
    const e = document.createElement(tag);
    e.className = cls;
    return e;
  }

  // ── state ──────────────────────────────────────────────────────────
  let run: Run | null = null;
  let interrupt: Interrupt | null = null;
  let visible = false;
  let riskPending: RunDecision | null = null;
  let hideTimer: ReturnType<typeof setTimeout> | null = null;
  let riskTimer: ReturnType<typeof setTimeout> | null = null;
  let fillEls: HTMLElement[] = [];
  let anchor: DOMRect | null = null;
  const mouse = { x: innerWidth / 2, y: innerHeight / 2 };
  addEventListener("mousemove", (e) => ((mouse.x = e.clientX), (mouse.y = e.clientY)), { passive: true });

  // ── helpers ────────────────────────────────────────────────────────
  const kbd = (k: string, lab: string) => `<span class="keys"><kbd>${k}</kbd><span class="kbd-lab">${lab}</span></span>`;
  const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
  const appTag = (app: string) => `<span class="app" aria-hidden="true">${app === "jira" ? "J" : app === "slack" ? "S" : app === "gmail" ? "G" : "•"}</span>`;

  function moveCursor(x: number, y: number): void {
    cursor.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
    cursor.classList.add("on");
  }

  /** Place a floating element below (or above) an anchor rect, clamped into the viewport. */
  function place(node: HTMLElement, rect: DOMRect | null, gap = 10): void {
    node.classList.add("on");
    const w = node.offsetWidth || 320;
    const h = node.offsetHeight || 40;
    let x: number, y: number;
    if (rect) {
      x = rect.left;
      y = rect.bottom + gap;
      if (y + h > innerHeight - 12) y = rect.top - h - gap;
    } else {
      x = mouse.x + 18;
      y = mouse.y + 22;
    }
    x = Math.max(12, Math.min(x, innerWidth - w - 12));
    y = Math.max(12, Math.min(y, innerHeight - h - 12));
    node.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
  }

  function clearFills(fade = false): void {
    const old = fillEls;
    fillEls = [];
    if (fade) {
      old.forEach((f) => f.classList.add("out"));
      setTimeout(() => old.forEach((f) => f.remove()), 200);
    } else old.forEach((f) => f.remove());
  }

  function hideAll(): void {
    visible = false;
    riskPending = null;
    anchor = null;
    if (hideTimer) clearTimeout(hideTimer);
    if (riskTimer) clearTimeout(riskTimer);
    [cursor, pill, card, preview].forEach((n) => n.classList.remove("on"));
    clearFills(true);
  }

  function autoHide(ms: number): void {
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(hideAll, ms);
  }

  function stepFields(step: RunStep): { key: string; label: string; value: string }[] {
    const targets = FILL_TARGETS[step.action] || [];
    const rows = targets.map((t) => ({ key: t.key, label: t.label, value: step.inputs[t.key] ?? "" }));
    if (rows.length) return rows.filter((r) => r.value);
    return Object.entries(step.inputs).map(([k, v]) => ({ key: k, label: k.replace(/_/g, " "), value: v }));
  }

  function fmtSaved(s: number): string {
    const m = Math.floor(s / 60), r = s % 60;
    return m ? `${m}m ${String(r).padStart(2, "0")}s` : `${r}s`;
  }

  // ── renderers ──────────────────────────────────────────────────────
  function renderOffer(): void {
    clearFills();
    preview.classList.remove("on");
    card.classList.remove("on");
    moveCursor(mouse.x + 6, mouse.y + 6);
    pill.innerHTML = `<span class="brand">REPEAT</span><span class="msg">can finish this.</span>
      ${kbd("Tab", "run")}${kbd("⇧Tab", "run all")}${kbd("Esc", "dismiss")}`;
    place(pill, null);
    visible = true;
  }

  function renderRisk(next: RunDecision): void {
    const r = run?.risk;
    riskPending = next;
    pill.classList.remove("on");
    const stat = (n: number, lab: string) => `<div class="stat"><b>${n}</b><span>${lab}</span></div>`;
    card.innerHTML = `
      <div class="row"><h3>Before the first commit</h3><span class="level ${r?.level ?? "low"}">${(r?.level ?? "low").toUpperCase()} RISK</span></div>
      <div class="blast">${esc(r?.blast_radius ?? "")}</div>
      <div class="stats">${stat(r?.records_created ?? 0, "created")}${stat(r?.external_messages ?? 0, "messages")}${stat(r?.records_modified ?? 0, "modified")}${stat(r?.records_deleted ?? 0, "deleted")}</div>
      <div class="actions"><button class="btn" data-act="cancel">Cancel <kbd>Esc</kbd></button>
      <button class="btn primary" data-act="go">${next === "all" ? "Run all" : "Continue"} <kbd>Enter</kbd></button></div>`;
    place(card, null);
    card.querySelector<HTMLButtonElement>('[data-act="go"]')?.focus();
    if (riskTimer) clearTimeout(riskTimer);
    riskTimer = setTimeout(confirmRisk, 2000); // shown for 2 s, then the run proceeds
  }

  function confirmRisk(): void {
    if (!riskPending || !run) return;
    const d = riskPending;
    riskPending = null;
    card.classList.remove("on");
    decide(d);
  }

  async function renderStepPreview(idx: number): Promise<void> {
    if (!run) return;
    const step = run.steps[idx];
    clearFills();
    card.classList.remove("on");
    const targets = (FILL_TARGETS[step.action] || []) as FillTarget[];
    const found = targets.map((t) => ({ t, node: findTarget(t) })).filter((x) => x.node) as { t: FillTarget; node: HTMLElement }[];
    const total = run.steps.length;
    const title = `Step ${idx + 1}/${total} · ${esc(step.title)}`;

    if (found.length) {
      // In-page ghost fill: grey text drawn over the real fields, 60 ms stagger.
      preview.classList.remove("on");
      const first = found[0].node.getBoundingClientRect();
      moveCursor(first.left + 14, first.top + first.height / 2);
      let last: DOMRect = first;
      found.forEach(({ t, node }, i) => {
        const r = node.getBoundingClientRect();
        last = r;
        const f = el("div", "fill");
        f.textContent = step.inputs[t.key] ?? "";
        f.style.cssText = `left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${Math.max(r.height, 30)}px`;
        fillsRoot.appendChild(f);
        fillEls.push(f);
        setTimeout(() => f.classList.add("on"), 60 * i);
      });
      anchor = last;
      pill.innerHTML = `<span class="brand">REPEAT</span><span class="msg">${title}</span>
        ${kbd("Tab", "commit")}${kbd("⇧Tab", "run all")}${kbd("Esc", "stop")}`;
      place(pill, anchor);
    } else {
      // Fallback: ghost preview card in the overlay (DOM not fillable or app not open here).
      moveCursor(mouse.x + 6, mouse.y + 6);
      const rows = stepFields(step);
      preview.innerHTML = `
        <div class="head">${appTag(step.app)}<b>${title}</b><span>· ${APP_LABEL[step.app as keyof typeof APP_LABEL] ?? step.app}</span></div>
        ${rows.map((r) => `<div class="field"><div class="lab">${esc(r.label)}</div><div class="val">${esc(r.value)}</div></div>`).join("")}
        <div class="foot"><span>Preview only. Commits through the ${APP_LABEL[step.app as keyof typeof APP_LABEL] ?? step.app} API.</span>
        ${kbd("Tab", "commit")}${kbd("Esc", "stop")}</div>`;
      place(preview, null);
      preview.querySelectorAll<HTMLElement>(".val").forEach((v, i) => setTimeout(() => v.classList.add("on"), 60 * i));
      fillEls = Array.from(preview.querySelectorAll<HTMLElement>(".val"));
      pill.classList.remove("on");
    }
    visible = true;
  }

  function renderFailure(): void {
    if (!interrupt || !run) return;
    const opts = interrupt.options;
    clearFills(true);
    preview.classList.remove("on");
    card.classList.remove("on");
    const btn = (act: string, k: string, lab: string, primary = false) =>
      opts.includes(act) ? `<button class="btn ${primary ? "primary" : ""}" data-act="${act}">${lab} <kbd>${k}</kbd></button>` : "";
    pill.innerHTML = `<span class="brand">REPEAT</span><span class="msg bad">Paused: ${esc(interrupt.message || "something went wrong.")}</span>
      ${btn("retry", "Enter", "Retry", true)}${btn("skip", "S", "Skip")}${btn("stop", "Esc", "Stop")}`;
    place(pill, anchor);
    visible = true;
  }

  function renderStatus(): void {
    if (!run) return;
    const idx = Math.min(run.current_step, run.steps.length - 1);
    const step = run.steps[idx];
    card.classList.remove("on");
    let html = "";
    let ttl = 0;
    switch (run.status) {
      case "running": {
        const busy = run.steps.find((s) => s.status === "running" || s.status === "verifying") ?? step;
        const verb = busy.status === "verifying" ? "Verifying" : busy.app === "jira" ? "Creating issue" : busy.app === "slack" ? "Posting message" : "Labelling email";
        fillEls.forEach((f) => f.classList.add("commit"));
        html = `<span class="spin" aria-hidden="true"></span><span class="msg">${verb}…</span>`;
        break;
      }
      case "completed": {
        const done = run.steps.filter((s) => s.status === "done").length;
        const key = run.variables["issue_key"];
        html = `<span class="ok">✓ Done</span><span class="msg">${done} steps${key ? ` · ${esc(String(key))}` : ""} · saved ${fmtSaved(run.seconds_saved)}</span>`;
        clearFills(true);
        preview.classList.remove("on");
        ttl = 4000;
        break;
      }
      case "stopped":
        html = `<span class="msg">Stopped. Nothing else was changed.</span>`;
        clearFills(true);
        preview.classList.remove("on");
        ttl = 2500;
        break;
      case "reverted":
      case "partially_reverted": {
        const n = run.steps.filter((s) => s.status === "reverted").length;
        html = `<span class="ok">✓ Reverted</span><span class="msg">${n} step${n === 1 ? "" : "s"} undone and confirmed</span>`;
        ttl = 3000;
        break;
      }
      default:
        return;
    }
    // Snap the committed step's result into the pill when it just landed.
    const justDone = run.steps.find((s) => s.status === "done" && s.result_url && s.id === step?.id);
    if (justDone && run.status === "running") html += ` <span class="ok">✓</span>`;
    pill.innerHTML = `<span class="brand">REPEAT</span>${html}`;
    place(pill, anchor);
    visible = true;
    if (ttl) autoHide(ttl);
  }

  function render(): void {
    if (hideTimer) clearTimeout(hideTimer);
    if (!run) return hideAll();
    if (interrupt?.type === "approval") return renderOffer();
    if (interrupt?.type === "step_gate") return void renderStepPreview(interrupt.step_index ?? run.current_step);
    if (interrupt?.type === "failure") return renderFailure();
    renderStatus();
  }

  // ── actions ────────────────────────────────────────────────────────
  async function decide(d: RunDecision): Promise<void> {
    if (!run) return;
    if (d === "commit" || d === "all") {
      fillEls.forEach((f) => f.classList.add("commit")); // 120 ms settle from grey to solid
      pill.innerHTML = `<span class="brand">REPEAT</span><span class="spin" aria-hidden="true"></span><span class="msg">Committing…</span>`;
      place(pill, anchor);
    }
    const state = await send<RunState>({ type: "run.decide", runId: run.id, decision: d });
    if (state && "run" in state) apply(state);
  }

  function apply(state: RunState): void {
    run = state.run;
    interrupt = state.interrupt;
    render();
  }

  // ── keyboard: Tab accept, Esc dismiss, Enter confirm ───────────────
  addEventListener(
    "keydown",
    (e) => {
      if (!visible || !run) return;
      const handled = (fn: () => void) => {
        e.preventDefault();
        e.stopImmediatePropagation();
        fn();
      };
      if (riskPending) {
        if (e.key === "Enter" || e.key === "Tab") return handled(confirmRisk);
        if (e.key === "Escape") return handled(() => { riskPending = null; card.classList.remove("on"); void decide("dismiss"); });
        return;
      }
      const t = interrupt?.type;
      if (t === "approval") {
        if (e.key === "Tab") return handled(() => renderRisk(e.shiftKey ? "all" : "step"));
        if (e.key === "Escape") return handled(() => decide("dismiss"));
      } else if (t === "step_gate") {
        if (e.key === "Tab") return handled(() => decide(e.shiftKey ? "all" : "commit"));
        if (e.key === "Escape") return handled(() => decide("stop"));
      } else if (t === "failure") {
        const o = interrupt!.options;
        if (e.key === "Enter" && o.includes("retry")) return handled(() => decide("retry"));
        if ((e.key === "s" || e.key === "S") && o.includes("skip")) return handled(() => decide("skip"));
        if (e.key === "Escape") return handled(() => decide("stop"));
      } else if (e.key === "Escape") {
        return handled(hideAll);
      }
    },
    true,
  );

  layer.addEventListener("click", (e) => {
    const b = (e.target as HTMLElement).closest<HTMLElement>("[data-act]");
    if (!b) return;
    const act = b.dataset.act!;
    if (act === "go") return confirmRisk();
    if (act === "cancel") { riskPending = null; card.classList.remove("on"); return void decide("dismiss"); }
    void decide(act as RunDecision);
  });

  // Keep fills aligned if the page scrolls or resizes while previewing.
  const realign = () => { if (interrupt?.type === "step_gate" && visible) void renderStepPreview(interrupt.step_index ?? 0); };
  addEventListener("scroll", realign, { passive: true, capture: true });
  addEventListener("resize", realign, { passive: true });

  // ── messages ───────────────────────────────────────────────────────
  onMessage((msg) => {
    if (msg.type === "ghost.show") {
      apply({ run: msg.run, interrupt: msg.interrupt, finished: false });
      return { ok: true };
    }
    if (msg.type === "ghost.hide") {
      hideAll();
      return { ok: true };
    }
    if (msg.type === "backend.event") {
      const r = msg.event.payload?.run as Run | undefined;
      if (r && run && r.id === run.id && !interrupt) {
        run = r;
        renderStatus();
      }
    }
    return undefined;
  });
})();
