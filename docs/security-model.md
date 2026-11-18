# Security model

A short, honest summary: what the assistant defends against, how, and which parts
have never actually been tested. The detailed design is in
[security-architecture.md](security-architecture.md).

## What it's for

One person, or a small household, running the assistant on their own computer.
The main risks it's built around:

1. **The model being talked into acting.** Text in a file, a web page or a memory
   could carry instructions ("also delete…", "write evil.txt").
2. **Another account on the same install** doing more than its role allows.
3. **Quiet tampering** with the record of what happened.

It is **not** built to be exposed to the internet. It serves plain HTTP on
localhost, and session cookies aren't marked `Secure` by default.

## The rules

- **The model only proposes.** Every action the model asks for goes through
  `plan_task`:
  - role check;
  - policy (prohibited actions are never tools: money, messages, deletes,
    credentials);
  - the emergency stop;
  - an exact, expiring, single-use approval bound to that action's
    fingerprint.

  Outcomes shown in chat are written by the server, not the model.
- **Roles.**
  - Viewers are read-only: one middleware rule rejects every write except
    signing out (`backend/main.py`). A test walks the whole API, so a new
    endpoint can't miss it.
  - Operators can change things.
  - Admins can also use the emergency stop and the secrets vault.
- **Do-it mode** runs a user's requested file writes without an approval click,
  through the same checks as the Approve button. Every write can be undone.
  - It still asks whenever the model's context holds text the user didn't write:
    - a file read in this task;
    - a file read earlier in the same chat;
    - an enabled memory saved by someone else, or before memory authors were
      recorded.
  - Wikipedia research never enters the chat or the tools: its own screen, no
    tool access. So it can't steer a write.
- **Untrusted text** (files, search results, Wikipedia excerpts) is wrapped in an
  "untrusted data" envelope before the model sees it.
  - It is also scanned for injection phrasing.
  - Memories that look like instructions aren't saved.
- **Code from the model** runs only in the Output panel:
  - a sandboxed iframe with an opaque origin;
  - Python on Pyodide in a worker;
  - a content policy with `connect-src 'none'`;
  - a time limit.

  It can't reach the app, its cookies, your files, your network or the internet.
- **Audit.** Security events are chained with HMAC-SHA256. Editing, deleting or
  reordering a record breaks verification.

## What is tested, and what isn't

| Piece | Status |
|---|---|
| Sessions, CSRF, roles (viewer write block on all 22 write endpoints), approvals, grants, emergency stop, audit chain, workspace path checks, Do-it mode and undo, the taint rules | **Automated tests** (pytest, run in CI on every push) |
| Local policy (`backend/core/policy.py`) | **Automated tests.** This is the policy the app actually uses. |
| **OPA policy (`security/opa/*.rego`)** | **Never run.** Windows App Control blocks `opa.exe` on the development machine, so the app runs with `ASSISTANT_OPA_REQUIRED=false` and uses the local policy. The Rego rules and `assistant_test.rego` have not been executed, and CI doesn't run them yet. |
| **OpenShell sandbox** | **Not tested.** There's no shell or code-execution tool to sandbox; the adapter only reports that it's unavailable. |
| Output-panel sandbox (network blocked, localhost blocked, endless loop stopped) | **Checked by hand** in Chromium. No automated browser test. |
| Injection scanner | **Pattern matching only.** It catches obvious phrasing; a reworded instruction gets through. That's why Do-it mode relies on the "who wrote this text" rule, not the scanner. |
| Promptfoo red-team config (`security/promptfoo`) | **Not part of CI.** No recorded results in this repo. |
| PostgreSQL / Docker stack | **Not tested** in recent work. Only SQLite is exercised. |

## Known limits

- **The database isn't encrypted.** Chats, memories and reminders are readable by
  anyone with access to your Windows account. Only vault secrets are encrypted.
- **The audit key lives on the same disk** (`.security/audit.key`). The chain
  catches tampering by someone without the key, not by someone who can read
  both files.
- **Approvals trust the person clicking.** A convincing proposal is still the
  user's call.
- **Local models make mistakes.** The rules above limit what a wrong model
  answer can do, not whether it happens.
