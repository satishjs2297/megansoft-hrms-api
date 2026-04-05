import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from jose import jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import AuthSession

settings = get_settings()
ALGORITHM = "HS256"


class RoleConfig(BaseModel):
    permissions: list[str]


class UserConfig(BaseModel):
    username: str
    role: str
    secret_env: str


class RBACConfig(BaseModel):
    roles: dict[str, RoleConfig]
    users: list[UserConfig]


class AuthenticatedUser(BaseModel):
    username: str
    role: str
    permissions: list[str]


@lru_cache(maxsize=1)
def get_rbac_config() -> RBACConfig:
    config_path = Path(settings.resolved_auth_config_file)
    if not config_path.exists():
        raise RuntimeError(f"RBAC config not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as file_obj:
        raw = json.load(file_obj)
    return RBACConfig.model_validate(raw)


def _get_secret_from_env_key(secret_env: str) -> str:
    env_key = (secret_env or "").strip().lower()
    if not env_key:
        return ""
    value = getattr(settings, env_key, "")
    return str(value).strip() if value is not None else ""


def authenticate_user(username: str, password: str) -> AuthenticatedUser | None:
    config = get_rbac_config()
    matched_user = next((u for u in config.users if u.username.lower() == username.lower()), None)
    if not matched_user:
        return None
    expected_secret = _get_secret_from_env_key(matched_user.secret_env)
    if not expected_secret or password != expected_secret:
        return None
    role = config.roles.get(matched_user.role)
    if not role:
        return None
    return AuthenticatedUser(
        username=matched_user.username,
        role=matched_user.role,
        permissions=role.permissions,
    )


def get_user_authorization(username: str) -> AuthenticatedUser | None:
    config = get_rbac_config()
    matched_user = next((u for u in config.users if u.username.lower() == username.lower()), None)
    if not matched_user:
        return None
    role = config.roles.get(matched_user.role)
    if not role:
        return None
    return AuthenticatedUser(
        username=matched_user.username,
        role=matched_user.role,
        permissions=role.permissions,
    )


def create_access_token(data: dict[str, Any]) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire, "typ": "access"})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token(data: dict[str, Any]) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    to_encode.update({"exp": expire, "typ": "refresh"})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    token_type = payload.get("typ")
    if expected_type and token_type != expected_type:
        raise ValueError(f"Invalid token type: expected {expected_type}")
    return payload


def hash_refresh_token(raw_token: str) -> str:
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        raw_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_session(
    db: Session,
    username: str,
    device_id: str,
    user_agent: str | None,
) -> tuple[AuthSession, str]:
    now = datetime.now(timezone.utc)
    device = (device_id or "unknown").strip()[:200]
    ua = (user_agent or "")[:500]

    # Keep recent sessions bounded per user.
    active_sessions = (
        db.query(AuthSession)
        .filter(AuthSession.username == username, AuthSession.revoked_at.is_(None))
        .order_by(AuthSession.created_at.desc())
        .all()
    )
    for stale in active_sessions[settings.auth_session_max_devices:]:
        stale.revoked_at = now
        stale.revoke_reason = "max_devices_exceeded"

    session = AuthSession(
        username=username,
        device_id=device or "unknown",
        user_agent=ua,
        refresh_token_hash="pending",
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(session)
    db.flush()

    refresh_token = create_refresh_token({"sub": username, "sid": session.id})
    session.refresh_token_hash = hash_refresh_token(refresh_token)
    db.commit()
    db.refresh(session)
    return session, refresh_token


def get_active_session(db: Session, session_id: int, username: str) -> AuthSession | None:
    now = datetime.now(timezone.utc)
    session = (
        db.query(AuthSession)
        .filter(AuthSession.id == session_id, AuthSession.username == username)
        .first()
    )
    if not session:
        return None
    if session.revoked_at is not None:
        return None
    if session.expires_at < now:
        return None
    return session


def rotate_refresh_token(db: Session, session: AuthSession) -> str:
    new_token = create_refresh_token({"sub": session.username, "sid": session.id})
    session.refresh_token_hash = hash_refresh_token(new_token)
    session.expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    db.commit()
    db.refresh(session)
    return new_token


def revoke_session(db: Session, session: AuthSession, reason: str = "manual_revoke") -> None:
    session.revoked_at = datetime.now(timezone.utc)
    session.revoke_reason = reason
    db.commit()


def revoke_all_user_sessions(db: Session, username: str, reason: str = "manual_revoke_all") -> int:
    now = datetime.now(timezone.utc)
    sessions = (
        db.query(AuthSession)
        .filter(AuthSession.username == username, AuthSession.revoked_at.is_(None))
        .all()
    )
    for session in sessions:
        session.revoked_at = now
        session.revoke_reason = reason
    db.commit()
    return len(sessions)
