import shutil
from dataclasses import dataclass

from backend.core.config import get_settings


@dataclass(frozen=True)
class SandboxStatus:
    available: bool
    enabled: bool
    mode: str
    detail: str


def sandbox_status() -> SandboxStatus:
    installed = shutil.which("openshell") is not None
    enabled = get_settings().openshell_enabled
    if enabled and installed:
        return SandboxStatus(True, True, "openshell", "OpenShell CLI detected; policy integration enabled.")
    if enabled and not installed:
        return SandboxStatus(False, True, "fail_closed", "OpenShell required but unavailable; code execution denied.")
    return SandboxStatus(installed, False, "disabled", "Arbitrary command execution is not exposed on the host.")


def require_sandbox() -> None:
    status = sandbox_status()
    if not (status.available and status.enabled):
        raise RuntimeError(status.detail)
