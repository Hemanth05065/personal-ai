// The evaluation harness's "browser half": the same code paths the web app uses, from Node.
//
//   node --permission --allow-fs-read=<repo> eval/runner.mjs < request.json > response.json
//
// One JSON request on stdin, one JSON response on stdout:
//   {"op": "run", "code", "input": [lines], "selfTest": bool}
//       Runs Python on Pyodide (the Output panel's runtime: Python 3.14, standard library
//       only) and judges it with the app's own self-test rules from apps/web/src/preview.js.
//   {"op": "extract", "text"}     -> the reply's runnable code block and example input
//   {"op": "fix", "errors", "attempt", "max", "code", "lang"} -> the app's auto-fix message
//
// Model-written code runs here, so run_eval.py starts this with Node's permission model:
// file reads limited to the repository, no file writes, no child processes, no workers.
// Node's permission model does not cover the network. Endless loops are handled by the
// caller's timeout, which kills this process.

import { constants as fsConstants, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import {
  bestRunnable,
  exampleInput,
  fixRequest,
  NEEDS_INPUT,
  selfTestFindings,
  summarizePythonFailure,
} from "../apps/web/src/preview.js";

// Pyodide's Node file-system setup reads the open() flag constants through process.binding,
// which the permission model disables entirely. Hand it the same constants from the public
// fs API, and nothing else.
process.binding = (name) => {
  if (name === "constants") return { fs: fsConstants };
  throw new Error(`process.binding("${name}") is not available in the sandbox`);
};

const here = dirname(fileURLToPath(import.meta.url));
const PYODIDE_DIR = join(here, "..", "apps", "web", "node_modules", "pyodide");

async function runPython({ code, input = [], selfTest = false }) {
  const { loadPyodide } = await import(pathToFileURL(join(PYODIDE_DIR, "pyodide.mjs")).href);
  const pyodide = await loadPyodide({ indexURL: PYODIDE_DIR + "/" });
  let stdout = "";
  let stderr = "";
  let readInput = false;
  const decoder = new TextDecoder();
  const errDecoder = new TextDecoder();
  pyodide.setStdout({ write: (bytes) => { stdout += decoder.decode(bytes, { stream: true }); return bytes.length; } });
  pyodide.setStderr({ write: (bytes) => { stderr += errDecoder.decode(bytes, { stream: true }); return bytes.length; } });
  const lines = [...input];
  pyodide.setStdin({ stdin: () => { if (!lines.length) return undefined; readInput = true; return lines.shift(); } });

  let failure = null;
  try {
    await pyodide.runPythonAsync(code);
  } catch (error) {
    failure = String((error && error.message) || error);
  } finally {
    try { pyodide.runPython("import sys\nsys.stdout.flush()\nsys.stderr.flush()"); } catch { /* best effort */ }
  }

  const printed = stdout.trim().length > 0;
  const result = { stdout, stderr, printed, readInput, failure: null, needsInput: false, errors: [], warnings: [] };
  if (failure) {
    const summary = summarizePythonFailure(failure);
    result.failure = summary;
    // Same rule as the Output panel: with no example input, stopping at input() isn't a bug.
    if (selfTest && input.length === 0 && /^EOFError/.test(summary)) {
      result.needsInput = true;
      result.warnings.push(NEEDS_INPUT);
    } else {
      result.errors.push(summary);
    }
  } else if (selfTest) {
    result.errors.push(...selfTestFindings(stdout, printed, readInput));
  }
  return result;
}

function extract({ text }) {
  const block = bestRunnable(text);
  return { lang: block ? block.lang : null, code: block ? block.code : null, example: exampleInput(text) };
}

function fix({ errors, attempt, max, code, lang }) {
  return { text: fixRequest(errors, attempt, max, code, lang) };
}

const request = JSON.parse(readFileSync(0, "utf8"));
const ops = { run: runPython, extract, fix };
if (!ops[request.op]) {
  process.stdout.write(JSON.stringify({ error: `unknown op ${request.op}` }));
  process.exit(2);
}
const response = await ops[request.op](request);
process.stdout.write(JSON.stringify(response));
