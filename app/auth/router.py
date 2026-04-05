from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from jose import JWTError
from app.auth.service import authenticate_user, create_access_token, decode_token

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

class Token(BaseModel):
    access_token: str
    token_type: str
    username: str
    role: str
    permissions: list[str]


class CurrentUser(BaseModel):
    username: str
    role: str
    permissions: list[str]


def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    try:
        payload = decode_token(token)
        username: str = payload.get("sub")
        role: str = payload.get("role")
        permissions: list[str] = payload.get("permissions", [])
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
        if not role:
            raise HTTPException(status_code=401, detail="Invalid token")
        return CurrentUser(username=username, role=role, permissions=permissions)
    except JWTError:
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


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token({"sub": user.username, "role": user.role, "permissions": user.permissions})
    return Token(
        access_token=token,
        token_type="bearer",
        username=user.username,
        role=user.role,
        permissions=user.permissions,
    )

@router.get("/me")
def get_me(current_user: CurrentUser = Depends(get_current_user)):
    return {
        "username": current_user.username,
        "role": current_user.role,
        "permissions": current_user.permissions,
    }
