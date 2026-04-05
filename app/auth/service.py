import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from jose import jwt
from pydantic import BaseModel

from app.config import get_settings

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


def create_access_token(data: dict[str, Any]) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
