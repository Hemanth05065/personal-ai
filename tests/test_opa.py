"""OPA client: optional OPA that isn't running mustn't slow every tool call."""

from urllib.error import URLError

import pytest

from backend.core.config import get_settings
from backend.security import opa


@pytest.fixture
def unreachable(monkeypatch):
    calls = []

    def refuse(*args, **kwargs):
        calls.append(1)
        raise URLError("connection refused")

    monkeypatch.setattr(opa, "urlopen", refuse)
    monkeypatch.setattr(opa, "_last_failure", float("-inf"))
    return calls


def test_optional_opa_is_skipped_for_a_while_after_a_failure(unreachable, monkeypatch):
    monkeypatch.setattr(get_settings(), "opa_required", False)
    assert opa.evaluate_with_opa({}) is None
    assert opa.evaluate_with_opa({}) is None
    assert len(unreachable) == 1  # the second call didn't wait on the network

    monkeypatch.setattr(opa, "_last_failure", opa.time.monotonic() - opa.SKIP_AFTER_FAILURE_S - 1)
    assert opa.evaluate_with_opa({}) is None
    assert len(unreachable) == 2  # tried again once the window passed


def test_required_opa_fails_closed_every_time(unreachable, monkeypatch):
    monkeypatch.setattr(get_settings(), "opa_required", True)
    for _ in range(2):
        decision = opa.evaluate_with_opa({})
        assert decision is not None and not decision.allow
    assert len(unreachable) == 2  # never skipped: each decision really checked
