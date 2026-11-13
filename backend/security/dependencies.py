from typing import Annotated

from fastapi import Depends, HTTPException, Request

from backend.security.auth import Principal

# Higher rank includes everything a lower rank may do.
ROLE_RANK = {"viewer": 0, "operator": 1, "admin": 2}


def current_principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return principal


PrincipalDependency = Annotated[Principal, Depends(current_principal)]


def has_role(principal: Principal, minimum: str) -> bool:
    return ROLE_RANK.get(principal.role, -1) >= ROLE_RANK[minimum]


def require_role(minimum: str):
    def dependency(principal: PrincipalDependency) -> Principal:
        if not has_role(principal, minimum):
            raise HTTPException(status_code=403, detail=f"The {minimum} role or higher is required")
        return principal

    return dependency


def require_admin(principal: PrincipalDependency) -> Principal:
    if principal.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator role required")
    return principal


AdminDependency = Annotated[Principal, Depends(require_admin)]
# Operators and admins may change state; viewers may only read.
OperatorDependency = Annotated[Principal, Depends(require_role("operator"))]
