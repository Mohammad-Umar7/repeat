import type { ReactNode } from "react";

export const Kbd = ({ k }: { k: string }) => <kbd aria-label={`shortcut ${k}`}>{k}</kbd>;

export const AppTag = ({ app }: { app: string }) => {
  const letter = app === "jira" ? "J" : app === "slack" ? "S" : app === "gmail" ? "G" : "•";
  const name = app === "jira" ? "Jira" : app === "slack" ? "Slack" : app === "gmail" ? "Gmail" : app;
  return (
    <span className={`app-tag ${app}`} role="img" aria-label={name} title={name}>
      {letter}
    </span>
  );
};

export const Spinner = () => <span className="spinner" role="progressbar" aria-label="working" />;

export const Logo = () => (
  <span className="logo" aria-hidden="true">
    <svg width="12" height="12" viewBox="0 0 22 22" fill="none">
      <path d="M4 2.5L4 17.5L8.1 13.6L11 20L13.6 18.9L10.8 12.6L16.5 12.4L4 2.5Z" fill="#22d3ee" />
    </svg>
  </span>
);

export function EmptyState({ title, body, action, icon }: { title: string; body: string; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="empty fade-in">
      <div className="ico">{icon ?? <Logo />}</div>
      <h2>{title}</h2>
      <p>{body}</p>
      {action}
    </div>
  );
}

export function Banner({ tone = "", children, action }: { tone?: "" | "bad" | "warn" | "ok" | "accent"; children: ReactNode; action?: ReactNode }) {
  return (
    <div className={`banner ${tone}`} role={tone === "bad" ? "alert" : "status"}>
      <div className="grow" style={{ flex: 1, minWidth: 0 }}>{children}</div>
      {action}
    </div>
  );
}

export function fmtDuration(s: number): string {
  s = Math.max(0, Math.round(s));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return m ? `${m}m ${String(r).padStart(2, "0")}s` : `${r}s`;
}

export function relTime(iso: string): string {
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  return `${Math.floor(d / 86400)}d ago`;
}

/** Highlights {variables} inside a template string. */
export function Template({ text }: { text: string }) {
  const parts = text.split(/(\{[a-zA-Z_][a-zA-Z0-9_]*\})/g);
  return (
    <>
      {parts.map((p, i) =>
        /^\{.*\}$/.test(p) ? (
          <span key={i} className="var">{p}</span>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  );
}
