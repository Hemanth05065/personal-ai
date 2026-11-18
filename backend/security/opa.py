import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from backend.core.config import get_settings


@dataclass(frozen=True)
class OpaDecision:
    allow: bool
    approval_required: bool
    reason: str
    available: bool


def opa_available() -> bool:
    settings = get_settings()
    try:
        with urlopen(f"{settings.opa_url}/health", timeout=1) as response:
            return response.status == 200
    except (HTTPError, URLError, TimeoutError, OSError):
        return False


# When OPA is optional and not running, each refused connection still took 2 s on Windows,
# so every tool call paid it. After a failure, skip OPA for this long and use the local policy.
# -inf, not 0.0: time.monotonic() can be small on a freshly booted machine.
SKIP_AFTER_FAILURE_S = 60.0
_last_failure = float("-inf")


def evaluate_with_opa(input_document: dict) -> OpaDecision | None:
    global _last_failure
    settings = get_settings()
    if not settings.opa_required and time.monotonic() - _last_failure < SKIP_AFTER_FAILURE_S:
        return None
    body = json.dumps({"input": input_document}).encode()
    request = Request(
        f"{settings.opa_url}/v1/data/assistant/authz/decision",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=2) as response:
            result = json.loads(response.read().decode()).get("result")
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        if settings.opa_required:
            # Required: fail closed, and keep trying every time (no skipping).
            return OpaDecision(False, False, "OPA is required but unavailable; failing closed.", False)
        _last_failure = time.monotonic()
        return None
    if not isinstance(result, dict):
        return OpaDecision(False, False, "OPA returned no policy decision; failing closed.", True)
    return OpaDecision(
        bool(result.get("allow", False)),
        bool(result.get("approval_required", False)),
        str(result.get("reason", "OPA policy decision")),
        True,
    )
