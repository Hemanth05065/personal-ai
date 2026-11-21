import threading
from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, SessionTransaction, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine_options: dict = {"connect_args": connect_args}
if settings.database_url == "sqlite:///:memory:":
    engine_options["poolclass"] = StaticPool
elif settings.database_url.startswith("sqlite"):
    # FastAPI runs sync endpoints on up to 40 worker threads; the default pool
    # (5 + 10 overflow) made busy moments queue for connections.
    engine_options.update(pool_size=20, max_overflow=20)
engine = create_engine(settings.database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Write serialization
#
# SQLite allows one writer at a time, and the audit chain computes "last
# sequence + 1" inside the writer's transaction. Two transactions could read the
# same last record and collide on the unique sequence. A single process-wide
# lock, taken before a session's first write and released when its transaction
# ends, makes every write transaction see the previous one's committed result.
# Request transactions here are short (chat commits before calling Ollama), so
# waiting is brief. The timeout turns an unexpected stall into an error instead
# of a hang.
# ---------------------------------------------------------------------------
WRITE_LOCK_TIMEOUT_SECONDS = 15
_write_lock = threading.Lock()
_LOCK_KEY = "holds_write_lock"


class DatabaseBusy(RuntimeError):
    pass


def hold_write_lock(session: Session) -> None:
    """Take the write lock for this session's current transaction (idempotent)."""
    if session.info.get(_LOCK_KEY):
        return
    if not _write_lock.acquire(timeout=WRITE_LOCK_TIMEOUT_SECONDS):
        raise DatabaseBusy("The local database is busy. Try again in a moment.")
    session.info[_LOCK_KEY] = True


@event.listens_for(Session, "before_flush")
def _lock_before_write(session: Session, _context, _instances) -> None:
    hold_write_lock(session)


@event.listens_for(Session, "after_transaction_end")
def _unlock_after_transaction(session: Session, transaction: SessionTransaction) -> None:
    if transaction.parent is None and session.info.pop(_LOCK_KEY, False):
        _write_lock.release()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Schema upgrades
#
# create_all() creates missing tables but never changes existing ones, so new
# nullable columns are added here. Additive only: nothing is dropped or rewritten.
# ---------------------------------------------------------------------------
ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "automations": {"owner_id": "VARCHAR(36)", "owner_role": "VARCHAR(30)"},
    "memories": {"created_by": "VARCHAR(64)"},
    "user_settings": {"web_search": "BOOLEAN"},
}


def add_missing_columns(target: Engine) -> None:
    inspector = inspect(target)
    tables = set(inspector.get_table_names())
    with target.begin() as connection:
        for table, columns in ADDED_COLUMNS.items():
            if table not in tables:
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def init_db() -> None:
    from backend.models import entities  # noqa: F401

    Base.metadata.create_all(bind=engine)
    add_missing_columns(engine)
