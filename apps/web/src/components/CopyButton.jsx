import React, { useEffect, useState } from "react";

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Older browsers or a blocked clipboard API: copy through a hidden text box.
    const box = document.createElement("textarea");
    box.value = text;
    box.setAttribute("readonly", "");
    box.style.position = "fixed";
    box.style.opacity = "0";
    document.body.appendChild(box);
    box.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { ok = false; }
    box.remove();
    return ok;
  }
}

const COPY_ICON = <svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
  <rect x="9" y="9" width="12" height="12" rx="2" /><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1" />
</svg>;
const DONE_ICON = <svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
  <path d="M5 12l5 5 9-10" />
</svg>;

/** One click copies `text`; the button says "Copied" for a moment so it's clear it worked. */
export default function CopyButton({ text, label = "Copy code", className = "" }) {
  const [state, setState] = useState("idle"); // idle | copied | failed
  useEffect(() => {
    if (state === "idle") return undefined;
    const timer = setTimeout(() => setState("idle"), 1800);
    return () => clearTimeout(timer);
  }, [state]);

  return <button type="button" className={`btn btn-sm copy-btn ${className}`.trim()} aria-label={label}
    onClick={async () => setState((await copyText(text)) ? "copied" : "failed")}>
    {state === "copied" ? DONE_ICON : COPY_ICON}
    <span aria-live="polite">{state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : "Copy"}</span>
  </button>;
}
