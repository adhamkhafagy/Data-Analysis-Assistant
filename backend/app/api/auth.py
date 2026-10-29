from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.schemas.auth import LoginRequest, RegisterRequest, UserResponse
from app.services.auth import authenticate, create_user, issue_session

router = APIRouter(prefix="/auth", tags=["authentication"])
COOKIE = "bi_session"


def set_session(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(COOKIE, token, max_age=settings.session_ttl_hours * 3600,
                        httponly=True, secure=settings.cookie_secure, samesite="lax", path="/")


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, response: Response, db: DbSession):
    user = create_user(db, body.name, str(body.email), body.password)
    set_session(response, issue_session(user))
    return user


@router.post("/login", response_model=UserResponse)
def login(body: LoginRequest, response: Response, db: DbSession):
    user = authenticate(db, str(body.email), body.password)
    set_session(response, issue_session(user))
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/", httponly=True, secure=get_settings().cookie_secure, samesite="lax")


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser):
    return user
