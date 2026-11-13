import React, { useState } from "react";

export function Skeleton({ rows = 3 }) {
  return <div className="skeleton" role="status" aria-busy="true" aria-label="Loading">{Array.from({ length: rows }, (_, index) => <span key={index} />)}</div>;
}

export function EmptyState({ title, children }) {
  return <div className="state"><p className="state-title">{title}</p>{children && <p>{children}</p>}</div>;
}

export function ErrorState({ message, onRetry }) {
  return <div className="state state-error" role="alert">
    <p className="state-title">This couldn’t load</p>
    <p>{message}</p>
    {onRetry && <button type="button" className="btn" onClick={onRetry}>Try again</button>}
  </div>;
}

/** Renders skeleton, error, or children for a useLoad() result. */
export function Async({ load, rows, children }) {
  if (load.status === "loading" && !load.data) return <Skeleton rows={rows} />;
  if (load.status === "error" && !load.data) return <ErrorState message={load.error} onRetry={load.reload} />;
  return children(load.data);
}

export function SectionHead({ title, hint, count }) {
  return <div className="section-head">
    <div><h2>{title}</h2>{hint && <p>{hint}</p>}</div>
    {count !== undefined && <span className="count">{count}</span>}
  </div>;
}

export function Badge({ tone, children }) {
  return <span className={`badge${tone ? ` badge-${tone}` : ""}`}>{children}</span>;
}

/** A button that asks for a second click inline instead of opening a dialog. Focus starts on Cancel. */
export function ConfirmButton({ children, confirmLabel = "Delete", label, tone = "danger", small = false, onConfirm }) {
  const [armed, setArmed] = useState(false);
  const size = small ? " btn-sm" : "";
  if (!armed) {
    return <button type="button" className={`btn btn-${tone}-quiet${size}`} aria-label={label} onClick={() => setArmed(true)}>{children}</button>;
  }
  return <span className="confirm" role="group" aria-label={label || "Confirm"} onKeyDown={(event) => { if (event.key === "Escape") setArmed(false); }}>
    <button type="button" className={`btn btn-${tone}${size}`} onClick={() => { setArmed(false); onConfirm(); }}>{confirmLabel}</button>
    <button type="button" className={`btn${size}`} autoFocus onClick={() => setArmed(false)}>Cancel</button>
  </span>;
}

export function formatTime(value) {
  try { return new Date(value).toLocaleString(); } catch { return String(value); }
}
