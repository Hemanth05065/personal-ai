import React, { useCallback, useEffect, useRef, useState } from "react";
import { request } from "../api.js";
import Markdown from "../components/Markdown.jsx";
import ToolCard from "../components/ToolCard.jsx";
import PreviewPane from "../components/PreviewPane.jsx";
import { bestRunnable, exampleInput, fixRequest, isPython } from "../preview.js";

const WHO = { user: "You", assistant: "Assistant", error: "Problem" };
const MAX_FIXES = 3;

function parseTool(content) {
  try { return JSON.parse(content); } catch { return null; }
}

function Thinking() {
  return <div className="skeleton" role="status" aria-label="The assistant is thinking"><span /><span /></div>;
}

export default function ChatView({ chat, notify, modelReady, refreshSafety }) {
  const { messages, busy, send } = chat;
  // Do-it mode: the user's own commands run without an approval click (saved per user on the server).
  const [doIt, setDoIt] = useState(null);
  useEffect(() => { request("/settings/me").then((s) => setDoIt(s.autopilot)).catch(() => setDoIt(false)); }, []);
  async function toggleDoIt() {
    try {
      const saved = await request("/settings/me", { method: "PUT", body: JSON.stringify({ autopilot: !doIt }) });
      setDoIt(saved.autopilot);
      notify(saved.autopilot ? "Do-it mode is on. File changes you ask for run straight away, and each one can be undone." : "Do-it mode is off. File changes wait for your approval.");
    } catch (error) { notify(error.message, "error"); }
  }
  // Code preview beside the chat: { lang, code, title, test }.
  const [preview, setPreview] = useState(null);
  const [testStatus, setTestStatus] = useState(null); // preparing | testing | passed | untested | fixing | failed
  const openPreview = (lang, code, title = "Code from the chat") => { setTestStatus(null); setPreview({ lang, code, title }); };
  // Self-check loop: a coding reply is run and played automatically; errors go back to the
  // coder as a visible message, at most MAX_FIXES times per request you send.
  const fixAttempts = useRef(0);
  const autoOpened = useRef(null);
  const latestJob = useRef(null);
  useEffect(() => {
    // Only live replies carry `coding`, so reopening an old conversation doesn't start a test.
    const last = messages[messages.length - 1];
    if (!last || last.role !== "assistant" || last.streaming || !last.coding || autoOpened.current === last) return;
    autoOpened.current = last;
    const block = bestRunnable(last.content);
    if (!block) return;
    const title = fixAttempts.current ? `Fixed version (attempt ${fixAttempts.current})` : "Latest coding reply";
    const given = exampleInput(last.content);
    // Only the newest reply's test may open the panel (no effect cleanup: StrictMode's
    // second run would cancel the first and, seeing autoOpened, never start another).
    const job = {};
    latestJob.current = job;
    (async () => {
      let input = given;
      // A Python program that reads input can only be tested with input in its own format.
      // The coders rarely write an example, so ask the fast coder for one.
      if (!input && isPython(block.lang) && /\binput\s*\(/.test(block.code)) {
        setTestStatus("preparing");
        notify("Writing a sample input so the program can be tested…");
        try {
          input = (await request("/chat/example-input", { method: "POST", body: JSON.stringify({ code: block.code, big: last.big === true }) })).input;
        } catch { /* test without input; it reports "needs input" */ }
        notify(null);
      }
      if (latestJob.current !== job) return;
      setTestStatus("testing");
      setPreview({ ...block, test: true, input, title });
    })();
  }, [messages, notify]);
  // A new (empty) chat starts without the previous chat's Output panel.
  useEffect(() => {
    if (!messages.length) { setPreview(null); setTestStatus(null); }
  }, [messages.length]);
  const onTestDone = useCallback((errors, code, lang, untested = false) => {
    if (!errors.length) { setTestStatus(untested ? "untested" : "passed"); return; }
    if (fixAttempts.current >= MAX_FIXES) { setTestStatus("failed"); return; }
    fixAttempts.current += 1;
    setTestStatus("fixing");
    send(fixRequest(errors, fixAttempts.current, MAX_FIXES, code, lang));
  }, [send]);
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
    notify={notify} onDecided={refreshSafety} onRun={openPreview} />;

  async function submit(event) {
    event.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    fixAttempts.current = 0; // a new request gets its own fix attempts
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

  return <div className={`chat-wrap${preview ? " has-preview" : ""}`}>
  <div className="chat">
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
            <p className="msg-who">{WHO[message.role] || message.role}{message.coding && <span className="msg-tag">{message.big ? "Big coding model (slower, more careful)" : "Coding model"}</span>}</p>
            {tools.map(card)}
            {message.role === "assistant"
              ? (message.streaming && !message.content
                ? (tools.length ? null : <Thinking />)
                : message.content && <Markdown text={message.content} onRun={message.streaming ? undefined : openPreview} />)
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
        {doIt !== null && <button type="button" className={`btn btn-sm do-it${doIt ? " is-on" : ""}`} aria-pressed={doIt} onClick={toggleDoIt}>Do-it mode: {doIt ? "On" : "Off"}</button>}
        <button type="button" className="btn" onClick={dictate} aria-pressed={listening}>{listening ? "Listening..." : "Dictate"}</button>
        {busy
          ? <button type="button" className="btn btn-primary" onClick={chat.stop}>Stop</button>
          : <button type="submit" className="btn btn-primary" disabled={!input.trim()}>Send</button>}
      </div>
      <p className="muted composer-hint">{doIt
        ? "Do-it mode: file changes you ask for run straight away; use Undo on a card to reverse one. If a task reads your files first, it still asks."
        : "Enter sends, Shift+Enter adds a line. File changes wait for your approval."}</p>
    </form>
  </div>
  {preview && <PreviewPane preview={preview} testStatus={testStatus} onTestDone={onTestDone}
    onClose={() => { setPreview(null); setTestStatus(null); }} />}
  </div>;
}
