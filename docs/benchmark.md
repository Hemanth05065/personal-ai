# Coding benchmark (November 2026)

A first, small measurement of how well the local coding pipeline works: the models,
the Output-panel self-test, and the auto-fix loop. It is a **single run per cell**, so
read the numbers as a sanity check, not as statistics.

## Setup

- **Machine:** laptop with an RTX 4050 (6 GB), Ryzen 7 7435HS, 24 GB RAM.
- **Models:** `qwen2.5-coder:7b` (fits on the GPU) and `qwen2.5-coder:14b`. The 14B
  runs 67% on the CPU, at about **4.6 tokens/s** with a 13 s load.
- **Method:** each task was sent through the app's exact pipeline:
  1. the same system prompt and coding checklist;
  2. the same self-test in the sandboxed Output panel;
  3. up to 3 auto-fix rounds.

  **Hidden checks the model never saw** then judged the final code.
- **Tasks:**
  - **Expression evaluator** (Python, no `eval`): 6 checks, covering precedence,
    unary minus, division and invalid input.
  - **Sudoku solver** (Python): 2 checks, a real puzzle and an invalid one.
  - **Tetris** and **2048** (HTML): the self-test plus a hand play-test.

## Results

| Task | 7B, first pipeline | 7B, fixed pipeline | 14B, first pipeline | 14B, fixed pipeline |
|---|---|---|---|---|
| Expression evaluator | 1/6 | **6/6** | 1/6 | 6/6, then 0/6 on a rerun* |
| Sudoku solver | 0/2 | 1/2 | **2/2** | **2/2** |
| Tetris | broken after 4 fix rounds | — | loads, but plays wrong** | — |
| 2048 | loads after 1 fix | — | loads after 1 fix, but plays wrong** | — |

\* On the rerun, the code defined everything but never called it. Fix 4 below now
catches this.
\** The hand play-test found logic and layout bugs that no error is raised for:
- Tetris built a 10×10 board on a 10×20 canvas, so pieces landed halfway down.
- 2048 stacked its cells in one column.

**Time:** the 14B took 2–6 minutes per program, and up to 13 minutes with fix
rounds. The 7B took under a minute.

## What the benchmark exposed, and the fixes

The first pipeline passed broken code. Each problem below was found by the hidden
checks and fixed:

1. **Generic sample input broke correct programs.** Lines like "5" and "hello" were
   fed to a sudoku solver, and the auto-fix then "fixed" a bug that didn't exist. The
   self-test now uses the coder's own example input, or a sample written for that
   exact program.
2. **Swallowed errors passed.** A program that caught its crash and printed it
   (`module 'ast' has no attribute 'Num'`) counted as a success. Python's own error
   wording in the output is now treated as a failure.
3. **Outdated Python.** Both models used `ast.Num`, which Python 3.14 removed, and
   ignored the system prompt about it. A short checklist placed right after the
   request fixed this for the 14B (1/6 → 6/6). The 7B still ignores it, but fix 2
   catches the result.
4. **Code that never runs passed.** A run that prints nothing and reads nothing is now
   a failure.
5. **"Passed" meant "couldn't test".** When no input could be given, the status now
   says so.

## Limits and next steps

- **One run per cell.** Model output varies between runs: the same 14B task scored
  6/6, then 0/6. Real numbers need several runs per task and a pass rate.
- **The harness isn't in the repo yet.** The script was temporary. A committed,
  repeatable harness (`eval/`) with more tasks is the next step.
- **Error-based testing can't see logic bugs** (see the games above). A review pass
  against a feature checklist, or task-specific checks such as "the canvas is filled
  to the bottom", would be needed.
