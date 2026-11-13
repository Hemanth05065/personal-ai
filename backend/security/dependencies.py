from typing import Annotated

from fastapi import Depends, HTTPException, Request

from backend.security.auth import Principal


def current_principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return principal


PrincipalDependency = Annotated[Principal, Depends(current_principal)]


def require_admin(principal: PrincipalDependency) -> Principal:
    if principal.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator role required")
    return principal


AdminDependency = Annotated[Principal, Depends(require_admin)]
