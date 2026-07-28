from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..auth import (
    cookie_max_age,
    create_session_token,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)
from ..config import Settings, get_settings
from ..database import get_db
from ..models import User
from ..schemas import ChangePasswordRequest, LoginRequest, LoginResponse, MessageOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_session_token(user.username, settings)
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=cookie_max_age(settings),
        path="/",
    )
    return LoginResponse(username=user.username, is_admin=user.is_admin)


@router.post("/logout", response_model=MessageOut)
def logout(response: Response, settings: Settings = Depends(get_settings)):
    response.delete_cookie(settings.cookie_name, path="/")
    return MessageOut(message="Logged out")


@router.get("/me", response_model=LoginResponse)
def me(user: User = Depends(get_current_user)):
    return LoginResponse(username=user.username, is_admin=user.is_admin)


@router.post("/change-password", response_model=MessageOut)
def change_password(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password incorrect")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return MessageOut(message="Password updated")
