import React, { useEffect, useRef, useState } from "react";
import Markdown from "../components/Markdown.jsx";

const WHO = { user: "You", assistant: "Assistant", error: "Problem" };

export default function ChatView({ chat, notify, modelReady }) {
  const { messages, busy, send } = chat;
  const [input, setInput] = useState("");
  const [listening, setListening] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    endRef.current?.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "end" });
  }, [messages, busy]);

  function submit(event) {
    event.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    send(text);
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
    <div className="messages" role="log" aria-live="polite" aria-label="Conversation">
      <div className="messages-inner">
        {!messages.length && !busy && <div className="intro">
          <h2>What would you like to work on?</h2>
          <p className="muted">Everything you type stays on this computer.</p>
          {modelReady === false && <p className="field-error" role="alert">Ollama isn’t running, so replies will fail. Start Ollama, then send your message.</p>}
        </div>}
        {messages.map((message, index) => <article className={`msg msg-${message.role}`} key={message.id || index}>
          <p className="msg-who">{WHO[message.role] || message.role}</p>
          {message.role === "assistant" ? <Markdown text={message.content} /> : <p className="msg-text">{message.content}</p>}
          {message.role === "assistant" && <button type="button" className="btn btn-quiet btn-sm" onClick={() => speak(message.content)}>Read aloud</button>}
        </article>)}
        {busy && <article className="msg msg-assistant" aria-busy="true">
          <p className="msg-who">Assistant</p>
          <div className="skeleton" role="status" aria-label="The assistant is thinking"><span /><span /></div>
        </article>}
        <div ref={endRef} />
      </div>
    </div>
    <form className="composer" onSubmit={submit}>
      <textarea aria-label="Message" rows={2} value={input} placeholder="Message your assistant" onChange={(event) => setInput(event.target.value)}
        onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) submit(event); }} />
      <div className="composer-actions">
        <button type="button" className="btn" onClick={dictate} aria-pressed={listening}>{listening ? "Listening..." : "Dictate"}</button>
        <button type="submit" className="btn btn-primary" disabled={busy || !input.trim()}>Send</button>
      </div>
      <p className="muted composer-hint">Enter sends, Shift+Enter adds a line. Replies come from Ollama on this machine.</p>
    </form>
  </div>;
}
