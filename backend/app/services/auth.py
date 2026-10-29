from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User
from app.repositories.users import by_email

password_hash = PasswordHash.recommended()


def serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret.get_secret_value(), salt="bi-platform-session-v1")


def create_user(db: Session, name: str, email: str, password: str) -> User:
    normalized = email.strip().lower()
    if by_email(db, normalized):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(name=name, email=normalized, password_hash=password_hash.hash(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = by_email(db, email.strip().lower())
    if not user or not password_hash.verify(password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect")
    return user


def issue_session(user: User) -> str:
    return serializer().dumps({"sub": user.id, "iat": int(datetime.now(timezone.utc).timestamp())})


def current_user(request: Request, db: Session) -> User:
    token = request.cookies.get("bi_session")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    max_age = get_settings().session_ttl_hours * 3600
    try:
        payload = serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session is invalid or expired") from None
    user = db.get(User, payload.get("sub"))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session is invalid or expired")
    return user
