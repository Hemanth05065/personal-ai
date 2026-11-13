import React, { useEffect, useRef, useState } from "react";
import { request } from "../api.js";
import Markdown from "../components/Markdown.jsx";
import ToolCard from "../components/ToolCard.jsx";

const WHO = { user: "You", assistant: "Assistant", error: "Problem" };

function parseTool(content) {
  try { return JSON.parse(content); } catch { return null; }
}

function Thinking() {
  return <div className="skeleton" role="status" aria-label="The assistant is thinking"><span /><span /></div>;
}

export default function ChatView({ chat, notify, modelReady, refreshSafety }) {
  const { messages, busy, send } = chat;
  const [input, setInput] = useState("");
  const [listening, setListening] = useState(false);
  const endRef = useRef(null);

  // The assistant's reply bubble already exists once streaming starts.
  const waitingOnReply = messages[messages.length - 1]?.streaming === true;

  useEffect(() => {
    // Smooth scrolling on every streamed fragment would lag behind the text.
    const calm = busy || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    endRef.current?.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "end" });
  }, [messages, busy]);

  // Current approval status for every proposal on screen, so reopened chats aren't stale.
  const approvalIds = messages.flatMap((message) => (message.role === "tool_event"
    ? [parseTool(message.content)?.approval_id]
    : (message.tools || []).map((tool) => tool.approval_id))).filter(Boolean);
  const approvalKey = approvalIds.join(",");
  const [approvalStatus, setApprovalStatus] = useState({});
  useEffect(() => {
    if (!approvalKey || busy) return;
    let live = true;
    request("/approvals")
      .then((items) => { if (live) setApprovalStatus(Object.fromEntries(items.map((item) => [item.id, item.status]))); })
      .catch(() => { /* cards fall back to the status saved with them */ });
    return () => { live = false; };
  }, [approvalKey, busy]);

  const card = (tool) => <ToolCard key={tool.id} tool={tool} approvalStatus={approvalStatus[tool.approval_id]}
    notify={notify} onDecided={refreshSafety} />;

  async function submit(event) {
    event.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    await send(text);
    refreshSafety(); // a proposal changes the approvals count in the top bar
  }

  function dictate() {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) { notify("Dictation isn’t supported by this browser.", "error"); return; }
    const recognition = new Recognition();
    recognition.lang = navigator.language || "en-US";
    recognition.interimResults = false;
    recognition.onstart = () => setListening(true);
    recognition.onend = () => setListening(false);
    recognition.onerror = (event) => { setListening(false); notify(`Dictation failed: ${event.error}`, "error"); };
    recognition.onresult = (event) => setInput((current) => `${current}${current ? " " : ""}${event.results[0][0].transcript}`);
    recognition.start();
  }

  function speak(text) {
    if (!("speechSynthesis" in window)) { notify("Reading aloud isn’t supported by this browser.", "error"); return; }
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  }

  return <div className="chat">
    {/* aria-busy while streaming: screen readers announce the finished reply once, not every fragment. */}
    <div className="messages" role="log" aria-live="polite" aria-busy={busy} aria-label="Conversation">
      <div className="messages-inner">
        {!messages.length && !busy && <div className="intro">
          <h2>What would you like to work on?</h2>
          <p className="muted">Everything you type stays on this computer.</p>
          {modelReady === false && <p className="field-error" role="alert">Ollama isn’t running, so replies will fail. Start Ollama, then send your message.</p>}
        </div>}
        {messages.map((message, index) => {
          const key = message.id || index;
          if (message.role === "tool_event") {
            // A saved proposal from an earlier turn.
            const tool = parseTool(message.content);
            return tool && <article className="msg msg-assistant" key={key}>
              <p className="msg-who">Assistant action</p>
              {card(tool)}
            </article>;
          }
          const tools = message.tools || [];
          return <article className={`msg msg-${message.role}`} key={key}>
            <p className="msg-who">{WHO[message.role] || message.role}</p>
            {tools.map(card)}
            {message.role === "assistant"
              ? (message.streaming && !message.content
                ? (tools.length ? null : <Thinking />)
                : message.content && <Markdown text={message.content} />)
              : <p className="msg-text">{message.content}</p>}
            {message.stopped && <p className="muted">Stopped. The text above was kept.</p>}
            {message.role === "assistant" && !message.streaming && message.content && <button type="button" className="btn btn-quiet btn-sm" onClick={() => speak(message.content)}>Read aloud</button>}
          </article>;
        })}
        {busy && !waitingOnReply && <article className="msg msg-assistant">
          <p className="msg-who">Assistant</p>
          <Thinking />
        </article>}
        <div ref={endRef} />
      </div>
    </div>
    <form className="composer" onSubmit={submit}>
      <textarea aria-label="Message" rows={2} value={input} placeholder="Message your assistant" onChange={(event) => setInput(event.target.value)}
        onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) submit(event); }} />
      <div className="composer-actions">
        <button type="button" className="btn" onClick={dictate} aria-pressed={listening}>{listening ? "Listening..." : "Dictate"}</button>
        {busy
          ? <button type="button" className="btn btn-primary" onClick={chat.stop}>Stop</button>
          : <button type="submit" className="btn btn-primary" disabled={!input.trim()}>Send</button>}
      </div>
      <p className="muted composer-hint">Enter sends, Shift+Enter adds a line. Replies come from Ollama on this machine.</p>
    </form>
  </div>;
}
