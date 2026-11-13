# Security operations

Authentication is enabled by default. First launch presents a local
administrator bootstrap. Passwords use salted scrypt hashes. Sessions are
random, hashed in storage, bound to a trusted device token, expire after 12
hours by default, and use HttpOnly SameSite=Strict cookies. Cookie-authenticated
state changes require a separate CSRF token.

Use TLS and `ASSISTANT_SECURE_COOKIES=true` beyond localhost. A service API key
bypasses cookie/CSRF only for configured automation and is an administrator
credential.

## Incident response

Emergency stop cancels planned, running, and approval-waiting tasks/tool calls,
denies pending approvals, and invalidates unused grants. New operations are
denied until an administrator explicitly resumes. Both events enter the
tamper-evident audit chain.

If the audit chain reports `TAMPERED`, stop the service, preserve the database
and `.security/audit.key`, investigate offline, rotate credentials, and do not
resume autonomous actions until the cause is understood.

## Backup and recovery

Back up the database, `.security/master.key`, and `.security/audit.key`
together to encrypted storage. Without `master.key`, vault ciphertext is not
recoverable; without `audit.key`, historical records cannot be verified. Never
commit `.security`, `.env`, databases, or backups.

## Secret handling

Vault values use Fernet authenticated encryption. APIs return metadata only,
never plaintext or ciphertext. Security details are redacted before logging.
Secrets are not injected into model prompts. Prefer an externally provided
`ASSISTANT_MASTER_KEY` for production.

## Limitations

- Pattern-based injection detection is defense in depth, not proof that content
  is benign. Untrusted text is also isolated and cannot authorize tools.
- Native Windows OpenShell MXC is not treated as production-qualified. No
  arbitrary command tool exists and sandbox-required execution fails closed.
- OPA is optional in native development, but Docker requires it. Enable
  `ASSISTANT_OPA_REQUIRED=true` wherever OPA is an authorization dependency.
- A local administrator can access database/key files; OS and disk security are
  still required.
