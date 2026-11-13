# OpenShell integration status

The repository includes a restrictive NVIDIA OpenShell policy, but arbitrary
command execution is not exposed by this application. The backend reports one
of three states: `disabled`, `openshell`, or `fail_closed`.

On this native Windows development host OpenShell is intentionally disabled.
NVIDIA documents the native Windows MXC path as development-stage and not
production-qualified. Setting `ASSISTANT_OPENSHELL_ENABLED=true` without an
available `openshell` executable makes sandbox-required execution fail closed;
it never falls back to the host shell.

For a supported Linux/container environment, install OpenShell from NVIDIA's
official distribution, validate `policy.yaml`, create the sandbox with the
policy at startup, and only then enable the setting. Keep `landlock` at
`hard_requirement`; paths outside the listed sets and all network destinations
are denied.
