package assistant.authz

import rego.v1

role_max := {"viewer": 1, "operator": 2, "admin": 3}

prohibited := {
    "purchase",
    "transfer_money",
    "delete_important_files",
    "change_credentials",
    "physical_security",
}

default allow := false
default approval_required := false

allow if {
    not input.emergency_stopped
    input.risk_level <= role_max[input.role]
    input.risk_level < 4
    not input.action in prohibited
}

approval_required if {
    allow
    input.risk_level >= 2
}

reason := "Denied by centralized OPA authorization policy." if not allow
reason := "Explicit approval is required by centralized OPA policy." if approval_required
reason := "Allowed by centralized OPA authorization policy." if {
    allow
    not approval_required
}

decision := {
    "allow": allow,
    "approval_required": approval_required,
    "reason": reason,
}
