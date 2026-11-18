"""Coding evaluation harness: measures the app's coding pipeline with hidden checks.

    python eval/run_eval.py                         # the app's own routing, 3 runs per task
    python eval/run_eval.py --models qwen2.5-coder:7b --runs 5 --tasks roman,spiral
    python eval/run_eval.py --summarize eval/results/<file>.json

Each run mirrors what happens in the chat, using the app's own code:
  1. The request goes to the model the app would pick (backend/services/routing.py), with
     the same system prompt, tools and coding checklist.
  2. The reply's code runs in the Output panel's runtime (Pyodide, via eval/runner.mjs),
     judged by the same self-test rules (apps/web/src/preview.js). A sample input is written
     the same way when the reply has none.
  3. Errors go back as the app's own auto-fix message, up to --max-fixes times.
Then hidden checks (eval/tasks.py), which the model never sees, run the first and the final
program. "First try" = the first reply passes every check; "final" = after the fix loop.

Needs Ollama running with the models pulled, and `npm ci` in apps/web (for Pyodide).
Model-written code runs under Node's permission model: see eval/runner.mjs.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings
from backend.services.agent import AGENT_GUIDANCE, OLLAMA_TOOLS
from backend.services.ollama import OllamaClient
from backend.services.routing import (
    CODER_GUIDANCE,
    EXAMPLE_INPUT_PROMPT,
    choose_model,
    extract_example_input,
    with_reminder,
)
from eval.checks import judge
from eval.tasks import TASKS

RUNNER = ROOT / "eval" / "runner.mjs"
INPUT_CALL = re.compile(r"\binput\s*\(")  # same test as the chat (ChatView.jsx)
TEST_LIMIT_S = 20  # the Output panel's self-test limit
TIME_LIMIT_MESSAGE = (
    "Stopped: the program was still running after 20 seconds. It may have an endless loop "
    "or be waiting for more input."
)


# ---------- the "browser half" (eval/runner.mjs) ----------


def runner(request: dict, timeout: float) -> dict:
    """Run one runner op in a fresh, permission-restricted Node process."""
    command = ["node", "--permission", f"--allow-fs-read={ROOT}", str(RUNNER)]
    try:
        done = subprocess.run(
            command,
            input=json.dumps(request),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"timed_out": True}
    if done.returncode != 0 or not done.stdout.strip():
        return {"crashed": (done.stderr or done.stdout)[-600:]}
    return json.loads(done.stdout)


def run_python(code: str, input_text: str, self_test: bool) -> dict:
    lines = input_text.replace("\r\n", "\n").split("\n") if input_text else []
    if lines and lines[-1] == "":
        lines.pop()
    # A few seconds on top of the program's limit for starting Node and Pyodide.
    result = runner(
        {"op": "run", "code": code, "input": lines, "selfTest": self_test}, TEST_LIMIT_S + 10
    )
    if result.get("timed_out"):
        return {"stdout": "", "errors": [TIME_LIMIT_MESSAGE], "needsInput": False}
    if result.get("crashed"):
        return {
            "stdout": "",
            "errors": [f"Python could not start: {result['crashed']}"],
            "needsInput": False,
        }
    return result


# ---------- the model side (the app's own prompts and routing) ----------


def call_model(
    model: str, context_tokens: int, messages: list[dict], guidance: str, tools: bool
) -> dict:
    """One non-streamed chat call with exactly the app's payload. Retries a failed model load."""
    settings = get_settings()
    client = OllamaClient(settings, model=model, context_tokens=context_tokens)
    payload = client._payload(
        messages, [], stream=False, tools=OLLAMA_TOOLS if tools else None, system_extra=guidance
    )
    last_error = ""
    for attempt in range(3):
        try:
            started = time.monotonic()
            response = httpx.post(f"{settings.ollama_url}/api/chat", json=payload, timeout=1800)
            data = response.json()
            if response.status_code == 200 and "message" in data:
                return {
                    "message": data["message"],
                    "secs": time.monotonic() - started,
                    "tokens": data.get("eval_count", 0),
                }
            last_error = str(data.get("error", response.text))[:300]
        except (httpx.HTTPError, ValueError) as exc:
            last_error = str(exc)[:300]
        time.sleep(10 * (attempt + 1))  # e.g. a model load that failed on a busy GPU
    raise RuntimeError(f"Ollama call failed for {model}: {last_error}")


def code_from_reply(message: dict) -> tuple[str | None, str, bool]:
    """(code, example input, came_from_a_tool_call), the way the Output panel finds it."""
    found = runner({"op": "extract", "text": message.get("content", "")}, 60)
    if found.get("code") and (found.get("lang") or "").lower() in {"python", "py", "python3"}:
        return found["code"], found.get("example", ""), False
    # The model may save the program with the write_file tool instead of replying with it.
    for call in message.get("tool_calls") or []:
        function = call.get("function", {})
        arguments = function.get("arguments") or {}
        if function.get("name") == "write_file" and str(arguments.get("path", "")).endswith(".py"):
            return str(arguments.get("content", "")), "", True
    return None, "", False


def sample_input(code: str, model: str, context_tokens: int) -> str:
    """What POST /chat/example-input does: the writing model drafts an input."""
    client = OllamaClient(get_settings(), model=model, context_tokens=context_tokens)
    payload = client._payload(
        [{"role": "user", "content": EXAMPLE_INPUT_PROMPT.replace("{code}", code)}],
        [],
        stream=False,
    )
    response = httpx.post(f"{get_settings().ollama_url}/api/chat", json=payload, timeout=1800)
    return extract_example_input(response.json()["message"]["content"])


def pick(mode: str, text: str) -> tuple[str, int, str, bool]:
    """(model, context window, guidance, big) for this message under --models <mode>."""
    settings = get_settings()
    if mode == "app":
        choice = choose_model(settings, text)
        return choice.model, choice.context_tokens, choice.guidance, choice.big
    return mode, settings.coder_context_tokens, CODER_GUIDANCE, False


# ---------- one task, one run ----------


def hidden_checks(task: dict, code: str | None) -> list[dict]:
    results = []
    for check in task["checks"]:
        if code is None:
            results.append({"stdin": check["stdin"][:40], "passed": False, "why": "no code"})
            continue
        run = run_python(code, check["stdin"], self_test=False)
        if run.get("failure") or run.get("errors"):
            problem = run.get("failure") or run["errors"][0]
            results.append({"stdin": check["stdin"][:40], "passed": False, "why": problem[:200]})
            continue
        passed, why = judge(check, run.get("stdout", ""))
        results.append({"stdin": check["stdin"][:40], "passed": passed, "why": why})
    return results


def run_task(task: dict, mode: str, max_fixes: int, log) -> dict:
    history: list[dict] = [{"role": "user", "content": task["prompt"]}]
    rounds: list[dict] = []
    first_code = code = None
    for attempt in range(max_fixes + 1):
        model, context, guidance, big = pick(mode, history[-1]["content"])
        log(f"round {attempt}: {model} writing")
        reply = call_model(
            model, context, with_reminder(history), f"{AGENT_GUIDANCE}\n\n{guidance}", tools=True
        )
        code, example, via_tool = code_from_reply(reply["message"])
        if first_code is None:
            first_code = code
        record = {
            "attempt": attempt,
            "model": model,
            "secs": round(reply["secs"], 1),
            "tokens": reply["tokens"],
            "via_tool": via_tool,
            "example_written": False,
        }
        if code is None:
            record["errors"] = ["the reply had no Python code block"]
            rounds.append(record)
            break
        if not example and INPUT_CALL.search(code):
            # Same rule as the chat: a program that reads input is tested with a sample of it.
            writer = (
                model
                if mode != "app"
                else (get_settings().big_coder_model if big else get_settings().coder_model)
            )
            example = sample_input(code, writer, context)
            record["example_written"] = True
        log(f"round {attempt}: self-test")
        test = run_python(code, example, self_test=True)
        record["errors"] = test.get("errors", [])
        record["needs_input"] = test.get("needsInput", False)
        rounds.append(record)
        if not record["errors"] or attempt == max_fixes:
            break
        fix = runner(
            {
                "op": "fix",
                "errors": record["errors"],
                "attempt": attempt + 1,
                "max": max_fixes,
                "code": code,
                "lang": "python",
            },
            60,
        )["text"]
        history += [
            {"role": "assistant", "content": reply["message"].get("content", "")},
            {"role": "user", "content": fix},
        ]

    log("hidden checks")
    first = hidden_checks(task, first_code)
    final = first if code == first_code else hidden_checks(task, code)
    return {
        "task": task["id"],
        "mode": mode,
        "rounds": rounds,
        "first_try": all(item["passed"] for item in first),
        "final": all(item["passed"] for item in final),
        "first_checks": first,
        "final_checks": final,
        "self_test_passed": bool(rounds) and not rounds[-1].get("errors"),
        "secs": round(sum(item["secs"] for item in rounds), 1),
    }


# ---------- reporting ----------


def summarize(results: dict) -> str:
    rows = [
        "| Model | Task | First try | After fixes | Avg fix rounds | Avg minutes |",
        "|---|---|---|---|---|---|",
    ]
    totals: dict[str, list[dict]] = {}
    for run in results["runs"]:
        totals.setdefault(run["mode"], []).append(run)
    for mode, runs in totals.items():
        by_task: dict[str, list[dict]] = {}
        for run in runs:
            by_task.setdefault(run["task"], []).append(run)
        for task_id, task_runs in by_task.items():
            count = len(task_runs)
            rows.append(
                f"| {mode} | {task_id} | {sum(r['first_try'] for r in task_runs)}/{count} "
                f"| {sum(r['final'] for r in task_runs)}/{count} "
                f"| {statistics.mean(len(r['rounds']) - 1 for r in task_runs):.1f} "
                f"| {statistics.mean(r['secs'] for r in task_runs) / 60:.1f} |"
            )
        count = len(runs)
        first, final = sum(r["first_try"] for r in runs), sum(r["final"] for r in runs)
        errors = sum("error" in r for r in runs)
        if errors:
            rows.append(
                f"| {mode} | ({errors} runs failed to reach the model; counted as failures) | | | | |"
            )
        rows.append(
            f"| **{mode}** | **all {len(by_task)} tasks** | **{first}/{count} ({100 * first / count:.0f}%)** "
            f"| **{final}/{count} ({100 * final / count:.0f}%)** "
            f"| {statistics.mean(len(r['rounds']) - 1 for r in runs):.1f} "
            f"| {statistics.mean(r['secs'] for r in runs) / 60:.1f} |"
        )
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--models", default="app", help="comma list: 'app' (the app's routing) or model names"
    )
    parser.add_argument("--runs", type=int, default=3, help="runs per task and model")
    parser.add_argument("--tasks", default="", help="comma list of task ids (default: all)")
    parser.add_argument("--max-fixes", type=int, default=3, help="auto-fix rounds, as in the app")
    parser.add_argument(
        "--out", default="", help="results file (default: eval/results/<time>.json)"
    )
    parser.add_argument(
        "--summarize", default="", help="print the table for an existing results file"
    )
    args = parser.parse_args()

    if args.summarize:
        print(summarize(json.loads(Path(args.summarize).read_text(encoding="utf-8"))))
        return

    wanted = {item for item in args.tasks.split(",") if item}
    tasks = [task for task in TASKS if not wanted or task["id"] in wanted]
    modes = [item.strip() for item in args.models.split(",") if item.strip()]
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.out) if args.out else ROOT / "eval" / "results" / f"{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    results = {
        "started": stamp,
        "models": {
            "app_chat": settings.model,
            "app_coder": settings.coder_model,
            "app_big_coder": settings.big_coder_model,
            "modes": modes,
        },
        "runs_per_task": args.runs,
        "max_fixes": args.max_fixes,
        "machine": {"system": platform.system(), "processor": platform.processor()},
        "runs": [],
    }

    total = len(modes) * len(tasks) * args.runs
    done = 0
    for mode in modes:
        for task in tasks:
            for index in range(args.runs):
                done += 1
                prefix = f"[{done}/{total}] {mode} {task['id']} #{index + 1}"
                try:
                    record = run_task(
                        task,
                        mode,
                        args.max_fixes,
                        lambda text, p=prefix: print(f"{p}: {text}", flush=True),
                    )
                except RuntimeError as exc:
                    # Ollama failed even after retries: count it as a failed run and go on.
                    print(f"{prefix}: ERROR {exc}", flush=True)
                    record = {
                        "task": task["id"],
                        "mode": mode,
                        "rounds": [],
                        "first_try": False,
                        "final": False,
                        "secs": 0,
                        "error": str(exc),
                    }
                record["run"] = index + 1
                results["runs"].append(record)
                # Saved after every run, so a long evaluation can be stopped and still used.
                out.write_text(json.dumps(results, indent=1), encoding="utf-8")
                print(
                    f"{prefix}: first try {'PASS' if record['first_try'] else 'fail'}, "
                    f"final {'PASS' if record['final'] else 'fail'}",
                    flush=True,
                )

    print()
    print(summarize(results))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
