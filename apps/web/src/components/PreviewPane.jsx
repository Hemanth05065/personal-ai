import React, { useEffect, useRef, useState } from "react";
import { isPython, loadPyodideFiles, previewDocument } from "../preview.js";
import CopyButton from "./CopyButton.jsx";

// What the automatic check is doing, in the user's words.
const TEST_TEXT = {
  preparing: "Writing a sample input to test the program with…",
  testing: "Testing: playing it for a few seconds and watching for errors…",
  testingPython: "Testing: running the program with a sample input…",
  passed: "Check passed: no errors while loading or when keys were pressed.",
  passedPython: "Check passed: the program ran to the end with a sample input and no errors.",
  untested: "Couldn't fully test: the program needs input. Type some in the Input box below and run it.",
  fixing: "Errors found. Asking the coding model to fix them…",
  failed: "Still has errors after the automatic fixes. See the console below.",
};

/**
 * Runs code from a reply in a sandboxed frame beside the chat.
 * sandbox="allow-scripts" without allow-same-origin gives the page an opaque origin:
 * it can draw, animate and read the keyboard, but can't touch the app or its session.
 *
 * preview.test asks for the self-test; onTestDone(errors) gets every error it saw.
 */
export default function PreviewPane({ preview, testStatus, onTestDone, onClose }) {
  const frameRef = useRef(null);
  const [run, setRun] = useState(0); // bump to reload
  const [logs, setLogs] = useState([]);
  const logsRef = useRef([]);
  const [full, setFull] = useState(false);
  // Reload replays the page without the self-test, so it doesn't press keys while you play.
  const testing = Boolean(preview.test) && run === 0;
  // Python only: lines handed to input(), used when you press "Run with this input".
  const python = isPython(preview.lang);
  const [inputText, setInputText] = useState("");
  const [appliedInput, setAppliedInput] = useState("");
  const source = previewDocument(preview.lang, preview.code, testing, testing ? preview.input || "" : appliedInput);

  useEffect(() => {
    setRun(0);
    // Start the Input box with the coder's example input, if it gave one.
    setInputText(preview.input || "");
    setAppliedInput(preview.input || "");
  }, [preview]);
  useEffect(() => { logsRef.current = []; setLogs([]); }, [source, run]);

  useEffect(() => {
    function onMessage(event) {
      if (event.source !== frameRef.current?.contentWindow || !event.data?.__preview) return;
      if (event.data.needPyodide) {
        // The sandbox can't fetch from this computer, so hand it Python's files directly.
        const target = event.source;
        loadPyodideFiles()
          .then((files) => target.postMessage({ __pyodideFiles: files }, "*"))
          .catch((error) => target.postMessage({ __pyodideError: error.message }, "*"));
        return;
      }
      if (event.data.done) {
        if (testing) {
          const errors = [...new Set(logsRef.current.filter((item) => item.level === "error").map((item) => item.text))];
          const untested = logsRef.current.some((item) => item.level === "warn" && item.text.startsWith("Needs input to test properly"));
          onTestDone?.(errors.slice(0, 8), preview.code, preview.lang, untested);
        }
        return;
      }
      const entry = { level: String(event.data.level), text: String(event.data.text).slice(0, 2000) };
      logsRef.current = [...logsRef.current.slice(-199), entry];
      setLogs(logsRef.current);
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [testing, onTestDone, preview.code, preview.lang]);

  useEffect(() => {
    const onKey = (event) => { if (event.key === "Escape" && full) setFull(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [full]);

  const errors = logs.filter((item) => item.level === "error").length;

  return <section className={`run-pane${full ? " preview-full" : ""}`} aria-label="Code preview">
    <header className="preview-bar">
      <div className="preview-title">
        <h2>Output</h2>
        <p className="muted">{preview.title}</p>
      </div>
      <div className="row-actions">
        <CopyButton text={preview.code} label="Copy the whole code" />
        <button type="button" className="btn btn-sm" onClick={() => setRun((value) => value + 1)}>{python ? "Run again" : "Reload"}</button>
        <button type="button" className="btn btn-sm" aria-pressed={full} onClick={() => setFull((value) => !value)}>{full ? "Exit full screen" : "Full screen"}</button>
        <button type="button" className="btn btn-sm" onClick={onClose}>Close</button>
      </div>
    </header>
    {testStatus && <p className={`preview-test test-${testStatus}`} role="status">{TEST_TEXT[python && (testStatus === "passed" || testStatus === "testing") ? `${testStatus}Python` : testStatus]}</p>}
    <iframe key={`${run}-${source.length}`} ref={frameRef} className="preview-frame" title="Output of the code" srcDoc={source}
      sandbox={testing ? "allow-scripts" : "allow-scripts allow-modals allow-pointer-lock"} referrerPolicy="no-referrer"
      onLoad={() => frameRef.current?.focus()} />
    {python && <form className="preview-input" onSubmit={(event) => { event.preventDefault(); setAppliedInput(inputText); setRun((value) => value + 1); }}>
      <label htmlFor="python-input">Input for the program (one line per <code>input()</code>)</label>
      <textarea id="python-input" rows={2} value={inputText} onChange={(event) => setInputText(event.target.value)} placeholder={"5\nAlice"} />
      <button type="submit" className="btn btn-sm">Run with this input</button>
    </form>}
    <details className="preview-console" open={errors > 0}>
      <summary>Console{logs.length ? ` (${logs.length}${errors ? `, ${errors} error${errors === 1 ? "" : "s"}` : ""})` : ""}</summary>
      {logs.length
        ? <ol>{logs.map((item, index) => <li key={index} className={`log-${item.level}`}>{item.text}</li>)}</ol>
        : <p className="muted">{python ? "Nothing logged yet." : "Nothing logged yet. Click the output to give it the keyboard."}</p>}
    </details>
  </section>;
}
