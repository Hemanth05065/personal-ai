package assistant.authz_test

import data.assistant.authz.decision
import rego.v1

test_viewer_read_allowed if {
    result := decision with input as {
        "action": "read_file",
        "risk_level": 1,
        "role": "viewer",
        "emergency_stopped": false,
    }
    result.allow
    not result.approval_required
}

test_operator_write_needs_approval if {
    result := decision with input as {
        "action": "write_file",
        "risk_level": 2,
        "role": "operator",
        "emergency_stopped": false,
    }
    result.allow
    result.approval_required
}

test_emergency_denies if {
    result := decision with input as {
        "action": "read_file",
        "risk_level": 1,
        "role": "admin",
        "emergency_stopped": true,
    }
    not result.allow
}

test_prohibited_denied if {
    result := decision with input as {
        "action": "purchase",
        "risk_level": 3,
        "role": "admin",
        "emergency_stopped": false,
    }
    not result.allow
}
