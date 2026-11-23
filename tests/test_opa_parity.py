"""The Rego policy and the local Python policy must agree.

The app uses the local policy when OPA isn't running (the usual case on Windows, where App
Control blocks opa.exe) and asks OPA when it is. Two policies that disagree would mean the
same action is allowed on one install and denied on another. CI starts a real OPA server with
security/opa/assistant.rego and sets OPA_PARITY_URL; without it, these tests are skipped.
"""

import itertools
import json
import os
from urllib.request import Request, urlopen

import pytest

from backend.core.policy import PROHIBITED_ACTIONS, RiskLevel, evaluate_action

OPA = os.environ.get("OPA_PARITY_URL")
pytestmark = pytest.mark.skipif(not OPA, reason="needs a running OPA server (set OPA_PARITY_URL)")

ACTIONS = ["list_files", "read_file", "write_file", "web_search", *sorted(PROHIBITED_ACTIONS)]
ROLES = ["viewer", "operator", "admin", "guest"]
GRID = list(itertools.product(ACTIONS, list(RiskLevel), ROLES, [False, True]))


def ask_opa(action, risk, role, stopped):
    body = json.dumps({"input": {"action": action, "risk_level": int(risk), "role": role,
                                 "emergency_stopped": stopped}}).encode()
    request = Request(f"{OPA}/v1/data/assistant/authz/decision", body, {"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        return json.load(response)["result"]


def local_only(monkeypatch, action, risk, role, stopped):
    monkeypatch.setattr("backend.core.policy.evaluate_with_opa", lambda document: None)
    return evaluate_action(action, risk, role, stopped)


@pytest.mark.parametrize("action, risk, role, stopped", GRID)
def test_rego_and_python_agree(monkeypatch, action, risk, role, stopped):
    rego = ask_opa(action, risk, role, stopped)
    python = local_only(monkeypatch, action, risk, role, stopped)
    assert rego["allow"] == python.allowed, (rego, python)
    if python.allowed:
        assert rego["approval_required"] == python.approval_required, (rego, python)
    assert rego["reason"]


def test_the_app_really_asks_opa_when_it_is_required(monkeypatch):
    """With OPA required, plan decisions come from the server: its reason text shows it."""
    from backend.core.config import get_settings

    monkeypatch.setattr(get_settings(), "opa_url", OPA)
    monkeypatch.setattr(get_settings(), "opa_required", True)
    decision = evaluate_action("write_file", RiskLevel.LIMITED_ACTION, "operator")
    assert decision.allowed and decision.approval_required
    assert "centralized OPA" in decision.reason
