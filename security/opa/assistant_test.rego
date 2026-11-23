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

test_viewer_write_denied if {
	result := decision with input as {
		"action": "write_file",
		"risk_level": 2,
		"role": "viewer",
		"emergency_stopped": false,
	}
	not result.allow
}

test_operator_sensitive_denied if {
	result := decision with input as {
		"action": "write_file",
		"risk_level": 3,
		"role": "operator",
		"emergency_stopped": false,
	}
	not result.allow
}

test_admin_sensitive_needs_approval if {
	result := decision with input as {
		"action": "write_file",
		"risk_level": 3,
		"role": "admin",
		"emergency_stopped": false,
	}
	result.allow
	result.approval_required
}

test_risk_four_always_denied if {
	result := decision with input as {
		"action": "read_file",
		"risk_level": 4,
		"role": "admin",
		"emergency_stopped": false,
	}
	not result.allow
}

test_unknown_role_denied if {
	result := decision with input as {
		"action": "list_files",
		"risk_level": 0,
		"role": "guest",
		"emergency_stopped": false,
	}
	not result.allow
}

test_every_decision_has_a_reason if {
	result := decision with input as {
		"action": "read_file",
		"risk_level": 1,
		"role": "operator",
		"emergency_stopped": false,
	}
	result.reason == "Allowed by centralized OPA authorization policy."
}
