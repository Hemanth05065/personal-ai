import asyncio
import hmac
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api import (
    audit,
    auth,
    automations,
    chat,
    files,
    health,
    memory,
    reminders,
    research,
    search,
    security,
    tasks,
)
from backend.api import (
    settings as settings_api,
)
from backend.core.config import get_settings
from backend.database import DatabaseBusy, SessionLocal, init_db
from backend.security.auth import DEVICE_COOKIE, SESSION_COOKIE, Principal, authenticate_session
from backend.services.automation import automation_loop


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    scheduler = asyncio.create_task(automation_loop()) if get_settings().scheduler_enabled else None
    try:
        yield
    finally:
        if scheduler:
            scheduler.cancel()


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def authenticate_request(request: Request, call_next):
    path = request.url.path
    protected = path.startswith("/api/v1")
    public = path in {
        "/api/v1/health",
        "/api/v1/auth/status",
        "/api/v1/auth/bootstrap",
        "/api/v1/auth/login",
    }
    # CORS preflight requests never carry credentials; let CORSMiddleware answer them.
    if request.method == "OPTIONS" or not protected or public:
        return await call_next(request)

    supplied_key = request.headers.get("X-Assistant-Key")
    # compare_digest takes the same time wherever the strings differ, so response
    # timing can't be used to guess the key one character at a time.
    if (
        settings.api_key
        and supplied_key
        and hmac.compare_digest(supplied_key.encode(), settings.api_key.encode())
    ):
        request.state.principal = Principal("service", "api-key", "admin", service=True)
        return await call_next(request)

    if settings.api_key and not settings.auth_required:
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})

    if not settings.auth_required:
        request.state.principal = Principal("local-development", "local", "admin", service=True)
        return await call_next(request)

    # Database work runs in a worker thread, never on the event loop: a blocked
    # loop can't return finished requests' connections, which deadlocked the
    # server under ~20 concurrent requests (found by load testing).
    authenticated = await run_in_threadpool(
        _check_session, request.cookies.get(SESSION_COOKIE), request.cookies.get(DEVICE_COOKIE)
    )
    if authenticated is None:
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})
    principal, csrf_hash = authenticated
    request.state.principal = principal
    if request.method in WRITE_METHODS:
        from backend.api.auth import valid_csrf

        if not valid_csrf(request.headers.get("X-CSRF-Token"), csrf_hash):
            return JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})
        # Viewers are read-only everywhere: one rule here instead of a role check on each
        # endpoint, so a new endpoint can't forget it. Signing out is the only write allowed.
        if principal.role == "viewer" and path not in VIEWER_WRITES:
            return JSONResponse(
                status_code=403,
                content={"detail": "Viewers have read-only access. Ask an admin for the operator role."},
            )
    return await call_next(request)


WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
VIEWER_WRITES = {"/api/v1/auth/logout"}


def _check_session(session_token: str | None, device_token: str | None) -> tuple[Principal, str] | None:
    """Validate the session and release the connection before the request runs,
    so one request never holds two pooled connections at once."""
    with SessionLocal() as db:
        authenticated = authenticate_session(db, session_token, device_token)
        if authenticated is None:
            return None
        principal, session = authenticated
        return principal, session.csrf_hash


@app.exception_handler(DatabaseBusy)
async def database_busy(_: Request, exc: DatabaseBusy) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(security.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(memory.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(files.router, prefix="/api/v1")
app.include_router(research.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(reminders.router, prefix="/api/v1")
app.include_router(settings_api.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(automations.router, prefix="/api/v1")


@app.get("/")
def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs"}
