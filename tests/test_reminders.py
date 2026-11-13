from datetime import UTC, datetime, timedelta

from backend.database import SessionLocal
from backend.models.entities import Reminder
from backend.services.automation import fire_reminders


def _at(minutes: float) -> str:
    return (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()


def _backdate(reminder_id: str, minutes: float = 1) -> None:
    with SessionLocal() as db:
        db.get(Reminder, reminder_id).due_at = datetime.now(UTC) - timedelta(minutes=minutes)
        db.commit()


def test_create_list_and_cancel(client):
    created = client.post("/api/v1/reminders", json={"text": "Call home", "due_at": _at(60)})
    assert created.status_code == 201
    reminder = created.json()
    assert reminder["status"] == "pending" and reminder["text"] == "Call home"
    assert [item["id"] for item in client.get("/api/v1/reminders").json()] == [reminder["id"]]

    assert client.delete(f"/api/v1/reminders/{reminder['id']}").status_code == 204
    listed = client.get("/api/v1/reminders").json()
    assert listed[0]["status"] == "cancelled"
    # Cancelling twice, or dismissing something that never went off, is refused.
    assert client.delete(f"/api/v1/reminders/{reminder['id']}").status_code == 409
    assert client.post(f"/api/v1/reminders/{reminder['id']}/dismiss").status_code == 409


def test_due_reminder_fires_when_listed_and_can_be_dismissed(client):
    reminder = client.post("/api/v1/reminders", json={"text": "Stretch", "due_at": _at(30)}).json()
    _backdate(reminder["id"])
    fired = client.get("/api/v1/reminders").json()[0]
    assert fired["status"] == "fired" and fired["fired_at"]
    dismissed = client.post(f"/api/v1/reminders/{reminder['id']}/dismiss")
    assert dismissed.status_code == 200 and dismissed.json()["status"] == "dismissed"


def test_scheduler_fires_due_reminders_only(client):
    due = client.post("/api/v1/reminders", json={"text": "Due", "due_at": _at(30)}).json()
    later = client.post("/api/v1/reminders", json={"text": "Later", "due_at": _at(90)}).json()
    _backdate(due["id"])
    assert fire_reminders() == 1
    with SessionLocal() as db:
        assert db.get(Reminder, due["id"]).status == "fired"
        assert db.get(Reminder, later["id"]).status == "pending"
    assert fire_reminders() == 0


def test_old_finished_reminders_drop_out_of_the_list(client):
    old = client.post("/api/v1/reminders", json={"text": "Old", "due_at": _at(10)}).json()
    _backdate(old["id"], minutes=60 * 24 * 8)
    client.get("/api/v1/reminders")  # fires it
    client.post(f"/api/v1/reminders/{old['id']}/dismiss")
    assert client.get("/api/v1/reminders").json() == []


def test_due_time_needs_a_time_zone_and_text_is_required(client):
    naive = client.post("/api/v1/reminders", json={"text": "No zone", "due_at": "2026-12-01T09:00:00"})
    assert naive.status_code == 422
    assert client.post("/api/v1/reminders", json={"text": "", "due_at": _at(5)}).status_code == 422
    offset = client.post("/api/v1/reminders", json={"text": "IST", "due_at": "2026-12-01T09:00:00+05:30"})
    assert offset.status_code == 201
    assert offset.json()["due_at"].startswith("2026-12-01T03:30:00")


def test_reminders_are_private_to_their_owner(sign_in):
    alice, bob = sign_in("operator"), sign_in("admin")
    mine = alice.post("/api/v1/reminders", json={"text": "Alice only", "due_at": _at(30)}).json()
    assert bob.get("/api/v1/reminders").json() == []
    # Even an admin can't see, cancel or dismiss another person's reminder.
    assert bob.delete(f"/api/v1/reminders/{mine['id']}").status_code == 404
    _backdate(mine["id"])
    assert bob.post(f"/api/v1/reminders/{mine['id']}/dismiss").status_code == 404
    # Bob listing his reminders must not fire Alice's.
    bob.get("/api/v1/reminders")
    with SessionLocal() as db:
        assert db.get(Reminder, mine["id"]).status == "pending"
    assert alice.get("/api/v1/reminders").json()[0]["status"] == "fired"
