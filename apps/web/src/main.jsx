import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const API_KEY = import.meta.env.VITE_API_KEY || "";
const welcome = { role: "assistant", content: "Hello. I run locally and keep you in control. What should we work on?" };
let csrfToken = sessionStorage.getItem("assistant_csrf") || "";

async function request(path, options = {}) {
  const method = options.method || "GET";
  const headers = {
    "Content-Type": "application/json",
    ...(API_KEY ? { "X-Assistant-Key": API_KEY } : {}),
    ...(csrfToken && !["GET", "HEAD", "OPTIONS"].includes(method) ? { "X-CSRF-Token": csrfToken } : {}),
    ...options.headers,
  };
  const response = await fetch(`${API}/api/v1${path}`, { ...options, method, headers, credentials: "include" });
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.detail || "Request failed");
    error.status = response.status;
    throw error;
  }
  return data;
}

function App() {
  const [view, setView] = useState("chat");
  const [authState, setAuthState] = useState("loading");
  const [authDraft, setAuthDraft] = useState({ username: "", password: "", device_name: "Local browser" });
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState("Checking local model...");
  const [notice, setNotice] = useState("");
  const [conversations, setConversations] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [messages, setMessages] = useState([welcome]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [memories, setMemories] = useState([]);
  const [memoryDraft, setMemoryDraft] = useState("");
  const [tasks, setTasks] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [automations, setAutomations] = useState([]);
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [researchQuery, setResearchQuery] = useState("");
  const [researchResult, setResearchResult] = useState(null);
  const [researchBusy, setResearchBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [securityStatus, setSecurityStatus] = useState(null);
  const [securityAudit, setSecurityAudit] = useState([]);
  const [securityFindings, setSecurityFindings] = useState([]);
  const [secrets, setSecrets] = useState([]);
  const [secretDraft, setSecretDraft] = useState({ name: "", value: "" });
  const [taskDraft, setTaskDraft] = useState({ title: "", description: "", action: "information", risk_level: 0, arguments: { path: "", content: "" } });
  const [automationDraft, setAutomationDraft] = useState({ title: "", action: "list_files", interval_minutes: 60, arguments: { path: "", content: "" } });
  const endRef = useRef(null);

  useEffect(() => {
    request("/health").then((data) => setStatus(data.ollama === "available" ? `${data.model} ready` : "Ollama offline")).catch(() => setStatus("Backend offline"));
    initializeAuth();
  }, []);

  useEffect(() => {
    if (view === "memory") refreshMemories();
    if (view === "tasks") refreshTasks();
    if (view === "files") refreshFiles();
    if (view === "security") refreshSecurity();
  }, [view]);
  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [messages, busy]);

  async function refreshConversations() {
    try { setConversations(await request("/chat/conversations")); } catch { /* health badge reports connection */ }
  }
  async function refreshMemories() {
    try { setMemories(await request("/memory")); } catch (error) { setNotice(error.message); }
  }
  async function refreshTasks() {
    try {
      const [taskItems, approvalItems, logs, automationItems] = await Promise.all([request("/tasks"), request("/approvals"), request("/audit?limit=20"), request("/automations")]);
      setTasks(taskItems); setApprovals(approvalItems); setAuditLogs(logs); setAutomations(automationItems);
    } catch (error) { setNotice(error.message); }
  }
  async function refreshFiles() {
    try { setFiles(await request("/files")); } catch (error) { setNotice(error.message); }
  }
  async function refreshSecurity() {
    try {
      const [state, logs, findings, storedSecrets] = await Promise.all([
        request("/security/status"), request("/security/audit?limit=50"),
        request("/security/findings?limit=50"), request("/security/secrets"),
      ]);
      setSecurityStatus(state); setSecurityAudit(logs); setSecurityFindings(findings); setSecrets(storedSecrets);
    } catch (error) { setNotice(error.message); }
  }
  async function emergencyStop() {
    const reason = window.prompt("Reason for emergency stop:");
    if (!reason) return;
    try { await request("/security/emergency-stop", { method: "POST", body: JSON.stringify({ reason }) }); await refreshSecurity(); }
    catch (error) { setNotice(error.message); }
  }
  async function resumeOperations() {
    if (!window.confirm("Resume autonomous operations after reviewing the incident?")) return;
    try { await request("/security/resume", { method: "POST", body: JSON.stringify({ reason: "Explicit administrator resume" }) }); await refreshSecurity(); }
    catch (error) { setNotice(error.message); }
  }
  async function saveSecret(event) {
    event.preventDefault();
    try {
      await request("/security/secrets", { method: "POST", body: JSON.stringify(secretDraft) });
      setSecretDraft({ name: "", value: "" }); setNotice("Secret encrypted and saved. Its value will not be displayed again."); await refreshSecurity();
    } catch (error) { setNotice(error.message); }
  }
  async function openFile(path) {
    try { setSelectedFile(await request(`/files/${encodeURI(path)}`)); }
    catch (error) { setNotice(error.message); }
  }

  function newChat() { setConversationId(null); setMessages([welcome]); setView("chat"); setNotice(""); }
  async function openConversation(id) {
    try {
      const conversation = await request(`/chat/conversations/${id}`);
      setConversationId(id); setMessages(conversation.messages); setView("chat"); setNotice("");
    } catch (error) { setNotice(error.message); }
  }
  async function deleteConversation(event, id) {
    event.stopPropagation();
    if (!window.confirm("Delete this local conversation permanently?")) return;
    try {
      await request(`/chat/conversations/${id}`, { method: "DELETE" });
      if (conversationId === id) newChat();
      await refreshConversations();
    } catch (error) { setNotice(error.message); }
  }

  async function send(event) {
    event.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput(""); setMessages((items) => [...items, { role: "user", content: text }]); setBusy(true); setNotice("");
    try {
      const data = await request("/chat", { method: "POST", body: JSON.stringify({ message: text, conversation_id: conversationId }) });
      setConversationId(data.conversation_id);
      setMessages((items) => [...items, { role: "assistant", content: data.message }]);
      await refreshConversations();
    } catch (error) { setMessages((items) => [...items, { role: "error", content: error.message }]); }
    finally { setBusy(false); }
  }

  async function addMemory(event) {
    event.preventDefault(); const content = memoryDraft.trim(); if (!content) return;
    try {
      await request("/memory", { method: "POST", body: JSON.stringify({ content, category: "preference" }) });
      setMemoryDraft(""); setNotice("Memory saved locally."); await refreshMemories();
    } catch (error) { setNotice(error.message); }
  }
  async function removeMemory(id) {
    if (!window.confirm("Forget this saved memory?")) return;
    try { await request(`/memory/${id}`, { method: "DELETE" }); setNotice("Memory removed."); await refreshMemories(); }
    catch (error) { setNotice(error.message); }
  }
  async function createTask(event) {
    event.preventDefault();
    try {
      const created = await request("/tasks", { method: "POST", body: JSON.stringify(taskDraft) });
      setTaskDraft({ title: "", description: "", action: "information", risk_level: 0, arguments: { path: "", content: "" } });
      setNotice(created.status === "awaiting_approval" ? "Task created and waiting for your approval." : "Task planned.");
      await refreshTasks();
    } catch (error) { setNotice(error.message); }
  }
  async function decideApproval(id, decision) {
    try { await request(`/approvals/${id}/${decision}`, { method: "POST" }); setNotice(`Request ${decision}.`); await refreshTasks(); }
    catch (error) { setNotice(error.message); }
  }
  async function runResearch(event) {
    event.preventDefault();
    const query = researchQuery.trim();
    if (!query || researchBusy) return;
    setResearchBusy(true); setNotice("");
    try { setResearchResult(await request("/research", { method: "POST", body: JSON.stringify({ query, max_sources: 3 }) })); }
    catch (error) { setNotice(error.message); }
    finally { setResearchBusy(false); }
  }
  async function createAutomation(event) {
    event.preventDefault();
    try {
      await request("/automations", { method: "POST", body: JSON.stringify(automationDraft) });
      setAutomationDraft({ title: "", action: "list_files", interval_minutes: 60, arguments: { path: "", content: "" } });
      setNotice("Recurring automation created."); await refreshTasks();
    } catch (error) { setNotice(error.message); }
  }
  async function toggleAutomation(item) {
    try { await request(`/automations/${item.id}/enabled/${!item.enabled}`, { method: "POST" }); await refreshTasks(); }
    catch (error) { setNotice(error.message); }
  }
  async function deleteAutomation(id) {
    if (!window.confirm("Delete this recurring automation?")) return;
    try { await request(`/automations/${id}`, { method: "DELETE" }); await refreshTasks(); }
    catch (error) { setNotice(error.message); }
  }
  function startListening() {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) { setNotice("Voice dictation is not supported by this browser."); return; }
    const recognition = new Recognition();
    recognition.lang = navigator.language || "en-US";
    recognition.interimResults = false;
    recognition.onstart = () => setListening(true);
    recognition.onend = () => setListening(false);
    recognition.onerror = (event) => { setListening(false); setNotice(`Voice input failed: ${event.error}`); };
    recognition.onresult = (event) => setInput((current) => `${current}${current ? " " : ""}${event.results[0][0].transcript}`);
    recognition.start();
  }
  function speak(text) {
    if (!("speechSynthesis" in window)) { setNotice("Speech playback is not supported by this browser."); return; }
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  }

  async function initializeAuth() {
    try {
      const auth = await request("/auth/status");
      if (!auth.auth_required || API_KEY) {
        setAuthState("ready");
        await refreshConversations();
        return;
      }
      if (!auth.configured) {
        setAuthState("bootstrap");
        return;
      }
      try {
        const current = await request("/auth/me");
        setUser(current); setAuthState("ready"); await refreshConversations();
      } catch { setAuthState("login"); }
    } catch (error) { setNotice(error.message); setAuthState("offline"); }
  }
  async function authenticate(event) {
    event.preventDefault();
    try {
      const endpoint = authState === "bootstrap" ? "/auth/bootstrap" : "/auth/login";
      const data = await request(endpoint, { method: "POST", body: JSON.stringify(authDraft) });
      csrfToken = data.csrf_token;
      sessionStorage.setItem("assistant_csrf", csrfToken);
      setUser(data.user); setAuthState("ready"); setAuthDraft({ ...authDraft, password: "" });
      await refreshConversations();
    } catch (error) { setNotice(error.message); }
  }
  async function logout() {
    try { await request("/auth/logout", { method: "POST" }); } catch { /* clear local state anyway */ }
    csrfToken = ""; sessionStorage.removeItem("assistant_csrf"); setUser(null); setAuthState("login");
  }

  if (authState !== "ready") return <main className="auth-screen"><form className="auth-card" onSubmit={authenticate}><div className="mark">A</div><h1>Local Assistant Security</h1><p>{authState === "bootstrap" ? "Create the first local administrator. This account is stored only in the local database." : authState === "login" ? "Sign in from this registered device." : authState === "offline" ? "The local API is unavailable." : "Checking local security state..."}</p>{notice && <div className="notice">{notice}</div>}{["bootstrap", "login"].includes(authState) && <><label>Username<input required minLength="3" value={authDraft.username} onChange={(event) => setAuthDraft({ ...authDraft, username: event.target.value })} /></label><label>Password<input required type="password" minLength={authState === "bootstrap" ? 12 : 1} value={authDraft.password} onChange={(event) => setAuthDraft({ ...authDraft, password: event.target.value })} /></label><label>Device name<input required value={authDraft.device_name} onChange={(event) => setAuthDraft({ ...authDraft, device_name: event.target.value })} /></label><button>{authState === "bootstrap" ? "Create administrator" : "Sign in"}</button></>}</form></main>;

  const viewInfo = {
    chat: ["Conversation", "Generated on this computer"], research: ["Research", "Free sources, injection-scanned and synthesized locally"],
    memory: ["Memory", "Inspect and control what the assistant remembers"], files: ["Authorized files", "Restricted to the local assistant workspace"],
    tasks: ["Tasks & approvals", "Sensitive actions stay behind action-bound approval gates"], security: ["Security center", "Authorization, audit integrity, sandbox, findings, and emergency controls"],
  }[view];

  return <div className="app-frame">
    <aside className="sidebar">
      <div className="brand"><div className="mark">A</div><div><h1>Local Assistant</h1><p>{status}</p></div></div>
      <button className="new-chat" onClick={newChat}>+ New chat</button>
      <nav aria-label="Primary">{[["chat", "Chat"], ["research", "Research"], ["memory", "Memory"], ["files", "Files"], ["tasks", "Tasks & approvals"], ["security", "Security"]].map(([id, label]) => <button className={view === id ? "active" : ""} onClick={() => setView(id)} key={id}>{label}</button>)}</nav>
      <div className="history-label">Recent conversations</div>
      <div className="history">{conversations.map((conversation) => <button className={conversationId === conversation.id ? "selected" : ""} onClick={() => openConversation(conversation.id)} key={conversation.id}><span>{conversation.title}</span><b onClick={(event) => deleteConversation(event, conversation.id)} aria-label={`Delete ${conversation.title}`}>x</b></button>)}{!conversations.length && <p>No conversations yet</p>}</div>
      <small>Private by default<br />No paid AI API{user && <><br />Signed in as {user.username}<br /><button className="link-button" onClick={logout}>Sign out</button></>}</small>
    </aside>

    <main className="workspace">
      <header className="topbar"><div><h2>{viewInfo[0]}</h2><p>{viewInfo[1]}</p></div></header>
      {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice("")}>x</button></div>}

      {view === "chat" && <><section className="messages" aria-live="polite">{messages.map((message, index) => <article className={`message ${message.role}`} key={message.id || index}><span>{message.role === "user" ? "You" : message.role === "error" ? "System" : "Assistant"}</span><p>{message.content}</p>{message.role === "assistant" && <button className="speak" onClick={() => speak(message.content)} aria-label="Read response aloud">Listen</button>}</article>)}{busy && <article className="message assistant"><span>Assistant</span><p className="pulse">Thinking locally...</p></article>}<div ref={endRef} /></section><form className="composer" onSubmit={send}><textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder="Message your local assistant..." rows="2" onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) send(event); }} /><button className="voice" type="button" onClick={startListening}>{listening ? "Listening..." : "Voice"}</button><button type="submit" disabled={busy || !input.trim()}>Send</button><small>AI runs in Ollama. Voice capture/playback uses your browser and operating-system capabilities.</small></form></>}

      {view === "memory" && <section className="panel"><div className="panel-heading"><div><h3>Long-term memory</h3><p>Only save details that should influence future conversations.</p></div><span>{memories.length} saved</span></div><form className="inline-form" onSubmit={addMemory}><input value={memoryDraft} onChange={(event) => setMemoryDraft(event.target.value)} placeholder="Example: I prefer concise technical explanations" /><button>Remember</button></form><div className="cards">{memories.map((memory) => <article className="card" key={memory.id}><div><span>{memory.category}</span><p>{memory.content}</p></div><button className="danger" onClick={() => removeMemory(memory.id)}>Forget</button></article>)}{!memories.length && <div className="empty">No memories saved. You are in full control of this list.</div>}</div></section>}

      {view === "research" && <section className="panel research-panel"><div className="panel-heading"><div><h3>Research a topic</h3><p>Wikipedia provides the free source material; Ollama writes the report locally.</p></div></div><form className="inline-form" onSubmit={runResearch}><input value={researchQuery} onChange={(event) => setResearchQuery(event.target.value)} placeholder="What would you like to investigate?" /><button disabled={researchBusy}>{researchBusy ? "Researching..." : "Research"}</button></form>{researchResult ? <article className="research-report"><h3>{researchResult.query}</h3><div className="report-body">{researchResult.report}</div><h4>Sources</h4><ol>{researchResult.sources.map((source) => <li key={source.url}><a href={source.url} target="_blank" rel="noreferrer">{source.title}</a><p>{source.excerpt.slice(0, 240)}{source.excerpt.length > 240 ? "..." : ""}</p></li>)}</ol></article> : <div className="empty">Enter a topic to produce a cited local report.</div>}</section>}

      {view === "files" && <section className="panel file-grid"><div><div className="panel-heading"><div><h3>Workspace files</h3><p>Read access is automatic. Creating or editing files requires approval.</p></div><span>{files.length} files</span></div><div className="cards">{files.map((file) => <button className="file-row" onClick={() => openFile(file.path)} key={file.path}><span>{file.path}</span><small>{file.size} bytes</small></button>)}{!files.length && <div className="empty">The workspace is empty. Create a write-file task to add a document.</div>}</div></div><div className="file-preview"><div className="panel-heading"><div><h3>{selectedFile?.path || "Preview"}</h3><p>{selectedFile ? `${selectedFile.size} bytes` : "Choose a UTF-8 text file"}</p></div></div><pre>{selectedFile?.content || "No file selected."}</pre></div></section>}

      {view === "tasks" && <section className="panel task-grid">
        <div><div className="panel-heading"><div><h3>Plan a task</h3><p>Actions with side effects automatically request approval.</p></div></div><form className="stack-form" onSubmit={createTask}><label>Title<input required value={taskDraft.title} onChange={(event) => setTaskDraft({ ...taskDraft, title: event.target.value })} placeholder="Prepare project notes" /></label><label>Description<textarea rows="3" value={taskDraft.description} onChange={(event) => setTaskDraft({ ...taskDraft, description: event.target.value })} /></label><label>Action type<select value={taskDraft.action} onChange={(event) => { const action = event.target.value; setTaskDraft({ ...taskDraft, action, risk_level: action === "information" ? 0 : action === "list_files" || action === "read_file" ? 1 : 2 }); }}><option value="information">Information only</option><option value="list_files">List workspace files</option><option value="read_file">Read a workspace file</option><option value="write_file">Write or edit a file</option></select></label>{["read_file", "write_file"].includes(taskDraft.action) && <label>Relative file path<input required value={taskDraft.arguments.path} onChange={(event) => setTaskDraft({ ...taskDraft, arguments: { ...taskDraft.arguments, path: event.target.value } })} placeholder="notes/project.txt" /></label>}{taskDraft.action === "write_file" && <label>File content<textarea required rows="5" value={taskDraft.arguments.content} onChange={(event) => setTaskDraft({ ...taskDraft, arguments: { ...taskDraft.arguments, content: event.target.value } })} /></label>}<button>Create task</button></form></div>
        <div><div className="panel-heading"><div><h3>Approval inbox</h3><p>Nothing executes until you decide.</p></div><span>{approvals.filter((item) => item.status === "pending").length} pending</span></div><div className="cards">{approvals.filter((item) => item.status === "pending").map((approval) => <article className="card approval" key={approval.id}><div><span>{approval.action}</span><p>{approval.description}</p><small>Why: {approval.justification}<br />Targets: {approval.targets.join(", ")}<br />Impact: {approval.consequences}</small></div><div><button onClick={() => decideApproval(approval.id, "approved")}>Approve</button><button className="danger" onClick={() => decideApproval(approval.id, "denied")}>Deny</button></div></article>)}{!approvals.some((item) => item.status === "pending") && <div className="empty">No pending approvals.</div>}</div></div>
        <div className="task-list"><div className="panel-heading"><div><h3>Task history</h3></div><span>{tasks.length} tasks</span></div><div className="cards">{tasks.map((task) => <article className="card" key={task.id}><div><span>Risk {task.risk_level} / {task.status.replaceAll("_", " ")}</span><p>{task.title}</p></div></article>)}{!tasks.length && <div className="empty">No tasks planned yet.</div>}</div></div>
        <div className="task-list automation-section"><div className="panel-heading"><div><h3>Recurring automations</h3><p>Read-only jobs run automatically. Every scheduled write still requires approval.</p></div><span>{automations.length} rules</span></div><form className="automation-form" onSubmit={createAutomation}><input required value={automationDraft.title} onChange={(event) => setAutomationDraft({ ...automationDraft, title: event.target.value })} placeholder="Automation name" /><select value={automationDraft.action} onChange={(event) => setAutomationDraft({ ...automationDraft, action: event.target.value })}><option value="list_files">List workspace files</option><option value="read_file">Read a file</option><option value="write_file">Write a file (approval required)</option></select><input type="number" min="1" max="43200" value={automationDraft.interval_minutes} onChange={(event) => setAutomationDraft({ ...automationDraft, interval_minutes: Number(event.target.value) })} aria-label="Interval in minutes" />{["read_file", "write_file"].includes(automationDraft.action) && <input required value={automationDraft.arguments.path} onChange={(event) => setAutomationDraft({ ...automationDraft, arguments: { ...automationDraft.arguments, path: event.target.value } })} placeholder="Relative file path" />}{automationDraft.action === "write_file" && <textarea required value={automationDraft.arguments.content} onChange={(event) => setAutomationDraft({ ...automationDraft, arguments: { ...automationDraft.arguments, content: event.target.value } })} placeholder="File content" />}<button>Create automation</button></form><div className="cards">{automations.map((item) => <article className="card" key={item.id}><div><span>{item.enabled ? "active" : "paused"} / every {item.interval_minutes} minutes</span><p>{item.title}</p></div><div className="card-actions"><button onClick={() => toggleAutomation(item)}>{item.enabled ? "Pause" : "Resume"}</button><button className="danger" onClick={() => deleteAutomation(item.id)}>Delete</button></div></article>)}</div></div>
        <div className="task-list"><div className="panel-heading"><div><h3>Audit log</h3><p>Recent memory, task, approval, and tool events.</p></div><span>{auditLogs.length} events</span></div><div className="cards">{auditLogs.map((log) => <article className="card" key={log.id}><div><span>{log.outcome} / {new Date(log.created_at).toLocaleString()}</span><p>{log.action}</p></div><small>{log.detail}</small></article>)}</div></div>
      </section>}
      {view === "security" && <section className="panel security-panel">
        <div className="security-actions"><button className="danger" onClick={emergencyStop}>Emergency stop</button>{securityStatus?.emergency_stopped && <button onClick={resumeOperations}>Resume operations</button>}</div>
        {securityStatus && <div className="status-grid">
          <article><span>Emergency</span><strong className={securityStatus.emergency_stopped ? "bad" : "good"}>{securityStatus.emergency_stopped ? "STOPPED" : "Ready"}</strong><small>{securityStatus.reason || "No active stop"}</small></article>
          <article><span>Audit chain</span><strong className={securityStatus.audit_chain_valid ? "good" : "bad"}>{securityStatus.audit_chain_valid ? "Valid" : "TAMPERED"}</strong><small>HMAC hash chain</small></article>
          <article><span>OPA</span><strong className={securityStatus.opa_available ? "good" : securityStatus.opa_required ? "bad" : "warn"}>{securityStatus.opa_available ? "Connected" : securityStatus.opa_required ? "Fail closed" : "Local fallback"}</strong><small>{securityStatus.opa_required ? "Required" : "Optional in development"}</small></article>
          <article><span>OpenShell</span><strong className={securityStatus.sandbox_mode === "openshell" ? "good" : "warn"}>{securityStatus.sandbox_mode}</strong><small>Host shell is never exposed</small></article>
          <article><span>Sessions</span><strong>{securityStatus.active_sessions}</strong><small>Active device-bound sessions</small></article>
          <article><span>Findings</span><strong>{securityStatus.open_findings}</strong><small>{securityStatus.pending_approvals} pending approvals</small></article>
        </div>}
        <div className="security-columns"><div><div className="panel-heading"><div><h3>Encrypted secret vault</h3><p>Values are encrypted at rest and never returned by the API.</p></div></div><form className="stack-form" onSubmit={saveSecret}><label>Name<input required pattern="[A-Za-z0-9_.-]+" value={secretDraft.name} onChange={(event) => setSecretDraft({ ...secretDraft, name: event.target.value })} /></label><label>Secret value<input required type="password" value={secretDraft.value} onChange={(event) => setSecretDraft({ ...secretDraft, value: event.target.value })} /></label><button>Encrypt and save</button></form><div className="cards compact">{secrets.map((item) => <article className="card" key={item.id}><p>{item.name}</p><small>{new Date(item.updated_at).toLocaleString()}</small></article>)}</div></div>
        <div><div className="panel-heading"><div><h3>Security findings</h3><p>Prompt-injection and suspicious-content detections.</p></div></div><div className="cards compact">{securityFindings.map((item) => <article className="card" key={item.id}><div><span>{item.severity} / {item.category}</span><p>{item.detail}</p></div></article>)}{!securityFindings.length && <div className="empty">No findings recorded.</div>}</div></div></div>
        <div className="panel-heading audit-heading"><div><h3>Tamper-evident audit</h3><p>Authentication, authorization, approvals, tools, secrets, and emergency events.</p></div><span>{securityAudit.length} shown</span></div><div className="cards compact">{securityAudit.map((item) => <article className="card" key={item.id}><div><span>#{item.sequence} / {item.outcome}</span><p>{item.event_type}</p></div><small>{item.detail}</small></article>)}</div>
      </section>}
    </main>
  </div>;
}

createRoot(document.getElementById("root")).render(<React.StrictMode><App /></React.StrictMode>);

if ("serviceWorker" in navigator && import.meta.env.PROD) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js"));
}
