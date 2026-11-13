import { useCallback, useEffect, useRef, useState } from "react";
import { request, json } from "./api.js";

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

const VIEW_IDS = ["chat", "research", "memory", "files", "tasks", "security"];

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

  const refreshConversations = useCallback(async () => {
    try { setConversations(await request("/chat/conversations")); } catch { /* the health indicator reports connection problems */ }
  }, []);

  useEffect(() => { if (enabled) refreshConversations(); }, [enabled, refreshConversations]);

  const newChat = useCallback(() => { setConversationId(null); setMessages([]); }, []);

  const openConversation = useCallback(async (id) => {
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
    setMessages((items) => [...items, { role: "user", content: text }]);
    setBusy(true);
    try {
      const data = await request("/chat", { method: "POST", body: json({ message: text, conversation_id: conversationId }) });
      setConversationId(data.conversation_id);
      setMessages((items) => [...items, { role: "assistant", content: data.message }]);
      await refreshConversations();
    } catch (error) {
      setMessages((items) => [...items, { role: "error", content: error.message }]);
    } finally { setBusy(false); }
  }, [conversationId, refreshConversations]);

  return { conversations, conversationId, messages, busy, newChat, openConversation, deleteConversation, send };
}
