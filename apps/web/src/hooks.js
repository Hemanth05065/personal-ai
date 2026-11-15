import { useCallback, useEffect, useRef, useState } from "react";
import { request, streamEvents } from "./api.js";

/** Load data once and on demand. status: loading | ready | error. Data is kept across reloads. */
export function useLoad(loader, deps = []) {
  const [state, setState] = useState({ status: "loading", data: null, error: "" });
  const [tick, setTick] = useState(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    let live = true;
    loaderRef.current()
      .then((data) => { if (live) setState({ status: "ready", data, error: "" }); })
      .catch((error) => { if (live) setState((current) => ({ status: "error", data: current.data, error: error.message })); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((value) => value + 1), []);
  return { ...state, reload };
}

export function useMedia(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const list = window.matchMedia(query);
    const onChange = () => setMatches(list.matches);
    list.addEventListener("change", onChange);
    onChange();
    return () => list.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

const VIEW_IDS = ["chat", "research", "memory", "reminders", "files", "tasks", "security"];

export function useRoute() {
  const read = () => {
    const id = window.location.hash.replace(/^#\/?/, "");
    return VIEW_IDS.includes(id) ? id : "chat";
  };
  const [view, setView] = useState(read);
  useEffect(() => {
    const onChange = () => setView(read());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return view;
}

export function goTo(view) {
  window.location.hash = `#/${view}`;
}

/** Conversation list and the active chat thread. */
export function useChat(notify, enabled) {
  const [conversations, setConversations] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef(null);

  const refreshConversations = useCallback(async () => {
    try { setConversations(await request("/chat/conversations")); } catch { /* the health indicator reports connection problems */ }
  }, []);

  useEffect(() => { if (enabled) refreshConversations(); }, [enabled, refreshConversations]);

  /** Stop the reply being streamed. The server keeps whatever text had arrived. */
  const stop = useCallback(() => { abortRef.current?.abort(); }, []);

  const newChat = useCallback(() => { stop(); setConversationId(null); setMessages([]); }, [stop]);

  const openConversation = useCallback(async (id) => {
    stop();
    try {
      const conversation = await request(`/chat/conversations/${id}`);
      setConversationId(id);
      setMessages(conversation.messages);
    } catch (error) { notify(error.message, "error"); }
  }, [notify]);

  const deleteConversation = useCallback(async (id) => {
    try {
      await request(`/chat/conversations/${id}`, { method: "DELETE" });
      if (id === conversationId) newChat();
      await refreshConversations();
      notify("Conversation deleted.");
    } catch (error) { notify(error.message, "error"); }
  }, [conversationId, newChat, notify, refreshConversations]);

  const send = useCallback(async (text) => {
    const controller = new AbortController();
    abortRef.current = controller;
    // Change only the reply this request is writing (the last message), never another thread's.
    const updateReply = (change) => setMessages((items) => {
      const last = items[items.length - 1];
      if (!last || last.role !== "assistant" || !last.streaming) return items;
      const next = change(last);
      return next ? [...items.slice(0, -1), next] : items.slice(0, -1);
    });
    // A finished reply keeps its text and any tool cards; an empty one is dropped.
    const settle = (reply, extra = {}) => (reply.content || reply.tools.length
      ? { role: "assistant", content: reply.content, tools: reply.tools, coding: reply.coding, ...extra }
      : null);
    setMessages((items) => [...items, { role: "user", content: text }]);
    setBusy(true);
    try {
      const result = await streamEvents("/chat/stream", { message: text, conversation_id: conversationId }, (event) => {
        if (event.type === "start") {
          setConversationId(event.conversation_id);
          setMessages((items) => [...items, { role: "assistant", content: "", tools: [], streaming: true, coding: event.coding === true }]);
        } else if (event.type === "delta") {
          updateReply((reply) => ({ ...reply, content: reply.content + event.text }));
        } else if (event.type === "tool") {
          updateReply((reply) => ({ ...reply, tools: [...reply.tools, event.tool] }));
        } else if (event.type === "done") {
          updateReply((reply) => settle(reply, { id: event.message_id }));
        } else if (event.type === "error") {
          updateReply((reply) => settle(reply));
          setMessages((items) => [...items, { role: "error", content: event.detail }]);
        }
      }, controller.signal);
      if (result.aborted) updateReply((reply) => settle(reply, { stopped: true }));
      await refreshConversations();
    } catch (error) {
      updateReply((reply) => settle(reply));
      setMessages((items) => [...items, { role: "error", content: error.message }]);
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setBusy(false);
    }
  }, [conversationId, refreshConversations]);

  return { conversations, conversationId, messages, busy, newChat, openConversation, deleteConversation, send, stop };
}

const SHOWN_KEY = "assistant_reminders_alerted";

function readShown() {
  try { return new Set(JSON.parse(localStorage.getItem(SHOWN_KEY) || "[]")); } catch { return new Set(); }
}

function saveShown(shown) {
  try { localStorage.setItem(SHOWN_KEY, JSON.stringify([...shown].slice(-200))); } catch { /* storage unavailable: may alert twice */ }
}

/**
 * Your reminders, polled every 30 s and whenever the tab becomes visible.
 * A reminder that has gone off raises one system notification (if allowed);
 * reminders that fired while the app was closed alert on the next open.
 */
export function useReminders(enabled, notify) {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const shown = useRef(null);

  const alertNew = useCallback((list) => {
    if (!shown.current) shown.current = readShown();
    const fresh = list.filter((item) => item.status === "fired" && !shown.current.has(item.id));
    if (!fresh.length) return;
    fresh.forEach((item) => shown.current.add(item.id));
    saveShown(shown.current);
    if ("Notification" in window && Notification.permission === "granted") {
      fresh.forEach((item) => {
        const note = new Notification("Reminder", { body: item.text, tag: item.id });
        note.onclick = () => { window.focus(); window.location.hash = "#/reminders"; note.close(); };
      });
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      const list = await request("/reminders");
      setItems(list); setStatus("ready"); setError("");
      alertNew(list);
    } catch (problem) { setError(problem.message); setStatus("error"); }
  }, [alertNew]);

  useEffect(() => {
    if (!enabled) return undefined;
    refresh();
    const timer = setInterval(refresh, 30000);
    const onVisible = () => { if (document.visibilityState === "visible") refresh(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", onVisible); };
  }, [enabled, refresh]);

  const act = useCallback(async (work, done) => {
    try { await work(); if (done) notify(done); await refresh(); return true; }
    catch (problem) { notify(problem.message, "error"); return false; }
  }, [notify, refresh]);

  return {
    items, status, error, refresh,
    due: items.filter((item) => item.status === "fired"),
    create: (text, dueAt) => act(() => request("/reminders", { method: "POST", body: JSON.stringify({ text, due_at: dueAt }) }), "Reminder set."),
    dismiss: (id) => act(() => request(`/reminders/${id}/dismiss`, { method: "POST" })),
    cancel: (id) => act(() => request(`/reminders/${id}`, { method: "DELETE" }), "Reminder cancelled."),
  };
}
