import React, { useState } from "react";
import { request, json } from "../api.js";
import { useLoad } from "../hooks.js";
import { Async, ConfirmButton, EmptyState, SectionHead, Skeleton, formatTime } from "../components/ui.jsx";

const loadDetails = () => Promise.all([request("/security/audit?limit=50"), request("/security/findings?limit=50"), request("/security/secrets")])
  .then(([audit, findings, secrets]) => ({ audit, findings, secrets }));

function opaFact(status) {
  if (status.opa_available) return { value: "Connected", tone: "good", hint: "Policies are checked by OPA." };
  if (status.opa_required) return { value: "Required, unavailable", tone: "bad", hint: "Every task is denied until OPA runs." };
  return { value: "Built-in policy", tone: "warn", hint: "The local fallback enforces the same rules." };
}

export default function SecurityView({ notify, status, refreshSafety }) {
  const details = useLoad(loadDetails);
  const [stopping, setStopping] = useState(false);
  const [reason, setReason] = useState("");
  const [secret, setSecret] = useState({ name: "", value: "" });

  async function act(work, success) {
    try { await work(); if (success) notify(success); await refreshSafety(); details.reload(); return true; }
    catch (error) { notify(error.message, "error"); return false; }
  }
  const stop = async (event) => {
    event.preventDefault();
    const ok = await act(() => request("/security/emergency-stop", { method: "POST", body: json({ reason: reason.trim() }) }), "Emergency stop is active.");
    if (ok) { setStopping(false); setReason(""); }
  };
  const resume = () => act(() => request("/security/resume", { method: "POST", body: json({ reason: "Explicit administrator resume" }) }), "Operations resumed.");
  const saveSecret = (event) => {
    event.preventDefault();
    act(async () => { await request("/security/secrets", { method: "POST", body: json(secret) }); setSecret({ name: "", value: "" }); }, "Secret encrypted and saved. Its value is never shown again.");
  };

  const facts = status ? [
    { label: "Emergency stop", value: status.emergency_stopped ? "Stopped" : "Ready", tone: status.emergency_stopped ? "bad" : "good", hint: status.reason || "No active stop." },
    { label: "Audit chain", value: status.audit_chain_valid ? "Verified" : "Tampering detected", tone: status.audit_chain_valid ? "good" : "bad", hint: "HMAC hash chain over every audit entry." },
    { label: "Policy engine", ...opaFact(status) },
    { label: "Sandbox", value: status.sandbox_mode.charAt(0).toUpperCase() + status.sandbox_mode.slice(1), tone: status.sandbox_mode === "openshell" ? "good" : "warn", hint: "The host shell is never exposed." },
    { label: "Active sessions", value: String(status.active_sessions), hint: "Device-bound sessions." },
    { label: "Open findings", value: String(status.open_findings), hint: `${status.pending_approvals} approvals waiting.` },
  ] : [];

  return <div className="page">
    <section>
      <SectionHead title="Emergency controls" hint="Stopping blocks every autonomous action until you resume." />
      {status?.emergency_stopped
        ? <ConfirmButton tone="primary" confirmLabel="Resume operations" label="Resume operations" onConfirm={resume}>Resume operations</ConfirmButton>
        : stopping
          ? <form className="form form-narrow" onSubmit={stop}>
            <label>Reason for the stop<input required autoFocus value={reason} onChange={(event) => setReason(event.target.value)} /></label>
            <div className="row-actions">
              <button className="btn btn-danger">Stop all operations</button>
              <button type="button" className="btn" onClick={() => { setStopping(false); setReason(""); }}>Cancel</button>
            </div>
          </form>
          : <button type="button" className="btn btn-danger-quiet" onClick={() => setStopping(true)}>Emergency stop</button>}
    </section>

    <section>
      <SectionHead title="Status" />
      {status ? <dl className="status-list">{facts.map((fact) => <div key={fact.label}>
        <dt>{fact.label}</dt>
        <dd><strong className={fact.tone}>{fact.value}</strong><span className="muted">{fact.hint}</span></dd>
      </div>)}</dl> : <Skeleton rows={3} />}
    </section>

    <Async load={details} rows={4}>{({ audit, findings, secrets }) => <>
      <div className="split">
        <section>
          <SectionHead title="Encrypted secret vault" hint="Values are encrypted at rest and never returned by the API." />
          <form className="form" onSubmit={saveSecret}>
            <label>Name<input required pattern="[A-Za-z0-9_.\-]+" autoComplete="off" value={secret.name} onChange={(event) => setSecret({ ...secret, name: event.target.value })} /><small>Letters, numbers, dots, dashes and underscores.</small></label>
            <label>Value<input required type="password" autoComplete="off" value={secret.value} onChange={(event) => setSecret({ ...secret, value: event.target.value })} /></label>
            <button className="btn btn-primary">Encrypt and save</button>
          </form>
          {secrets.length ? <ul className="rows rows-tight">{secrets.map((item) => <li key={item.id}><p>{item.name}</p><p className="muted">Updated {formatTime(item.updated_at)}</p></li>)}</ul> : <EmptyState title="No secrets stored" />}
        </section>
        <section>
          <SectionHead title="Findings" hint="Prompt-injection and suspicious-content detections." count={`${findings.length}`} />
          {findings.length ? <ul className="rows rows-tight">{findings.map((item) => <li key={item.id}><div><p>{item.detail}</p><p className="muted">{item.severity}, {item.category}</p></div></li>)}</ul> : <EmptyState title="No findings" >Nothing suspicious has been detected.</EmptyState>}
        </section>
      </div>
      <section>
        <SectionHead title="Tamper-evident audit" hint="Sign-ins, approvals, tools, secrets and emergency events." count={`${audit.length} shown`} />
        {audit.length ? <div className="table-wrap"><table>
          <thead><tr><th scope="col">No.</th><th scope="col">Event</th><th scope="col">Outcome</th><th scope="col">Detail</th></tr></thead>
          <tbody>{audit.map((item) => <tr key={item.id}><td>{item.sequence}</td><td>{item.event_type}</td><td>{item.outcome}</td><td>{item.detail}</td></tr>)}</tbody>
        </table></div> : <EmptyState title="The audit log is empty" />}
      </section>
    </>}</Async>
  </div>;
}
