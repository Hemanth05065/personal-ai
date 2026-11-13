# Architecture

The application is a modular monolith with explicit trust boundaries.

```text
React PWA
   |
FastAPI routes -- optional API key
   |
policy -> task/tool execution -> receipts + audit log
   |                 |                    |
Ollama          restricted files     SQLite/PostgreSQL
   |
local model

research route -> Wikipedia excerpts -> local Ollama synthesis
automation loop -> due task -> read execution or write approval
```

The API owns authorization, risk classification, approval state, persistence,
and model access. The browser never calls Ollama directly. Client-provided risk
levels are advisory; the server raises them to the minimum for each tool.

## Trust boundaries

- User requests remain subject to configured safety policy.
- Model output is a proposal, never proof that an action occurred.
- Retrieved excerpts, files, and model output are untrusted input.
- Credentials must never enter model context or audit details.
- Side effects require an approval record.
- File paths stay inside one configured workspace.
- Recurring writes create a new approval request on every run.
- Purchases, transfers, destructive operations, credential changes, and
  physical-security actions are prohibited.

## Persistence and deployment

SQLite provides zero-configuration local development. SQLAlchemy also supports
PostgreSQL; Docker includes PostgreSQL 16 with pgvector and Redis 7. Redis is
provisioned for future distributed coordination, while the local scheduler uses
the primary database.

The Windows launcher binds development services to `127.0.0.1`. The PWA can be
installed on desktop or mobile browsers. Docker provides a production web
server and PostgreSQL API. Enable API-key protection before extending access
beyond localhost.
