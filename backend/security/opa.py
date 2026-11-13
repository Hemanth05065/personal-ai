import json
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


def evaluate_with_opa(input_document: dict) -> OpaDecision | None:
    settings = get_settings()
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
            return OpaDecision(False, False, "OPA is required but unavailable; failing closed.", False)
        return None
    if not isinstance(result, dict):
        return OpaDecision(False, False, "OPA returned no policy decision; failing closed.", True)
    return OpaDecision(
        bool(result.get("allow", False)),
        bool(result.get("approval_required", False)),
        str(result.get("reason", "OPA policy decision")),
        True,
    )
