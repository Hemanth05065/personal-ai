# AI Personal Assistant: Complete Project Handoff

Last updated: 7 November 2026 (Asia/Calcutta)

This document records what was built, what was verified, what is deliberately
limited, and what still needs to be completed. It is the reference point for
resuming the project later.

## 1. Honest current status

The project is a working local-first personal-assistant foundation with a
FastAPI backend, React PWA, SQLite persistence, Ollama integration, typed local
tools, approvals, automations, authentication, and a substantial deterministic
security pipeline.

The configured local model is now genuinely installed and working:

- Ollama model: `qwen3.5:4b`
- Installed size reported by Ollama: approximately 3.3 GB
- Ollama health check: available
- Direct generation test: returned `LOCAL_MODEL_OK`
- Backend health response reported `qwen3.5:4b`

The earlier statement that everything was complete before the model was set up
was incorrect. That claim was challenged and corrected. The project is now
reported using verified results only.

No paid AI API, subscription, or paid service was used. If a future step asks
for payment, stop and wait for the owner's manual instruction.

## 2. Work completed before the security phase

### Backend

A modular FastAPI backend was created with:

- health and Ollama availability checks;
- local chat using Ollama;
- conversation creation, history, reopening, and deletion;
- inspectable long-term memory;
- Wikipedia research with local-model synthesis and source links;
- task planning and typed tool calls;
- execution receipts;
- a restricted UTF-8 file workspace;
- path-traversal and file-size protection;
- approval-gated writes;
- recurring automations;
- conventional application audit records;
- SQLite development persistence through SQLAlchemy;
- PostgreSQL compatibility and a Docker stack with pgvector and Redis.

### Local tools and safety levels

The backend currently exposes only typed tools, not a general host shell:

- `information`: risk level 0;
- `list_files`: risk level 1;
- `read_file`: risk level 1;
- `write_file`: risk level 2 and approval required.

The server owns the minimum risk level. A client cannot label a write as risk
zero to bypass approval.

The following are explicitly prohibited by policy:

- purchases;
- money transfers;
- deletion of important files;
- credential changes;
- physical-security actions;
- unrestricted computer control.

### Web application

A React/Vite Progressive Web App was created with:

- local chat UI;
- conversation history;
- memory management;
- research reports and source links;
- workspace file listing and preview;
- task creation;
- approval inbox;
- task and receipt history;
- recurring automation management;
- browser voice dictation and speech playback where supported;
- PWA manifest and service worker;
- responsive desktop/mobile layout.

### Setup and deployment

The repository includes:

- Windows setup and start scripts;
- backend and frontend Dockerfiles;
- Docker Compose services for PostgreSQL/pgvector, Redis, OPA, API, and web;
- local `.env` and documented `.env.example` settings;
- a portable verified Node.js runtime under ignored `tools/` because the
  registered Windows Node installation was not accessible in this session.

## 3. Model setup and migration

The original project configuration used `qwen2.5:3b`. It was migrated to
`qwen3.5:4b` in:

- backend default settings;
- `.env`;
- `.env.example`;
- Windows setup script;
- Docker Compose;
- README documentation;
- Promptfoo local red-team provider.

The official Ollama model was pulled. Ollama verified the SHA-256 digest and
wrote the manifest. Both models may still exist locally, but the application
now selects `qwen3.5:4b`.

## 4. Security pipeline implemented

The security system is independent of model behavior. Ollama generates text;
it does not decide permissions, approve tools, or claim that a side effect
occurred.

The enforced flow is:

```text
device session + CSRF or service API key
  -> user role
  -> emergency-stop state
  -> OPA and deterministic local policy
  -> prompt-injection boundary for external content
  -> exact-action approval when required
  -> immediate approval revalidation
  -> restricted typed tool or fail-closed sandbox requirement
  -> receipt and tamper-evident security audit
```

### Authentication and session security

Implemented controls include:

- first-run local administrator bootstrap;
- salted scrypt password hashing;
- minimum password length and character-category checks;
- random session and device tokens;
- only token hashes stored in the database;
- device-bound sessions;
- configurable session expiry, defaulting to 12 hours;
- HttpOnly, SameSite=Strict cookies;
- optional Secure cookies for HTTPS deployments;
- CSRF token validation on cookie-authenticated mutations;
- explicit logout/session revocation;
- optional service API key for automated clients.

### Role-based access control

The policy defines:

| Role | Maximum permitted risk |
|---|---:|
| viewer | 1, read-only |
| operator | 2, limited side effects with approval |
| admin | 3, sensitive actions with approval/integration |

Unknown roles default to risk level 0. Risk level 4 and prohibited actions are
always denied.

Important limitation: policy-level RBAC exists, but an administrator UI/API for
creating additional viewer/operator users and changing roles has not yet been
built. First-run bootstrap currently creates the administrator account.

### OPA centralized authorization

Implemented:

- official OPA 1.11.0 Windows binary downloaded;
- binary SHA-256 checksum verified;
- Rego policy in `security/opa/assistant.rego`;
- Rego tests for viewer read, operator write approval, emergency denial, and
  prohibited-action denial;
- FastAPI OPA REST client;
- fail-closed behavior when OPA is marked required and is unavailable;
- Docker Compose OPA service;
- Windows start script launches local OPA;
- local `.env` currently has `ASSISTANT_OPA_REQUIRED=true`.

During testing, the first Rego version returned undefined decisions for denial
paths. This was caught by the OPA test suite and fixed with explicit default
deny values.

Verified results:

- OPA policy tests: 4/4 passed;
- live OPA write-file/operator query: allowed with approval required;
- live reason: centralized OPA policy requires explicit approval.

### Action-specific approvals

Approval behavior was strengthened to include:

- human-readable description;
- justification;
- target list;
- possible consequences;
- approving actor;
- ten-minute expiry;
- single use;
- SHA-256 fingerprint of task ID, tool name, and exact arguments;
- revalidation immediately before tool execution;
- rejection if arguments change after approval;
- invalidation by emergency stop;
- audit events for grant, decision, consumption, expiry/mismatch, and tampering.

### Emergency stop

The security dashboard provides an administrator emergency stop. Activation:

- marks planned, running, and approval-waiting tasks as cancelled;
- cancels pending/running tool calls;
- denies pending approvals;
- consumes/invalidates unused approval grants;
- blocks new task authorization;
- creates a tamper-evident security event.

Resuming requires an explicit administrator request and is also audited.

### Prompt-injection protection

External research content now passes through a deterministic scanner. It looks
for instruction overrides, secret exfiltration, role overrides, security-policy
bypass requests, command induction, and role markup.

Unsafe excerpts are quarantined. Accepted excerpts are wrapped in an explicit
untrusted-data envelope containing source identity and a SHA-256 digest. The
envelope tells the local model that the enclosed content is data, not an
instruction. Findings are recorded in the security database and audit chain.

This scanner is defense in depth, not proof that content is safe. The stronger
control is that retrieved text and model output cannot directly authorize or
execute tools.

### Encrypted secret vault

Implemented:

- Fernet authenticated encryption through `cryptography`;
- configurable external master key;
- protected local master-key file fallback in `.security/master.key`;
- API to save, list metadata, and delete secrets;
- API responses never return plaintext or ciphertext;
- security logs redact token/password/secret-like data;
- secrets are not passed into model prompts.

The vault is not yet connected to email/calendar/cloud adapters because those
adapters have not been implemented.

### Tamper-evident audit

Security events are stored with:

- monotonically increasing sequence number;
- event type and outcome;
- actor ID;
- redacted details;
- previous-entry hash;
- timestamp;
- HMAC-SHA256 entry hash.

The dashboard verifies the complete chain. Editing, deleting, reordering, or
inserting records breaks verification. The audit HMAC key is stored separately
in `.security/audit.key`.

For high-concurrency PostgreSQL deployment, sequence allocation should later be
hardened with database locking or a database sequence. The current mechanism is
appropriate for the single-process local SQLite deployment.

### OpenShell sandbox stance

NVIDIA OpenShell was researched and a restrictive policy was added under
`security/openshell/policy.yaml`:

- schema version 1;
- explicit read-only and read-write filesystem paths;
- Landlock `hard_requirement`;
- no network rules, so outbound network is denied by default.

OpenShell was deliberately not claimed as active on this native Windows host.
NVIDIA describes the native Windows MXC path as development-stage and not
production-qualified. The application exposes no arbitrary shell/code tool.
If a future operation requires a sandbox and OpenShell is configured but not
available, it fails closed and never falls back to the Windows host shell.

### Security dashboard

The React application now includes:

- first-run administrator and login screens;
- credentialed requests and CSRF handling;
- emergency stop/resume controls;
- OPA state;
- OpenShell/sandbox state;
- audit-chain integrity;
- active-session count;
- pending-approval count;
- prompt-injection findings;
- encrypted secret metadata and save form;
- tamper-evident security event list;
- richer approval descriptions, targets, and consequences.

## 5. Promptfoo status

Promptfoo 0.125.1 is installed under `security/promptfoo` and configured for:

- local target testing through the assistant API;
- local adversarial generation with `ollama:chat:qwen3.5:4b`;
- prompt injection;
- excessive agency;
- broken function-level authorization;
- session PII exposure;
- OWASP LLM and agentic frameworks.

Remote generation must be disabled with:

```powershell
$env:PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION = "true"
```

The initial Promptfoo dependency installation reported 5 high and 3 moderate
transitive vulnerabilities. Patched versions of `basic-ftp`, `glob`, and
`minimatch` were pinned through npm overrides. The final Promptfoo dependency
audit reports 0 vulnerabilities.

Important: Promptfoo is installed and configured, but a complete live red-team
generation/evaluation run has not yet been executed. This is still required.
The run can be slow because generation and grading use the local 4B model.

## 6. Tests and verification completed

Latest verified results on 7 November 2026:

| Check | Result |
|---|---|
| Python/API/security pytest suite | 21 passed |
| Python Ruff lint | Passed |
| OPA Rego policy tests | 4 passed |
| React production build | Passed |
| Web npm audit | 0 vulnerabilities |
| Promptfoo npm audit after overrides | 0 vulnerabilities |
| Ollama model installed | `qwen3.5:4b`, about 3.3 GB |
| Direct model generation | Passed, returned `LOCAL_MODEL_OK` |
| Backend health/model check | Available, `qwen3.5:4b` |
| Live OPA REST decision | Passed |

The only pytest warning is a Starlette notice that its current `TestClient`
path uses an httpx integration that will move to `httpx2`. It does not fail the
tests, but dependencies/tests should be updated later.

Security tests cover:

- all four allowed risk levels and prohibited risk level 4;
- viewer/operator/admin boundaries;
- risk spoofing by clients;
- administrator bootstrap and device sessions;
- CSRF rejection;
- prompt-injection detection;
- exact-action approval tampering;
- emergency stop and explicit resume;
- encrypted vault behavior and absence of plaintext API output;
- audit-chain tamper detection;
- path traversal;
- fail-closed sandbox behavior;
- approval and automation workflows.

## 7. Important files

```text
backend/main.py                     authentication/CSRF middleware and routers
backend/core/policy.py              deterministic risk and role policy
backend/security/auth.py            passwords, devices, and sessions
backend/security/approval.py        exact-action approval grants
backend/security/audit.py           redaction and HMAC audit chain
backend/security/content.py         prompt-injection scanning/isolation
backend/security/emergency.py       stop and resume behavior
backend/security/opa.py             OPA REST integration
backend/security/sandbox.py         OpenShell capability/fail-closed adapter
backend/security/vault.py           secret encryption
backend/api/auth.py                 bootstrap/login/logout/me endpoints
backend/api/security.py             dashboard, vault, scan, stop, and audit APIs
apps/web/src/main.jsx               PWA, authentication, and security dashboard
security/opa/                       Rego policy and tests
security/openshell/                 restrictive policy and Windows limitation
security/promptfoo/                 local red-team configuration
scripts/setup-security.ps1          OPA checksum/test and Promptfoo audit setup
scripts/start.ps1                   launches OPA, backend, and frontend
docs/security-architecture.md       trust boundaries and enforcement design
docs/security-testing-report.md     security test inventory
docs/security.md                    operations, backup, and incident guidance
```

## 8. What still needs to be done

### Priority 1: manual first-run account setup

The owner must choose the administrator username and password. This must not be
invented or stored by an automated assistant.

1. Start the project.
2. Open `http://localhost:5173`.
3. Create the first administrator account.
4. Store the password in the owner's password manager.
5. Confirm login, logout, and login again.

### Priority 2: run the live Promptfoo red team

The Promptfoo suite still needs a complete live run. Use a temporary local
service API key, never a real secret:

1. Configure a temporary `ASSISTANT_API_KEY` for a dedicated test server.
2. Start the test server against a disposable test database.
3. Set the same value in `ASSISTANT_SECURITY_TEST_KEY`.
4. Set `PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION=true`.
5. Run Promptfoo from `security/promptfoo`.
6. Review every failure; do not automatically accept model-graded results.
7. Save a redacted report in `docs/`.
8. remove the temporary key and test database.

Suggested command after the test server is ready:

```powershell
$env:PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION = "true"
$env:ASSISTANT_SECURITY_TEST_KEY = "temporary-local-test-key"
Set-Location security/promptfoo
npm run redteam
```

Do not run without the remote-generation disable variable.

### Priority 3: cold-start acceptance test

The updated pieces were tested individually, but a full reboot/cold-start user
acceptance pass should be performed:

- run `scripts/start.ps1` from a clean terminal;
- confirm OPA starts before the API;
- confirm the API fails closed if OPA is stopped;
- confirm the web app loads;
- bootstrap/login manually;
- chat with `qwen3.5:4b`;
- create a read task;
- create, inspect, approve, and execute a write task;
- verify the receipt and security audit;
- test emergency stop and explicit resume;
- restart and confirm sessions/data persist correctly.

### Priority 4: production hardening

Before exposing the application beyond localhost:

- put it behind TLS;
- set `ASSISTANT_SECURE_COOKIES=true`;
- provide a strong external `ASSISTANT_MASTER_KEY`;
- replace all default database passwords;
- restrict database, `.env`, workspace, and `.security` filesystem access;
- use PostgreSQL and formal migrations;
- add rate limiting and login-attempt throttling;
- add session/device revocation UI;
- add administrator user and role management;
- add audit retention/export and finding-resolution workflows;
- automate encrypted backups and perform a recovery drill;
- add CI for pytest, Ruff, OPA tests, frontend build, and npm audits;
- configure monitoring without logging prompts or secrets.

### Priority 5: database migrations

The project currently uses SQLAlchemy `create_all`. It creates missing tables
but is not a full schema-migration system. Add Alembic before long-term or
multi-user deployment, generate a baseline migration, and test upgrades from a
copy of the existing database.

### Priority 6: supported OpenShell deployment, only if code execution is added

There is no need to activate OpenShell merely for the current typed file tools.
If arbitrary code execution becomes a real requirement:

- deploy on a production-supported Linux/container host;
- install OpenShell only from NVIDIA's official release;
- verify checksums/signatures;
- validate the included policy against that OpenShell version;
- keep Landlock as a hard requirement;
- use CPU, memory, process, time, filesystem, environment, and network limits;
- add kill/timeout controls and audit every sandbox lifecycle event;
- never fall back to host execution;
- add escape, network-egress, resource-exhaustion, and process-isolation tests.

### Priority 7: optional external integrations

Email, calendars, cloud storage, smart-home control, mobile app-store
publishing, and similar integrations are not implemented. Each requires an
owner-selected provider, account authorization, scoped credentials, a typed
adapter, permission policy, approval workflow, audit events, and tests.

Do not silently enable or claim these integrations. If a provider requests
payment, stop and wait for the owner's decision.

### Priority 8: source-control baseline

The repository currently shows the project files as untracked. No clean
baseline commit has been made. Before further work:

1. Review `.gitignore` carefully.
2. Ensure `.env`, `.security`, databases, workspaces, model files, portable
   tools, npm caches, and generated builds are not staged.
3. Review all source files.
4. Make an initial commit only after the owner approves the contents.

The `.vscode/` folder is user-owned and was intentionally not modified.

## 9. How to start later

From PowerShell in `D:\works`:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\start.ps1
```

Expected local endpoints:

- web application: `http://localhost:5173`;
- API documentation: `http://localhost:8000/docs`;
- API health: `http://localhost:8000/api/v1/health`;
- OPA: `http://127.0.0.1:8181`;
- Ollama: `http://127.0.0.1:11434`.

If setup must be repeated:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
```

All configured setup components are free/open source. Stop if any new step
requests payment.

## 10. Verification commands for future work

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check --no-cache backend tests
.\tools\opa\opa.exe test security/opa -v
.\tools\node\node-v24.20.0-win-x64\npm.cmd --prefix apps/web run build
.\tools\node\node-v24.20.0-win-x64\npm.cmd --prefix apps/web audit --audit-level=high
.\tools\node\node-v24.20.0-win-x64\npm.cmd --prefix security/promptfoo audit --audit-level=high
```

## 11. Definition of genuinely complete

Do not call the whole assistant complete until all of the following are true:

- the owner account has been created and login tested;
- a cold-start acceptance test passes;
- the full Promptfoo local red-team run has been reviewed and remediated;
- backup and restore have been tested;
- production deployment settings are applied for the intended network scope;
- required external integrations, if any, are explicitly selected and tested;
- unsupported features are documented rather than implied;
- the repository has an owner-reviewed baseline commit;
- no paid step has been taken without manual owner approval.

At present, the local model, core application, deterministic security controls,
OPA policy, automated tests, dashboard build, and dependency audits are
verified. The manual acceptance, full Promptfoo run, production hardening, and
optional integrations remain future work.
