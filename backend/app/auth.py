from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import get_db
from .models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def serializer(settings: Settings | None = None) -> URLSafeTimedSerializer:
    s = settings or get_settings()
    return URLSafeTimedSerializer(s.secret_key, salt="premarket-session")


def create_session_token(username: str, settings: Settings | None = None) -> str:
    return serializer(settings).dumps({"u": username})


def read_session_token(token: str, settings: Settings | None = None) -> str:
    s = settings or get_settings()
    max_age = s.session_hours * 3600
    try:
        data = serializer(s).loads(token, max_age=max_age)
    except SignatureExpired as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired") from exc
    except BadSignature as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from exc
    return str(data["u"])


def get_current_user(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> User:
    token = request.cookies.get(settings.cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    username = read_session_token(token, settings)
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


def cookie_max_age(settings: Settings) -> int:
    return int(timedelta(hours=settings.session_hours).total_seconds())
