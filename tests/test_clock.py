"""The model is told today's date and time: a local model has no clock of its own."""

from datetime import datetime, timedelta, timezone

from backend.core.config import get_settings
from backend.services import ollama


def test_every_request_carries_the_current_date_and_time(monkeypatch):
    ist = timezone(timedelta(hours=5, minutes=30), "IST")
    monkeypatch.setattr(ollama, "_now", lambda: datetime(2026, 11, 18, 16, 52, tzinfo=ist))
    payload = ollama.OllamaClient(get_settings())._payload([{"role": "user", "content": "date?"}], [], stream=True)
    system = payload["messages"][0]["content"]
    assert "Wednesday, 18 November 2026, 16:52 (IST, UTC+05:30)" in system


def test_the_time_is_read_fresh_for_each_request(monkeypatch):
    times = iter([datetime(2026, 1, 1, 9, 0).astimezone(), datetime(2026, 1, 2, 9, 0).astimezone()])
    monkeypatch.setattr(ollama, "_now", lambda: next(times))
    assert "01 January" in ollama.clock_text()
    assert "02 January" in ollama.clock_text()
