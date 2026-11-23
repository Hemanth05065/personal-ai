from dataclasses import dataclass
from enum import IntEnum

from backend.security.opa import evaluate_with_opa


class RiskLevel(IntEnum):
    INFORMATION = 0
    READ_ONLY = 1
    LIMITED_ACTION = 2
    SENSITIVE = 3
    PROHIBITED = 4


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    approval_required: bool
    reason: str


PROHIBITED_ACTIONS = {
    "purchase",
    "transfer_money",
    "delete_important_files",
    "change_credentials",
    "physical_security",
}

ROLE_MAX_RISK = {
    "viewer": RiskLevel.READ_ONLY,
    "operator": RiskLevel.LIMITED_ACTION,
    "admin": RiskLevel.SENSITIVE,
}


def evaluate_action(
    action: str,
    risk: RiskLevel,
    role: str = "admin",
    emergency_stopped: bool = False,
) -> PolicyDecision:
    if emergency_stopped:
        return PolicyDecision(
            False, False, "Emergency stop is active; autonomous operations are disabled."
        )
    if action in PROHIBITED_ACTIONS or risk >= RiskLevel.PROHIBITED:
        return PolicyDecision(False, False, "This action is denied by the local safety policy.")
    role_limit = ROLE_MAX_RISK.get(role)
    if role_limit is None:
        # The same as the Rego policy: a role it doesn't know gets nothing, not risk 0.
        return PolicyDecision(False, False, f"Role {role!r} is not a known role.")
    if risk > role_limit:
        return PolicyDecision(
            False, False, f"Role {role!r} is not authorized for risk level {int(risk)}."
        )
    local_approval = risk >= RiskLevel.LIMITED_ACTION
    opa = evaluate_with_opa(
        {
            "action": action,
            "risk_level": int(risk),
            "role": role,
            "emergency_stopped": emergency_stopped,
        }
    )
    if opa is not None:
        if not opa.allow:
            return PolicyDecision(False, False, opa.reason)
        return PolicyDecision(True, local_approval or opa.approval_required, opa.reason)
    if local_approval:
        return PolicyDecision(True, True, "Explicit user approval is required before execution.")
    return PolicyDecision(True, False, "Action is permitted within the current authorization.")
