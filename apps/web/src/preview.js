// Helpers for the code preview panel. Code written by the model runs only inside a
// sandboxed iframe with no same-origin access, so it can't reach the app, its cookies or its API.

const RUNNABLE = new Set(["html", "htm", "xhtml", "svg", "js", "javascript", "python", "py", "python3"]);
const PYTHON = new Set(["python", "py", "python3"]);

export const isPython = (lang) => PYTHON.has((lang || "").toLowerCase());

/** Can this fenced code block run in the preview? */
export function isRunnable(lang, code) {
  const language = (lang || "").toLowerCase();
  if (RUNNABLE.has(language)) return true;
  // Unlabelled blocks that are clearly a whole web page.
  return !language && /^\s*(<!doctype html|<html[\s>])/i.test(code);
}

/** Fenced code blocks in Markdown text, as { lang, code }. */
export function codeBlocks(text) {
  const blocks = [];
  const fence = /^\s*```([\w+#-]*)[^\n]*\n([\s\S]*?)^\s*```/gm;
  let match;
  while ((match = fence.exec(text || ""))) blocks.push({ lang: match[1], code: match[2] });
  return blocks;
}

/** The block a "Run" should show for a whole reply: the biggest runnable one. */
export function bestRunnable(text) {
  return codeBlocks(text)
    .filter((block) => isRunnable(block.lang, block.code))
    .sort((a, b) => b.code.length - a.code.length)[0] || null;
}

// One line on purpose: injected without a newline, so error line numbers still match the code.
const BRIDGE = "<script>(function(){function send(level,args){try{parent.postMessage({__preview:true,level:level,text:Array.prototype.map.call(args,function(a){if(a instanceof Error)return a.message;if(typeof a==='string')return a;try{return JSON.stringify(a)}catch(e){return String(a)}}).join(' ')},'*')}catch(e){}}['log','info','warn','error'].forEach(function(level){var original=console[level];console[level]=function(){send(level,arguments);original.apply(console,arguments)}});window.addEventListener('error',function(e){send('error',[e.message+(e.lineno?' (line '+e.lineno+')':'')])});window.addEventListener('unhandledrejection',function(e){send('error',['Unhandled promise rejection: '+((e.reason&&e.reason.message)||e.reason)])})})();</script>";

// Self-test, also one line: once the page has loaded, play it like a person would for a few
// seconds (click it, press arrows, space and Enter), then report back. Errors that only happen
// on input or after a timer (a game loop) show up this way, not just load-time crashes.
export const TEST_MS = 6000;
const TEST = "<script>(function(){var keys=[['ArrowLeft','ArrowLeft',37],['ArrowRight','ArrowRight',39],['ArrowUp','ArrowUp',38],['ArrowDown','ArrowDown',40],[' ','Space',32],['Enter','Enter',13],['a','KeyA',65],['d','KeyD',68],['w','KeyW',87],['s','KeyS',83]];function press(k){['keydown','keyup'].forEach(function(type){var e=new KeyboardEvent(type,{key:k[0],code:k[1],keyCode:k[2],which:k[2],bubbles:true,cancelable:true});(document.activeElement||document.body||document).dispatchEvent(e)})}function poke(){var target=document.querySelector('canvas,button,body');if(target){var r=target.getBoundingClientRect();['mousedown','mouseup','click'].forEach(function(type){target.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,clientX:r.left+r.width/2,clientY:r.top+r.height/2}))})}}window.addEventListener('load',function(){setTimeout(function(){try{poke()}catch(e){}var i=0;var timer=setInterval(function(){try{press(keys[i%keys.length])}catch(e){}if(++i>=30)clearInterval(timer)},80)},1200);setTimeout(function(){parent.postMessage({__preview:true,done:true},'*')}," + TEST_MS + ")})})();</script>";

/**
 * Turn a code block into a full page for the iframe, with console output forwarded to the panel.
 * selfTest adds the automatic play-through that reports {done: true} when it's finished.
 */
export function previewDocument(lang, code, selfTest = false, input = "") {
  if (isPython(lang)) return pythonDocument(code, selfTest, input);
  const inject = selfTest ? BRIDGE + TEST : BRIDGE;
  const language = (lang || "").toLowerCase();
  if (language === "js" || language === "javascript") {
    return `<!doctype html><html><head><meta charset="utf-8">${inject}</head><body><script>${code.replace(/<\/script/gi, "<\\/script")}</script></body></html>`;
  }
  if (/<head[^>]*>/i.test(code)) return code.replace(/<head[^>]*>/i, (head) => head + inject);
  if (/<html[^>]*>/i.test(code)) return code.replace(/<html[^>]*>/i, (html) => html + inject);
  return inject + code;
}

/** The message that asks the coder to fix what the self-test found. */
export function fixRequest(errors, attempt, maxAttempts, code = "", lang = "html") {
  const python = isPython(lang);
  // Line numbers match the code (the injected scripts add no lines), so quote the failing line.
  const rows = code.split("\n");
  const list = errors.map((error) => {
    const line = Number(error.match(/\(line (\d+)\)$/)?.[1]);
    const source = line && rows[line - 1]?.trim();
    return source ? `- ${error}\n  That line is: ${source.slice(0, 200)}` : `- ${error}`;
  }).join("\n");
  const what = python ? "Python code" : "HTML code in the browser";
  const check = python
    ? "Use only the Python standard library. If the program reads input(), handle bad or missing input instead of crashing."
    : "Also check that every function you call actually exists and that everything the user should see is drawn.";
  const fence = python ? "python" : "html";
  return `Auto-fix (attempt ${attempt} of ${maxAttempts}): I ran your ${what} and it failed with these errors:\n${list}\n\nFind the cause of each error and fix it. ${check} Reply with the complete corrected program in a single \`\`\`${fence} code block.`;
}

// ---------- Python ----------
// Python runs on Pyodide (CPython compiled to WebAssembly) in a Worker inside the sandboxed
// frame. The worker is a separate thread, so an endless loop can't freeze the app, and the
// frame stops it after a time limit. The browser won't let the sandbox fetch anything from
// this computer, so the app hands it Pyodide's files by message; the frame's content policy
// then blocks every network request, so the program can't reach the internet either.
export const PYTHON_TEST_INPUT = ["5", "3", "hello", "2", "1", "10", "y", "n", "4", "0"];
const PY_LIMIT_MS = 60000;
const PY_TEST_LIMIT_MS = 20000;
const PYODIDE_FILES = ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"];

let pyodideFiles = null;
/** Pyodide's files, fetched once from this app and kept for later runs (about 14 MB). */
export function loadPyodideFiles() {
  pyodideFiles ||= Promise.all(PYODIDE_FILES.map(async (name) => {
    const response = await fetch(`/pyodide/${name}`);
    if (!response.ok) throw new Error(`Couldn't load ${name} (${response.status}).`);
    return [name, await response.arrayBuffer()];
  })).then(Object.fromEntries).catch((error) => { pyodideFiles = null; throw error; });
  return pyodideFiles;
}

// A classic worker (module workers can't start in an opaque-origin sandbox). Pyodide refuses
// classic workers only because it would load packages with importScripts; it never needs to
// here, so that's switched off. fetch serves Pyodide's own files and nothing else.
const PY_WORKER = `self.importScripts = () => { throw new Error("importScripts is turned off"); };
self.onmessage = async (event) => {
  const { files, code, input } = event.data;
  const types = { "pyodide.asm.wasm": "application/wasm", "python_stdlib.zip": "application/zip", "pyodide-lock.json": "application/json" };
  self.fetch = async (url) => {
    const name = String(url).split("/").pop().split("?")[0];
    if (files[name]) return new Response(files[name], { headers: { "Content-Type": types[name] || "application/octet-stream" } });
    throw new TypeError("Network access is turned off in the sandbox.");
  };
  const moduleUrl = (name) => URL.createObjectURL(new Blob([files[name]], { type: "text/javascript" }));
  try {
    const asm = await import(moduleUrl("pyodide.asm.mjs"));
    const { loadPyodide } = await import(moduleUrl("pyodide.mjs"));
    const lines = input.slice();
    const pyodide = await loadPyodide({
      indexURL: "https://pyodide.invalid/",
      createPyodideModule: asm.default,
      lockFileContents: new TextDecoder().decode(files["pyodide-lock.json"]),
    });
    // Raw writes, not whole lines, so an input() prompt shows before the answer is typed in.
    const stream = (kind) => {
      const decoder = new TextDecoder();
      return { write: (bytes) => { postMessage({ kind, text: decoder.decode(bytes, { stream: true }) }); return bytes.length; } };
    };
    pyodide.setStdout(stream("out"));
    pyodide.setStderr(stream("err"));
    pyodide.setStdin({ stdin: () => {
      if (!lines.length) return undefined;
      const line = lines.shift();
      postMessage({ kind: "in", text: line + "\\n" }); // echo it, like a terminal
      return line;
    } });
    postMessage({ kind: "ready" });
    const flushOutput = () => { try { pyodide.runPython("import sys\\nsys.stdout.flush()\\nsys.stderr.flush()"); } catch {} };
    try {
      await pyodide.runPythonAsync(code);
    } finally {
      flushOutput(); // print(..., end="") at the very end would otherwise never show
    }
    postMessage({ kind: "done" });
  } catch (error) {
    postMessage({ kind: "fail", text: String((error && error.message) || error) });
  }
};`;

// The page script that drives the worker. Plain text with placeholders, filled in below.
const PY_PAGE = `
const out = document.getElementById("out");
const status = document.getElementById("status");
function write(text, kind) { const span = document.createElement("span"); if (kind) span.className = kind; span.textContent = text; out.appendChild(span); }
function add(text, kind) { flush(); write((out.textContent && !out.textContent.endsWith("\\n") ? "\\n" : "") + text + "\\n", kind); }
// Program output arrives in pieces; the console gets it a whole line at a time.
const pending = { out: "", err: "" };
const log = { out: (line) => console.log(line), err: (line) => console.warn(line) };
function feed(kind, text) {
  write(text, kind === "out" ? "" : kind === "err" ? "warn" : "in");
  if (kind === "in") {
    // Keep the question and its answer on one console line: "How many? 12".
    console.log(pending.out + text.replace(/\\n$/, ""));
    pending.out = "";
    return;
  }
  const parts = (pending[kind] + text).split("\\n");
  pending[kind] = parts.pop();
  parts.forEach(log[kind]);
}
function flush() { for (const kind of Object.keys(pending)) { if (pending[kind]) log[kind](pending[kind]); pending[kind] = ""; } }
let finished = false;
let worker = null;
let timer = null;
function finish(text) {
  if (finished) return;
  finished = true;
  clearTimeout(timer);
  if (worker) worker.terminate();
  status.textContent = text;
  parent.postMessage({ __preview: true, done: true }, "*");
}
function fail(message, label) { add(message, "err"); console.error(message); finish(label); }
function start(files) {
  worker = new Worker(URL.createObjectURL(new Blob([__WORKER__], { type: "text/javascript" })));
  timer = setTimeout(() => fail("Stopped: the program was still running after __SECONDS__ seconds. It may have an endless loop or be waiting for more input.", "Stopped (time limit)"), __LIMIT__);
  worker.onmessage = (event) => {
    const { kind, text } = event.data;
    if (kind === "ready") status.textContent = __RUNNING__;
    else if (kind === "out" || kind === "err" || kind === "in") feed(kind, text);
    else if (kind === "done") { add("[Program finished]", "note"); finish("Finished"); }
    else if (kind === "fail") {
      // The traceback from the user's own code down, without Pyodide's internal frames.
      const begin = text.search(/File "<exec>"/);
      add(begin >= 0 ? "Traceback (most recent call last):\\n  " + text.slice(begin).trim() : text.trim(), "err");
      const last = text.trim().split("\\n").filter(Boolean).pop() || "Python error";
      const lines = [...text.matchAll(/File "<exec>", line (\\d+)/g)];
      console.error(last + (lines.length ? " (line " + lines[lines.length - 1][1] + ")" : ""));
      finish("Failed with an error");
    }
  };
  worker.onerror = (event) => fail("Python could not start: " + (event.message || "unknown error"), "Could not start");
  worker.postMessage({ files, code: __CODE__, input: __INPUT__ });
}
window.addEventListener("message", (event) => {
  if (event.source !== parent || !event.data) return;
  if (event.data.__pyodideFiles) start(event.data.__pyodideFiles);
  else if (event.data.__pyodideError) fail("Python could not start: " + event.data.__pyodideError, "Could not start");
});
parent.postMessage({ __preview: true, needPyodide: true }, "*");
`;

// Keeps "</script>" inside a string from closing the page's script tag.
const embed = (value) => JSON.stringify(value).replace(/</g, "\\u003c");

/** Lines typed in the Input box, one per input() call. */
export function inputLines(text) {
  const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
  if (lines[lines.length - 1] === "") lines.pop();
  return lines;
}

function pythonDocument(code, selfTest, input) {
  const limit = selfTest ? PY_TEST_LIMIT_MS : PY_LIMIT_MS;
  const policy = "default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval' blob:; worker-src blob:; connect-src 'none'; style-src 'unsafe-inline'";
  const fill = {
    __WORKER__: embed(PY_WORKER),
    __SECONDS__: String(limit / 1000),
    __LIMIT__: String(limit),
    __RUNNING__: embed(selfTest ? "Running (automatic test with sample input)…" : "Running…"),
    __CODE__: embed(code),
    __INPUT__: embed(selfTest ? PYTHON_TEST_INPUT : inputLines(input)),
  };
  // A function replacer, so "$&" and friends in the user's code stay literal.
  const script = PY_PAGE.replace(/__[A-Z]+__/g, (key) => fill[key] ?? key);
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${policy}">${BRIDGE}<style>
body { margin: 0; background: #0b0b0b; color: #f2f2f2; font: 14px/1.55 ui-monospace, "Cascadia Code", Consolas, monospace; }
#status { position: sticky; top: 0; padding: 8px 14px; background: #1a1a1a; color: #bdbdbd; border-bottom: 1px solid #333; }
#out { margin: 0; padding: 12px 14px; white-space: pre-wrap; overflow-wrap: anywhere; }
.err { color: #ff8f8f; } .warn { color: #e6c07b; } .note { color: #9a9a9a; } .in { color: #8fd3ff; text-decoration: underline; }
</style></head><body><div id="status">Starting Python…</div><pre id="out"></pre><script>${script}</script></body></html>`;
}
