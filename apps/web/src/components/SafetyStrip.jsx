import React from "react";

/** The assistant's signature: live safety state, visible on every screen. */
export default function SafetyStrip({ status }) {
  if (!status) return <p className="muted safety-missing">Safety status unavailable</p>;
  const stopped = status.emergency_stopped;
  const chainOk = status.audit_chain_valid;
  const waiting = status.pending_approvals;
  return <ul className="safety" aria-label="Safety status">
    <li><a href="#/security"><span>Operations</span><strong className={stopped ? "bad" : "good"}>{stopped ? "Stopped" : "Running"}</strong></a></li>
    <li><a href="#/security"><span>Audit chain</span><strong className={chainOk ? "good" : "bad"}>{chainOk ? "Verified" : "Broken"}</strong></a></li>
    <li><a href="#/tasks"><span>Approvals</span><strong className={waiting ? "warn" : "good"}>{waiting ? `${waiting} waiting` : "None waiting"}</strong></a></li>
  </ul>;
}
