import React, { useState } from "react";
import { request, json } from "../api.js";
import { useLoad } from "../hooks.js";
import { Async, Badge, ConfirmButton, EmptyState, SectionHead, formatTime } from "../components/ui.jsx";

const EMPTY_TASK = { title: "", description: "", action: "information", risk_level: 0, arguments: { path: "", content: "" } };
const EMPTY_AUTOMATION = { title: "", action: "list_files", interval_minutes: 60, arguments: { path: "", content: "" } };
const RISK_FOR = { information: 0, list_files: 1, read_file: 1, write_file: 2 };

const loadAll = () => Promise.all([request("/tasks"), request("/approvals"), request("/audit?limit=20"), request("/automations")])
  .then(([tasks, approvals, logs, automations]) => ({ tasks, approvals, logs, automations }));

export default function TasksView({ notify, refreshSafety }) {
  const load = useLoad(loadAll);
  const [task, setTask] = useState(EMPTY_TASK);
  const [automation, setAutomation] = useState(EMPTY_AUTOMATION);

  async function act(work, success) {
    try { await work(); if (success) notify(success); load.reload(); refreshSafety(); }
    catch (error) { notify(error.message, "error"); }
  }

  const createTask = (event) => {
    event.preventDefault();
    act(async () => {
      const created = await request("/tasks", { method: "POST", body: json(task) });
      setTask(EMPTY_TASK);
      notify(created.status === "awaiting_approval" ? "Task created. It is waiting for your approval." : "Task planned.");
    });
  };
  const createAutomation = (event) => {
    event.preventDefault();
    act(async () => { await request("/automations", { method: "POST", body: json(automation) }); setAutomation(EMPTY_AUTOMATION); }, "Automation created.");
  };
  const decide = (id, decision) => act(() => request(`/approvals/${id}/${decision}`, { method: "POST" }), decision === "approved" ? "Approved." : "Denied.");
  const toggle = (item) => act(() => request(`/automations/${item.id}/enabled/${!item.enabled}`, { method: "POST" }));
  const remove = (id) => act(() => request(`/automations/${id}`, { method: "DELETE" }), "Automation deleted.");

  const needsPath = ["read_file", "write_file"].includes(task.action);
  const autoNeedsPath = ["read_file", "write_file"].includes(automation.action);

  return <div className="page">
    <Async load={load} rows={4}>{({ tasks, approvals, logs, automations }) => {
      const pending = approvals.filter((item) => item.status === "pending");
      return <>
        <section>
          <SectionHead title="Waiting for your decision" hint="Nothing runs until you approve the exact action shown." count={`${pending.length} waiting`} />
          {pending.length ? <ul className="approvals">{pending.map((approval) => <li key={approval.id}>
            <div className="approval-main">
              <p><Badge tone="warn">{approval.action}</Badge></p>
              <p className="approval-title">{approval.description}</p>
              <dl className="facts">
                <div><dt>Why</dt><dd>{approval.justification}</dd></div>
                <div><dt>Affects</dt><dd>{approval.targets.join(", ")}</dd></div>
                <div><dt>Result</dt><dd>{approval.consequences}</dd></div>
              </dl>
            </div>
            <div className="approval-actions">
              <button type="button" className="btn btn-primary" onClick={() => decide(approval.id, "approved")}>Approve</button>
              <button type="button" className="btn btn-danger-quiet" onClick={() => decide(approval.id, "denied")}>Deny</button>
            </div>
          </li>)}</ul> : <EmptyState title="Nothing is waiting">When a task needs approval it will appear here, and the badge in the top bar will count it.</EmptyState>}
        </section>

        <div className="split">
          <section>
            <SectionHead title="Plan a task" hint="Actions that change things ask for approval first." />
            <form className="form" onSubmit={createTask}>
              <label>Title<input required value={task.title} onChange={(event) => setTask({ ...task, title: event.target.value })} placeholder="Prepare project notes" /></label>
              <label>Description<textarea rows={3} value={task.description} onChange={(event) => setTask({ ...task, description: event.target.value })} /></label>
              <label>Action
                <select value={task.action} onChange={(event) => { const action = event.target.value; setTask({ ...task, action, risk_level: RISK_FOR[action] ?? 2 }); }}>
                  <option value="information">Information only</option>
                  <option value="list_files">List workspace files</option>
                  <option value="read_file">Read a workspace file</option>
                  <option value="write_file">Write or edit a file (needs approval)</option>
                </select>
              </label>
              {needsPath && <label>File path<input required value={task.arguments.path} onChange={(event) => setTask({ ...task, arguments: { ...task.arguments, path: event.target.value } })} placeholder="notes/project.txt" /><small>Relative to the workspace folder.</small></label>}
              {task.action === "write_file" && <label>File content<textarea required rows={5} value={task.arguments.content} onChange={(event) => setTask({ ...task, arguments: { ...task.arguments, content: event.target.value } })} /></label>}
              <button className="btn btn-primary">Create task</button>
            </form>
          </section>

          <section>
            <SectionHead title="Task history" count={`${tasks.length} tasks`} />
            {tasks.length ? <div className="table-wrap"><table>
              <thead><tr><th scope="col">Task</th><th scope="col">Risk</th><th scope="col">Status</th></tr></thead>
              <tbody>{tasks.map((item) => <tr key={item.id}><td>{item.title}</td><td>{item.risk_level}</td><td>{item.status.replaceAll("_", " ")}</td></tr>)}</tbody>
            </table></div> : <EmptyState title="No tasks yet">Plan one with the form and it will be listed here.</EmptyState>}
          </section>
        </div>

        <section>
          <SectionHead title="Recurring automations" hint="Read-only jobs run on their own. Every scheduled write still asks for approval." count={`${automations.length} rules`} />
          <form className="form form-row" onSubmit={createAutomation}>
            <label>Name<input required value={automation.title} onChange={(event) => setAutomation({ ...automation, title: event.target.value })} /></label>
            <label>Action
              <select value={automation.action} onChange={(event) => setAutomation({ ...automation, action: event.target.value })}>
                <option value="list_files">List workspace files</option>
                <option value="read_file">Read a file</option>
                <option value="write_file">Write a file (needs approval)</option>
              </select>
            </label>
            <label>Every (minutes)<input type="number" min={1} max={43200} value={automation.interval_minutes} onChange={(event) => setAutomation({ ...automation, interval_minutes: Number(event.target.value) })} /></label>
            {autoNeedsPath && <label>File path<input required value={automation.arguments.path} onChange={(event) => setAutomation({ ...automation, arguments: { ...automation.arguments, path: event.target.value } })} /></label>}
            {automation.action === "write_file" && <label className="span-all">File content<textarea required rows={3} value={automation.arguments.content} onChange={(event) => setAutomation({ ...automation, arguments: { ...automation.arguments, content: event.target.value } })} /></label>}
            <div className="span-all"><button className="btn btn-primary">Create automation</button></div>
          </form>
          {automations.length ? <ul className="rows">{automations.map((item) => <li key={item.id}>
            <div><p>{item.title}</p><p className="muted">{item.enabled ? "Active" : "Paused"}, every {item.interval_minutes} minutes</p></div>
            <div className="row-actions">
              <button type="button" className="btn" onClick={() => toggle(item)}>{item.enabled ? "Pause" : "Resume"}</button>
              <ConfirmButton label={`Delete automation: ${item.title}`} onConfirm={() => remove(item.id)}>Delete</ConfirmButton>
            </div>
          </li>)}</ul> : <EmptyState title="No automations">Create one above to run a read-only job on a schedule.</EmptyState>}
        </section>

        <details className="disclosure">
          <summary>Recent activity ({logs.length})</summary>
          {logs.length ? <div className="table-wrap"><table>
            <thead><tr><th scope="col">When</th><th scope="col">Event</th><th scope="col">Outcome</th><th scope="col">Detail</th></tr></thead>
            <tbody>{logs.map((log) => <tr key={log.id}><td>{formatTime(log.created_at)}</td><td>{log.action}</td><td>{log.outcome}</td><td>{log.detail}</td></tr>)}</tbody>
          </table></div> : <EmptyState title="No activity yet" />}
        </details>
      </>;
    }}</Async>
  </div>;
}
