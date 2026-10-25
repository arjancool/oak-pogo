"""Authentication endpoints (spec §20.1)."""

from __future__ import annotations

import re
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth, get_container, get_session, session_policy
from app.auth.passwords import hash_password, needs_rehash, verify_password
from app.auth.sessions import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    create_session,
    resolve_session,
    revoke_all_for_user,
    revoke_session,
)
from app.auth.tokens import csrf_token_for
from app.core.container import Container
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    RateLimitedError,
    UnauthorizedError,
    ValidationFailedError,
)
from app.models import AuditLog, User
from app.schemas.common import ApiModel, UtcDatetime

router = APIRouter(prefix="/auth", tags=["auth"])
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.\-]{3,32}$")


class LoginRequest(ApiModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


class SetupRequest(ApiModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)
    email: str | None = Field(default=None, max_length=254)


class ChangePasswordRequest(ApiModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class UserOut(ApiModel):
    id: int
    username: str
    email: str | None
    role: str
    status: str
    created_at: UtcDatetime
    last_login_at: UtcDatetime | None
    preferences: dict[str, object]


class AuthStatus(ApiModel):
    setup_required: bool
    registration_open: bool
    authenticated: bool
    user: UserOut | None
    csrf_token: str | None


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_cookies(response: Response, container: Container, token: str) -> str:
    settings = container.settings
    csrf = csrf_token_for(container.secret, token)
    max_age = int(timedelta(days=settings.session_max_days).total_seconds())
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=max_age,
        httponly=False,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    return csrf


def validate_username(username: str) -> str:
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValidationFailedError("Gebruikersnaam: 3–32 tekens, letters, cijfers, punt, streepje of underscore.")
    return username.lower()


def audit(
    session: Session,
    user_id: int | None,
    action: str,
    target: str | None,
    container: Container,
    details: dict[str, object] | None = None,
) -> None:
    session.add(
        AuditLog(
            user_id=user_id,
            action=action,
            target=target,
            details=details,
            created_at=container.clock.now(),
        )
    )


@router.get("/status", response_model=AuthStatus)
def auth_status(
    request: Request,
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> AuthStatus:
    owners = session.scalar(select(func.count()).select_from(User).where(User.role == "owner")) or 0
    user = None
    csrf = None
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        resolved = resolve_session(session, token, session_policy(container), container.clock.now())
        if resolved:
            user = UserOut.model_validate(resolved[0])
            csrf = csrf_token_for(container.secret, token)
    return AuthStatus(
        setup_required=owners == 0,
        registration_open=container.settings.allow_registration,
        authenticated=user is not None,
        user=user,
        csrf_token=csrf,
    )


@router.post("/setup", response_model=AuthStatus, status_code=201)
def setup_owner(
    body: SetupRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> AuthStatus:
    """Create the owner. Only possible while no owner exists, also when a user registered
    earlier while registration was open before the owner existed (audit A09)."""
    if (session.scalar(select(func.count()).select_from(User).where(User.role == "owner")) or 0) > 0:
        raise ConflictError("De eigenaar is al aangemaakt.", code="SETUP_DONE")
    now = container.clock.now()
    user = User(
        username=validate_username(body.username),
        email=body.email,
        password_hash=hash_password(body.password),
        role="owner",
        status="active",
        preferences={},
        created_at=now,
        password_changed_at=now,
    )
    session.add(user)
    session.flush()
    token = create_session(session, user, session_policy(container), now, request.headers.get("user-agent"))
    csrf = _set_cookies(response, container, token)
    audit(session, user.id, "owner_created", user.username, container)
    return AuthStatus(
        setup_required=False,
        registration_open=container.settings.allow_registration,
        authenticated=True,
        user=UserOut.model_validate(user),
        csrf_token=csrf,
    )


@router.post("/register", response_model=AuthStatus, status_code=201)
def register(
    body: SetupRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> AuthStatus:
    if not container.settings.allow_registration:
        raise ForbiddenError("Registratie staat uit.", code="REGISTRATION_CLOSED")
    # The write transaction serializes this check with the owner setup (audit A09).
    if not session.scalar(select(User.id).where(User.role == "owner").limit(1)):
        raise ConflictError("Registreren kan pas als de eigenaar is aangemaakt.", code="SETUP_REQUIRED")
    blocked = container.login_by_ip.hit(f"register:{_client_ip(request)}")
    if blocked:
        raise RateLimitedError("Te veel pogingen. Probeer het later opnieuw.", retry_after=blocked)
    username = validate_username(body.username)
    if session.scalar(select(User.id).where(User.username == username)):
        raise ConflictError("Deze gebruikersnaam bestaat al.")
    now = container.clock.now()
    user = User(
        username=username,
        email=body.email,
        password_hash=hash_password(body.password),
        role="user",
        status="active",
        preferences={},
        created_at=now,
        password_changed_at=now,
    )
    session.add(user)
    session.flush()
    token = create_session(session, user, session_policy(container), now, request.headers.get("user-agent"))
    csrf = _set_cookies(response, container, token)
    audit(session, user.id, "user_registered", user.username, container)
    return AuthStatus(
        setup_required=False,
        registration_open=True,
        authenticated=True,
        user=UserOut.model_validate(user),
        csrf_token=csrf,
    )


@router.post("/login", response_model=AuthStatus)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> AuthStatus:
    username = body.username.strip().lower()
    ip = _client_ip(request)
    for limiter, key in (
        (container.login_by_user, f"user:{username}"),
        (container.login_by_ip, f"ip:{ip}"),
    ):
        retry = limiter.blocked(key)
        if retry:
            raise RateLimitedError("Te veel mislukte inlogpogingen. Probeer het later opnieuw.", retry_after=retry)
    user = session.scalars(select(User).where(User.username == username)).first()
    if (
        not verify_password(user.password_hash if user else None, body.password)
        or user is None
        or user.status != "active"
    ):
        container.login_by_user.hit(f"user:{username}")
        container.login_by_ip.hit(f"ip:{ip}")
        audit(session, user.id if user else None, "login_failed", username, container)
        # Commit before the error response: the request's rollback would drop the entry (audit A08).
        session.commit()
        raise UnauthorizedError("Onjuiste gebruikersnaam of wachtwoord.", code="INVALID_CREDENTIALS")
    container.login_by_user.reset(f"user:{username}")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    now = container.clock.now()
    token = create_session(session, user, session_policy(container), now, request.headers.get("user-agent"))
    csrf = _set_cookies(response, container, token)
    audit(session, user.id, "login", username, container)
    return AuthStatus(
        setup_required=False,
        registration_open=container.settings.allow_registration,
        authenticated=True,
        user=UserOut.model_validate(user),
        csrf_token=csrf,
    )


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> Response:
    revoke_session(session, auth.token, container.clock.now())
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(auth: AuthContext = Depends(get_auth)) -> UserOut:
    return UserOut.model_validate(auth.user)


class PreferencesRequest(ApiModel):
    preferences: dict[str, object]


@router.put("/me/preferences", response_model=UserOut)
def update_preferences(
    body: PreferencesRequest,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
) -> UserOut:
    allowed = {"active_account_id", "box_view", "box_columns", "page_size", "theme", "language"}
    user = session.get(User, auth.user.id)
    assert user is not None
    user.preferences = {
        **(user.preferences or {}),
        **{k: v for k, v in body.preferences.items() if k in allowed},
    }
    return UserOut.model_validate(user)


@router.post("/change-password", status_code=204)
def change_password(
    body: ChangePasswordRequest,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> Response:
    user = session.get(User, auth.user.id)
    assert user is not None
    if not verify_password(user.password_hash, body.current_password):
        raise UnauthorizedError("Het huidige wachtwoord klopt niet.", code="INVALID_CREDENTIALS")
    now = container.clock.now()
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = now
    revoke_all_for_user(session, user.id, now, except_id=auth.record.id)
    audit(session, user.id, "password_changed", user.username, container)
    return Response(status_code=204)
