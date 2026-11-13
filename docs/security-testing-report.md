# Security testing report

Automated pytest coverage includes:

- all permission levels and viewer/operator/admin boundaries;
- prohibited actions and client risk-level spoofing;
- device-bound login, administrator bootstrap, and CSRF rejection;
- prompt-injection and secret-exfiltration detection;
- exact-action approval fingerprint tamper rejection;
- emergency cancellation, new-action blocking, and explicit resume;
- encrypted vault round trip without plaintext API/storage exposure;
- HMAC audit verification and database-tamper detection;
- workspace path traversal rejection;
- sandbox fail-closed behavior without host fallback;
- recurring automation and approval workflows.

Promptfoo configuration adds local adversarial generation using
`ollama:chat:qwen3.5:4b` for prompt injection, excessive agency, broken
function-level authorization, and session PII. Remote red-team generation must
be explicitly disabled with `PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION=true`.

## Verification commands

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check --no-cache backend tests
npm --prefix apps/web run build
npm --prefix apps/web audit --audit-level=high
```

OPA policy tests can be run with an official OPA binary:

```powershell
opa test security/opa -v
```

OpenShell runtime validation is environment-specific and is not claimed on the
native Windows development host. See `security/openshell/README.md`.
