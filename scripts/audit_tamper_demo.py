"""Tamper with the audit log and watch the integrity check, on a throwaway database.

    python scripts/audit_tamper_demo.py

Uses the app's own /api/v1/security/status check (the "Audit chain" line on the Security
page). Everything lives in .demo-audit/, deleted at the start of each run; the real
database and .security/ key are never touched.

It shows what the chain catches and, just as plainly, what it doesn't:
  1. editing a row          -> caught
  2. deleting a middle row  -> caught
  3. deleting the newest rows -> NOT caught (nothing records how long the chain was)
  4. editing with the key   -> NOT caught (the key sits on the same disk)
"""

import os
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".demo-audit"
sys.path.insert(0, str(ROOT))

if WORK.exists():
    shutil.rmtree(WORK)
WORK.mkdir()
DB = WORK / "demo.db"
os.environ["ASSISTANT_DATABASE_URL"] = f"sqlite:///{DB.as_posix()}"
os.environ["ASSISTANT_AUTH_REQUIRED"] = "false"
os.environ["ASSISTANT_OPA_REQUIRED"] = "false"
os.environ["ASSISTANT_SECURITY_DIR"] = str(WORK / "security")
os.environ["ASSISTANT_SCHEDULER_ENABLED"] = "false"

from fastapi.testclient import TestClient

from backend.core.config import get_settings
from backend.main import app
from backend.security.audit import _digest, _timestamp

get_settings().workspace_dir = WORK / "workspace"


def sql(query: str, *args) -> list[tuple]:
    with sqlite3.connect(DB) as connection:
        rows = connection.execute(query, args).fetchall()
        connection.commit()
    return rows


def rows() -> list[tuple]:
    return sql("SELECT sequence, event_type, outcome, detail FROM secure_audit_records ORDER BY sequence")


def check(client: TestClient, label: str) -> None:
    valid = client.get("/api/v1/security/status").json()["audit_chain_valid"]
    print(f"   integrity check: {'PASS' if valid else 'FAIL (tampering detected)'}   <- {label}")


def backup() -> list[tuple]:
    return sql("SELECT * FROM secure_audit_records")


def restore(snapshot: list[tuple]) -> None:
    """Put the original rows back (through SQLite: the app holds the file open)."""
    sql("DELETE FROM secure_audit_records")
    marks = ", ".join("?" * len(snapshot[0]))
    with sqlite3.connect(DB) as connection:
        connection.executemany(f"INSERT INTO secure_audit_records VALUES ({marks})", snapshot)


with TestClient(app) as client:
    print("Writing 5 audit events (Do-it mode on/off: each change is a security event)...")
    for on in (True, False, True, False, True):
        client.put("/api/v1/settings/me", json={"autopilot": on}).raise_for_status()
    for row in rows():
        print("  ", row)
    check(client, "untouched log")
    clean = backup()

    print("\n1. Edit row 3's outcome from 'on' to 'off', directly in the database file:")
    sql("UPDATE secure_audit_records SET outcome = 'off' WHERE sequence = 3")
    print("  ", rows()[2])
    check(client, "edited row")
    restore(clean)
    check(client, "original rows put back")

    print("\n2. Delete row 3:")
    sql("DELETE FROM secure_audit_records WHERE sequence = 3")
    check(client, "middle row deleted")
    restore(clean)
    check(client, "original rows put back")

    print("\n3. Delete the two newest rows (4 and 5):")
    sql("DELETE FROM secure_audit_records WHERE sequence > 3")
    check(client, "newest rows deleted: a known limit")
    restore(clean)
    check(client, "original rows put back")

    print("\n4. Edit row 5 AND recompute its hash with the key from .security/audit.key:")
    record = sql(
        "SELECT sequence, event_type, actor_id, detail, previous_hash, created_at "
        "FROM secure_audit_records WHERE sequence = 5"
    )[0]
    from datetime import datetime

    created = datetime.fromisoformat(record[5])
    forged = _digest(record[0], record[1], "off", record[2], record[3], record[4], _timestamp(created))
    sql("UPDATE secure_audit_records SET outcome = 'off', entry_hash = ? WHERE sequence = 5", forged)
    print("  ", rows()[4])
    check(client, "forged with the key: a known limit")

shutil.rmtree(WORK, ignore_errors=True)
