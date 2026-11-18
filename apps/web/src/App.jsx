import React, { useCallback, useEffect, useRef, useState } from "react";
import { request, setCsrf, API_KEY } from "./api.js";
import { goTo, useChat, useMedia, useReminders, useRoute } from "./hooks.js";
import AuthScreen from "./components/AuthScreen.jsx";
import Sidebar, { NAV } from "./components/Sidebar.jsx";
import SafetyStrip from "./components/SafetyStrip.jsx";
import ChatView from "./views/ChatView.jsx";
import ResearchView from "./views/ResearchView.jsx";
import MemoryView from "./views/MemoryView.jsx";
import RemindersView, { formatWhen } from "./views/RemindersView.jsx";
import FilesView from "./views/FilesView.jsx";
import TasksView from "./views/TasksView.jsx";
import SecurityView from "./views/SecurityView.jsx";

const SUBTITLES = {
  chat: "Replies are generated on this computer.",
  research: "Free sources, scanned for prompt injection, summarized locally.",
  memory: "What the assistant remembers between conversations.",
  reminders: "Alerts at the top of the app and as Windows notifications.",
  files: "Only the local assistant workspace is reachable.",
  tasks: "Anything with side effects waits for your approval.",
  security: "Access, audit integrity, the sandbox and the emergency stop.",
};

export default function App() {
  const view = useRoute();
  const narrow = useMedia("(max-width: 59.99rem)");
  const [authState, setAuthState] = useState("loading");
  const [authError, setAuthError] = useState("");
  const [user, setUser] = useState(null);
  const [modelStatus, setModelStatus] = useState("Checking local model...");
  const [modelReady, setModelReady] = useState(null);
  const [safety, setSafety] = useState(null);
  const [notice, setNotice] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const mainRef = useRef(null);

  // notify(null) clears the notice (used when a "working on it" message is finished).
  const notify = useCallback((text, kind = "info") => setNotice(text ? { text, kind } : null), []);
  const ready = authState === "ready";
  const chat = useChat(notify, ready);
  const reminders = useReminders(ready, notify);

  const refreshSafety = useCallback(async () => {
    try { setSafety(await request("/security/status")); } catch { setSafety(null); }
  }, []);
  const refreshHealth = useCallback(async () => {
    try {
      const data = await request("/health");
      const online = data.ollama === "available";
      setModelReady(online);
      setModelStatus(online ? `${data.model} is ready` : "Ollama is offline");
    } catch { setModelReady(false); setModelStatus("Backend is offline"); }
  }, []);

  const initializeAuth = useCallback(async () => {
    setAuthState("loading"); setAuthError("");
    try {
      const auth = await request("/auth/status");
      if (!auth.auth_required || API_KEY) { setAuthState("ready"); return; }
      if (!auth.configured) { setAuthState("bootstrap"); return; }
      try { setUser(await request("/auth/me")); setAuthState("ready"); }
      catch { setAuthState("login"); }
    } catch (error) { setAuthError(error.message); setAuthState("offline"); }
  }, []);

  useEffect(() => { initializeAuth(); }, [initializeAuth]);
  useEffect(() => {
    refreshHealth();
    if (!ready) return undefined;
    refreshSafety();
    const timer = setInterval(() => { refreshHealth(); refreshSafety(); }, 30000);
    return () => clearInterval(timer);
  }, [ready, refreshHealth, refreshSafety]);

  useEffect(() => { if (ready) refreshSafety(); setNotice(null); }, [view, ready, refreshSafety]);
  useEffect(() => {
    const entry = NAV.find(([id]) => id === view);
    document.title = `${entry ? entry[1] : "Chat"} - Local Assistant`;
    mainRef.current?.focus({ preventScroll: true });
  }, [view]);
  useEffect(() => {
    if (!menuOpen) return undefined;
    const onKey = (event) => { if (event.key === "Escape") setMenuOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);
  useEffect(() => { if (!narrow) setMenuOpen(false); }, [narrow]);

  async function signOut() {
    try { await request("/auth/logout", { method: "POST" }); } catch { /* clear local state anyway */ }
    setCsrf(""); setUser(null); chat.newChat(); setAuthState("login");
  }

  if (!ready) {
    return <AuthScreen key={authState} mode={authState} error={authError} onRetry={initializeAuth}
      onSignedIn={(signedInUser) => { setUser(signedInUser); setAuthState("ready"); }} />;
  }

  const title = (NAV.find(([id]) => id === view) || NAV[0])[1];
  const shared = { notify, refreshSafety };
  const body = {
    chat: <ChatView chat={chat} notify={notify} modelReady={modelReady} refreshSafety={refreshSafety} />,
    research: <ResearchView {...shared} />,
    memory: <MemoryView {...shared} />,
    reminders: <RemindersView reminders={reminders} />,
    files: <FilesView {...shared} />,
    tasks: <TasksView {...shared} />,
    security: <SecurityView {...shared} status={safety} />,
  }[view];

  return <div className="shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <Sidebar view={view} chat={chat} user={user} modelStatus={modelStatus} drawer={narrow ? (menuOpen ? "open" : "closed") : undefined}
      onNavigate={() => setMenuOpen(false)} onNewChat={() => { chat.newChat(); goTo("chat"); setMenuOpen(false); }} onSignOut={signOut} />
    {narrow && menuOpen && <button type="button" className="scrim" aria-label="Close menu" onClick={() => setMenuOpen(false)} />}

    <div className="column">
      <header className="topbar">
        {narrow && <button type="button" className="btn btn-sm" aria-expanded={menuOpen} aria-controls="sidebar" onClick={() => setMenuOpen((value) => !value)}>Menu</button>}
        <div className="topbar-title"><h1>{title}</h1><p className="muted">{SUBTITLES[view]}</p></div>
        <SafetyStrip status={safety} />
      </header>
      {notice && <div className={`notice notice-${notice.kind}`} role={notice.kind === "error" ? "alert" : "status"}>
        <span>{notice.text}</span>
        <button type="button" className="btn btn-sm" onClick={() => setNotice(null)}>Dismiss</button>
      </div>}
      {reminders.due.length > 0 && <div className="due" role="alert">
        {reminders.due.slice(0, 3).map((item) => <div className="due-item" key={item.id}>
          <p><strong>Reminder:</strong> {item.text} <span className="muted">(due {formatWhen(item.due_at)})</span></p>
          <button type="button" className="btn btn-sm" onClick={() => reminders.dismiss(item.id)}>Dismiss</button>
        </div>)}
        {reminders.due.length > 3 && <a href="#/reminders">{reminders.due.length - 3} more on the Reminders screen</a>}
      </div>}
      <main id="main" ref={mainRef} tabIndex={-1} className={`main${view === "chat" ? " main-chat" : ""}`}>{body}</main>
    </div>
  </div>;
}
