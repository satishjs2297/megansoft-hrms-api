import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.service import (
    authenticate_user,
    create_access_token,
    create_session,
    decode_token,
    get_user_authorization,
    get_active_session,
    hash_refresh_token,
    revoke_all_user_sessions,
    revoke_session,
    rotate_refresh_token,
)
from app.database import AuthSession, get_db
from app.security.rate_limiter import rate_limit

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
audit_logger = logging.getLogger("audit")


class Token(BaseModel):
    access_token: str
    refresh_token: str
    session_id: int
    token_type: str
    username: str
    role: str
    permissions: list[str]


class RefreshRequest(BaseModel):
    refresh_token: str
    device_id: str | None = None


class RevokeRequest(BaseModel):
    session_id: int | None = None
    all_devices: bool = False


class CurrentUser(BaseModel):
    username: str
    role: str
    permissions: list[str]
    session_id: int | None = None


def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    try:
        payload = decode_token(token, expected_type="access")
        username: str = payload.get("sub")
        role: str = payload.get("role")
        permissions: list[str] = payload.get("permissions", [])
        session_id = payload.get("sid")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
        if not role:
            raise HTTPException(status_code=401, detail="Invalid token")
        return CurrentUser(username=username, role=role, permissions=permissions, session_id=session_id)
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")


def require_permissions(*required_permissions: str):
    permission_set = {p for p in required_permissions if p}

    def checker(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        user_permissions = set(current_user.permissions)
        if "*" in user_permissions:
            return current_user
        if permission_set and permission_set.intersection(user_permissions):
            return current_user
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    return checker


@router.post("/login", response_model=Token, dependencies=[Depends(rate_limit("login"))])
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    session, refresh_token = create_session(
        db=db,
        username=user.username,
        device_id=x_device_id or "unknown",
        user_agent=request.headers.get("user-agent"),
    )
    access_token = create_access_token(
        {
            "sub": user.username,
            "role": user.role,
            "permissions": user.permissions,
            "sid": session.id,
        }
    )
    _audit(
        action="auth.login",
        username=user.username,
        request=request,
        details={"session_id": session.id, "device_id": session.device_id},
    )
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        session_id=session.id,
        token_type="bearer",
        username=user.username,
        role=user.role,
        permissions=user.permissions,
    )


@router.post("/refresh", response_model=Token)
def refresh(
    payload: RefreshRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("heavy")),
):
    try:
        token_payload = decode_token(payload.refresh_token, expected_type="refresh")
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    username = token_payload.get("sub")
    session_id = token_payload.get("sid")
    if not username or not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    session = get_active_session(db, int(session_id), username)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or revoked")

    if payload.device_id and session.device_id != payload.device_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Device mismatch")

    if session.refresh_token_hash != hash_refresh_token(payload.refresh_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token rotated or invalid")

    refresh_token = rotate_refresh_token(db, session)
    user = get_user_authorization(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer authorized")
    role = user.role
    permissions = user.permissions

    session.user_agent = (request.headers.get("user-agent") or "")[:500]
    db.commit()

    access_token = create_access_token({"sub": username, "role": role, "permissions": permissions, "sid": session.id})
    _audit(
        action="auth.refresh",
        username=username,
        request=request,
        details={"session_id": session.id},
    )
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        session_id=session.id,
        token_type="bearer",
        username=username,
        role=role,
        permissions=permissions,
    )


@router.get("/sessions")
def list_sessions(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    sessions = (
        db.query(AuthSession)
        .filter(AuthSession.username == current_user.username)
        .order_by(AuthSession.created_at.desc())
        .all()
    )
    return {
        "sessions": [
            {
                "id": s.id,
                "device_id": s.device_id,
                "user_agent": s.user_agent,
                "created_at": s.created_at,
                "expires_at": s.expires_at,
                "revoked_at": s.revoked_at,
                "active": s.revoked_at is None and s.expires_at >= now,
            }
            for s in sessions
        ]
    }


@router.post("/revoke")
def revoke(
    request: Request,
    payload: RevokeRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if payload.all_devices:
        count = revoke_all_user_sessions(db, current_user.username, reason="user_revoked_all")
        _audit(
            action="auth.revoke_all",
            username=current_user.username,
            request=request,
            details={"revoked_sessions": count},
        )
        return {"revoked_sessions": count}

    target_session_id = payload.session_id or current_user.session_id
    if not target_session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    session = get_active_session(db, int(target_session_id), current_user.username)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    revoke_session(db, session, reason="user_revoked_single")
    _audit(
        action="auth.revoke_single",
        username=current_user.username,
        request=request,
        details={"revoked_session_id": session.id},
    )
    return {"revoked_session_id": session.id}


@router.get("/me")
def get_me(current_user: CurrentUser = Depends(get_current_user)):
    return {
        "username": current_user.username,
        "role": current_user.role,
        "permissions": current_user.permissions,
        "session_id": current_user.session_id,
    }


def _audit(action: str, username: str, request: Request, details: dict | None = None):
    payload = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "action": action,
        "username": username,
        "request_id": getattr(request.state, "request_id", None),
        "ip": request.client.host if request.client else None,
        "details": details or {},
    }
    audit_logger.info(json.dumps(payload))
