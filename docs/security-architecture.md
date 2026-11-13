# Security architecture

## Trust boundaries

```text
Browser/device
  | HttpOnly session + device cookie + CSRF
  v
FastAPI authentication middleware
  | principal: viewer / operator / admin
  v
Emergency stop -> OPA decision (or deterministic development policy)
  | deny / allow / approval required
  v
Untrusted-content scanner and context isolation
  v
Action-bound approval -> immediate fingerprint revalidation
  v
Typed workspace tool OR OpenShell-required sandbox (fail closed)
  v
Receipt + conventional audit + HMAC hash-chain security audit
```

Ollama and `qwen3.5:4b` generate text but do not make authorization decisions.
The model cannot issue a session, lower risk, approve a task, alter an action
fingerprint, or execute a tool directly.

## Permission levels

| Level | Meaning | Minimum role | Enforcement |
|---|---|---|---|
| 0 | Information only | viewer | Allowed unless emergency stopped |
| 1 | Authorized read | viewer | Workspace and size boundaries |
| 2 | Limited side effect | operator | Exact, expiring, single-use approval |
| 3 | Sensitive action | admin | Approval plus dedicated integration |
| 4 | Prohibited | none | Always denied |

Purchases, money transfers, important-file deletion, credential changes, and
physical-security control are prohibited. Unsupported integrations are never
reported as completed.

## Policy engines

`backend/core/policy.py` is the deterministic base policy. When OPA responds,
its decision is authoritative and combined with the stricter local approval
requirement. If OPA is required and unavailable or returns no decision, access
is denied. The Rego package and tests live in `security/opa`.

## Content and model boundary

Every retrieved research excerpt is scanned before model use. High-risk text is
quarantined; allowed text is wrapped with source and SHA-256 identity in an
explicit untrusted-data envelope. The model receives no vault contents or
authorization tokens. Model output remains a proposal until deterministic
backend policy permits an action.

## Sandboxing

The app exposes no arbitrary shell or code-execution endpoint. The OpenShell
adapter only reports capability and refuses sandbox-required execution unless
both configured and detected. The included policy uses Landlock
`hard_requirement`, explicit filesystem lists, and no network rules. This
prevents silent fallback to unrestricted host execution.

## Audit integrity

Security events contain sequence, type, outcome, actor, redacted detail,
previous hash, timestamp, and HMAC-SHA256 entry hash. Verification recomputes
the entire chain. Database edits, deletions, reorderings, and insertions break
validation. The HMAC key is stored separately from the database.
