import React, { useState } from "react";
import { request } from "../api.js";

const ACTION_LABEL = {
  list_files: "List files", read_file: "Read a file", search_files: "Search files", write_file: "Write a file",
  web_lookup: "Look up online", weather: "Weather", web_search: "Search the web", open_page: "Open a web page",
};

// What each status means, in the user's words. Every value comes from the server.
const STATUS = {
  awaiting_approval: { text: "Waiting for your approval", tone: "pending" },
  completed: { text: "Done", tone: "done" },
  auto: { text: "Done automatically (Do-it mode)", tone: "done" },
  undone: { text: "Undone", tone: "stopped" },
  denied: { text: "Not allowed by your permissions or the safety policy", tone: "stopped" },
  rejected: { text: "Not a valid request", tone: "stopped" },
  failed: { text: "Failed", tone: "stopped" },
  flagged: { text: "Withheld: the file looks like a prompt-injection attempt", tone: "stopped" },
  denied_by_user: { text: "You denied this. Nothing was changed.", tone: "stopped" },
  expired: { text: "Expired without a decision. Nothing was changed.", tone: "stopped" },
  approved: { text: "Approved", tone: "done" },
};

// Map an approval's current server status onto a card status.
export const fromApproval = { pending: "awaiting_approval", approved: "approved", denied: "denied_by_user", expired: "expired" };

/** One action the assistant asked for, with its real outcome. */
export default function ToolCard({ tool, approvalStatus, notify, onDecided, onRun }) {
  const [local, setLocal] = useState(null); // { status, detail, undoId } after an action taken here
  const [busy, setBusy] = useState(false);
  // An auto-run card already shows its real outcome; the approval record would only say "approved".
  const saved = tool.auto ? "auto" : tool.status;
  const status = local?.status || (!tool.auto && approvalStatus && fromApproval[approvalStatus]) || saved;
  const shown = STATUS[status] || { text: status, tone: "stopped" };
  const undoId = local?.undoId || tool.undo_id;
  const canUndo = tool.action === "write_file" && undoId && ["auto", "completed"].includes(status);
  // A web page the assistant saved can open straight in the preview.
  const canRun = onRun && tool.action === "write_file" && /\.(html?|svg|py)$/i.test(tool.target || "")
    && ["auto", "completed", "approved"].includes(status);

  async function run() {
    try {
      const path = tool.target.split("/").map(encodeURIComponent).join("/");
      const file = await request(`/files/${path}`);
      const extension = tool.target.toLowerCase().split(".").pop();
      onRun({ svg: "svg", py: "python" }[extension] || "html", file.content, tool.target);
    } catch (error) { notify(error.message, "error"); }
  }

  async function decide(decision) {
    setBusy(true);
    try {
      await request(`/approvals/${tool.approval_id}/${decision}`, { method: "POST" });
      if (decision === "denied") {
        setLocal({ status: "denied_by_user" });
      } else {
        // Report what actually happened, from the server's receipt.
        const [receipt] = await request(`/tasks/${tool.task_id}/receipts`);
        const result = JSON.parse(receipt?.result || "{}");
        setLocal(receipt?.status === "completed"
          ? { status: "completed", detail: result.summary, undoId: receipt.id }
          : { status: "failed", detail: result.error || "The action did not complete." });
      }
      onDecided?.();
    } catch (error) { notify(error.message, "error"); }
    finally { setBusy(false); }
  }

  async function undo() {
    setBusy(true);
    try {
      const { message } = await request(`/files/undo/${undoId}`, { method: "POST" });
      setLocal({ status: "undone", detail: message });
    } catch (error) { notify(error.message, "error"); }
    finally { setBusy(false); }
  }

  return <div className={`tool-card tool-${shown.tone}`}>
    <p className="tool-head"><strong>{ACTION_LABEL[tool.action] || tool.action}</strong>{tool.target && tool.target !== "workspace" && <code>{tool.target}</code>}</p>
    <p className="muted">{tool.summary}</p>
    <p className="tool-status">{shown.text}{local?.detail ? `: ${local.detail}` : ""}</p>
    {tool.reason && status === "awaiting_approval" && <p className="muted">{tool.reason}</p>}
    {status === "awaiting_approval" && tool.approval_id && <div className="row-actions">
      <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={() => decide("approved")}>Approve</button>
      <button type="button" className="btn btn-danger-quiet btn-sm" disabled={busy} onClick={() => decide("denied")}>Deny</button>
    </div>}
    {(canUndo || canRun) && <div className="row-actions">
      {canRun && <button type="button" className="btn btn-sm btn-primary" disabled={busy} onClick={run}>Run</button>}
      {canUndo && <button type="button" className="btn btn-sm" disabled={busy} onClick={undo}>Undo</button>}
    </div>}
  </div>;
}
