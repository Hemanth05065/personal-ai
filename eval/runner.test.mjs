// node --test eval/   (needs `npm ci` in apps/web for Pyodide)
// The harness runner: same results as the Output panel, and the sandbox holds.

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function call(request) {
  const done = spawnSync(
    process.execPath,
    ["--permission", `--allow-fs-read=${root}`, join(root, "eval", "runner.mjs")],
    { input: JSON.stringify(request), encoding: "utf8", timeout: 60000 },
  );
  assert.equal(done.status, 0, done.stderr);
  return JSON.parse(done.stdout);
}

const run = (code, input = [], selfTest = true) => call({ op: "run", code, input, selfTest });

test("runs Python with input", () => {
  const result = run("n = int(input())\nprint(n * 2)", ["21"]);
  assert.equal(result.stdout, "42\n");
  assert.deepEqual(result.errors, []);
});

test("Python 3.14 runtime, like the Output panel", () => {
  assert.match(run("import sys\nprint(sys.version)").stdout, /^3\.14\./);
  // ast.Num was removed in 3.14: the bug the benchmark caught must stay catchable.
  assert.match(run("import ast\nast.Num").errors[0], /has no attribute 'Num' \(line 2\)/);
});

test("self-test rules match the app", () => {
  assert.match(run("try:\n    [1][5]\nexcept Exception as e:\n    print(e)").errors[0], /caught a Python error/);
  assert.match(run("def main():\n    print(1)").errors[0], /without printing anything/);
  const waiting = run("x = input()");
  assert.equal(waiting.needsInput, true);
  assert.deepEqual(waiting.errors, []);
  assert.match(run("x = input()\ny = input()", ["only one"]).errors[0], /^EOFError/);
});

test("the sandbox blocks processes and reads outside the repository", () => {
  const spawn = run('import js\njs.process.getBuiltinModule("child_process").execSync("whoami")');
  assert.match(spawn.errors[0], /restricted/);
  const outside = join(root, "..", "outside-the-repo.txt");
  const read = run(`import js\njs.process.getBuiltinModule("fs").readFileSync(${JSON.stringify(outside)})`);
  assert.match(read.errors[0], /restricted/);
});

test("extract and fix use the app's own code", () => {
  const found = call({ op: "extract", text: "```python\nprint(input())\n```\n```text\n# Example input\n5\n```" });
  assert.deepEqual(found, { lang: "python", code: "print(input())\n", example: "5" });
  const { text } = call({ op: "fix", errors: ["NameError: name 'x' is not defined (line 1)"], attempt: 1, max: 3, code: "print(x)", lang: "python" });
  assert.match(text, /^Auto-fix \(attempt 1 of 3\)/);
  assert.match(text, /That line is: print\(x\)/);
});
