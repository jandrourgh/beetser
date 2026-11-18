"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ..schemas import LoginRequest, PasswordChangeRequest, SetupRequest
from ..security import AuthService
from .deps import client_id, get_auth, is_secure_request, require_auth

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookie(response: Response, auth: AuthService, request: Request) -> None:
    response.set_cookie(
        key=auth.cookie_name,
        value=auth.create_token(),
        max_age=auth.max_age,
        httponly=True,
        samesite="lax",
        secure=is_secure_request(request),
        path="/",
    )


@router.get("/status")
def status_(request: Request, auth: AuthService = Depends(get_auth)) -> dict:
    token = request.cookies.get(auth.cookie_name)
    return {
        "authenticated": auth.validate_token(token),
        "setup_required": auth.setup_required(),
    }


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth),
) -> dict:
    client = client_id(request)
    locked = auth.is_locked(client)
    if locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many attempts. Try again in {locked} seconds.",
        )
    if auth.setup_required():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Setup required",
        )
    if not auth.check_password(payload.password):
        auth.record_failure(client)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
        )
    auth.clear_failures(client)
    _set_cookie(response, auth, request)
    return {"ok": True}


@router.post("/setup")
def setup(
    payload: SetupRequest,
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth),
) -> dict:
    if not auth.setup_required():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Already configured",
        )
    auth.change_password(payload.password)
    _set_cookie(response, auth, request)
    return {"ok": True}


@router.post("/logout")
def logout(response: Response, auth: AuthService = Depends(get_auth)) -> dict:
    response.delete_cookie(auth.cookie_name, path="/")
    return {"ok": True}


@router.post("/password", dependencies=[Depends(require_auth)])
def change_password(
    payload: PasswordChangeRequest, auth: AuthService = Depends(get_auth)
) -> dict:
    if not auth.check_password(payload.current_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )
    auth.change_password(payload.new_password)
    return {"ok": True}
