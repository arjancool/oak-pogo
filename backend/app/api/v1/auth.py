"""Authentication endpoints (spec §20.1)."""

from __future__ import annotations

import re
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth, get_container, get_session, session_policy
from app.auth.passwords import hash_password, needs_rehash, validate_password, verify_password
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
from app.core.ratelimit import SlidingWindowLimiter, address_key
from app.models import AuditLog, User
from app.schemas.common import ApiModel, UtcDatetime

router = APIRouter(prefix="/auth", tags=["auth"])
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.\-]{3,32}$")
LANGUAGE = re.compile(r"[a-z]{2}")


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


def _reserve_login(container: Container, address: str, username: str) -> list[tuple[SlidingWindowLimiter, str]]:
    """Take a place in every limit before the password is checked, so attempts sent at the same
    time cannot all pass a limit that only one of them would fit in. Returns the places taken,
    to give back after a successful login.

    Ten failures block a username from one address, and thirty block an address for every
    username. The address comes first: a blocked address is refused before anything about the
    username is stored (audit F02 of 25 October). Many failures for one username from different
    addresses only slow it down, so nobody can lock another user out by guessing at the account.
    """
    taken: list[tuple[SlidingWindowLimiter, str]] = []

    def refuse(retry: int) -> RateLimitedError:
        for limiter, key in taken:
            limiter.release(key)
        return RateLimitedError(
            "Te veel mislukte inlogpogingen. Probeer het later opnieuw.", retry_after=retry, context="login"
        )

    for limiter, key in (
        (container.login_by_ip, f"ip:{address}"),
        (container.login_by_pair, f"pair:{address}|{username}"),
    ):
        retry = limiter.hit(key)
        if retry:
            raise refuse(retry)
        taken.append((limiter, key))
    user_key = f"user:{username}"
    if container.login_by_user.hit(user_key) is None:
        taken.append((container.login_by_user, user_key))
    else:
        retry = container.login_slow_by_user.hit(user_key)
        if retry:
            raise refuse(retry)
    return taken


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
        raise ValidationFailedError(
            "Gebruikersnaam: 3–32 tekens, letters, cijfers, punt, streepje of underscore.", context="username"
        )
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


# Argon2 takes a while and a lot of memory. Setup, registration and login therefore check what
# they can in a read transaction, hash or verify the password outside any transaction, and only
# then write, briefly. A write transaction would hold the database write lock during the hash, and
# every other writer, such as a webhook import, would have to wait (issue #40).


def _require_no_owner(session: Session) -> None:
    if (session.scalar(select(func.count()).select_from(User).where(User.role == "owner")) or 0) > 0:
        raise ConflictError("De eigenaar is al aangemaakt.", code="SETUP_DONE")


def _require_owner(session: Session) -> None:
    if not session.scalar(select(User.id).where(User.role == "owner").limit(1)):
        raise ConflictError("Registreren kan pas als de eigenaar is aangemaakt.", code="SETUP_REQUIRED")


def _require_free_username(session: Session, username: str) -> None:
    if session.scalar(select(User.id).where(User.username == username)):
        raise ConflictError("Deze gebruikersnaam bestaat al.", context="username_taken")


@router.post("/setup", response_model=AuthStatus, status_code=201)
def setup_owner(
    body: SetupRequest,
    request: Request,
    response: Response,
    container: Container = Depends(get_container),
) -> AuthStatus:
    """Create the owner. Only possible while no owner exists, also when a user registered
    earlier while registration was open before the owner existed (audit A09)."""
    with container.db.read() as session:
        _require_no_owner(session)
    username = validate_username(body.username)
    password_hash = hash_password(body.password)
    with container.db.transaction() as session:
        # Again in the write transaction, which serializes it with a registration (audit A09).
        _require_no_owner(session)
        now = container.clock.now()
        user = User(
            username=username,
            email=body.email,
            password_hash=password_hash,
            role="owner",
            status="active",
            preferences={},
            created_at=now,
            password_changed_at=now,
        )
        session.add(user)
        session.flush()
        token = create_session(session, user, session_policy(container), now, request.headers.get("user-agent"))
        audit(session, user.id, "owner_created", user.username, container)
        user_out = UserOut.model_validate(user)
    return AuthStatus(
        setup_required=False,
        registration_open=container.settings.allow_registration,
        authenticated=True,
        user=user_out,
        csrf_token=_set_cookies(response, container, token),
    )


@router.post("/register", response_model=AuthStatus, status_code=201)
def register(
    body: SetupRequest,
    request: Request,
    response: Response,
    container: Container = Depends(get_container),
) -> AuthStatus:
    if not container.settings.allow_registration:
        raise ForbiddenError("Registratie staat uit.", code="REGISTRATION_CLOSED")
    with container.db.read() as session:
        _require_owner(session)
    blocked = container.login_by_ip.hit(f"register:{address_key(_client_ip(request))}")
    if blocked:
        raise RateLimitedError("Te veel pogingen. Probeer het later opnieuw.", retry_after=blocked, context="register")
    username = validate_username(body.username)
    with container.db.read() as session:
        _require_free_username(session, username)
    password_hash = hash_password(body.password)
    with container.db.transaction() as session:
        # Again in the write transaction, which serializes these checks with the owner setup and
        # with another registration (audit A09).
        _require_owner(session)
        _require_free_username(session, username)
        now = container.clock.now()
        user = User(
            username=username,
            email=body.email,
            password_hash=password_hash,
            role="user",
            status="active",
            preferences={},
            created_at=now,
            password_changed_at=now,
        )
        session.add(user)
        session.flush()
        token = create_session(session, user, session_policy(container), now, request.headers.get("user-agent"))
        audit(session, user.id, "user_registered", user.username, container)
        user_out = UserOut.model_validate(user)
    return AuthStatus(
        setup_required=False,
        registration_open=True,
        authenticated=True,
        user=user_out,
        csrf_token=_set_cookies(response, container, token),
    )


@router.post("/login", response_model=AuthStatus)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    container: Container = Depends(get_container),
) -> AuthStatus:
    username = body.username.strip().lower()
    address = address_key(_client_ip(request))
    taken = _reserve_login(container, address, username)
    with container.db.read() as session:
        found = session.scalars(select(User).where(User.username == username)).first()
        user_id = found.id if found else None
        stored_hash = found.password_hash if found else None
        active = found is not None and found.status == "active"
    # Always verified, also for an unknown or disabled user, so the time it takes says nothing.
    valid = verify_password(stored_hash, body.password) and active
    new_hash = hash_password(body.password) if valid and stored_hash and needs_rehash(stored_hash) else None
    logged_in: tuple[str, UserOut] | None = None
    with container.db.transaction() as session:
        user = session.get(User, user_id) if valid and user_id is not None else None
        # The user may have been disabled, or the password changed, while it was being checked.
        if user is None or user.status != "active" or user.password_hash != stored_hash:
            # The places taken stay: they count this failure.
            audit(session, user_id, "login_failed", username, container)
        else:
            if new_hash:
                user.password_hash = new_hash
            now = container.clock.now()
            token = create_session(session, user, session_policy(container), now, request.headers.get("user-agent"))
            audit(session, user.id, "login", username, container)
            logged_in = token, UserOut.model_validate(user)
    if logged_in is None:
        raise UnauthorizedError("Onjuiste gebruikersnaam of wachtwoord.", code="INVALID_CREDENTIALS", context="login")
    token, user_out = logged_in
    for limiter, key in taken:
        limiter.release(key)
    container.login_by_pair.reset(f"pair:{address}|{username}")
    return AuthStatus(
        setup_required=False,
        registration_open=container.settings.allow_registration,
        authenticated=True,
        user=user_out,
        csrf_token=_set_cookies(response, container, token),
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
    language = body.preferences.get("language")
    # Which languages exist is up to the frontend (ADR-0025); here only the form is checked.
    if language is not None and not (isinstance(language, str) and LANGUAGE.fullmatch(language)):
        raise ValidationFailedError("Taal: een code van twee letters, zoals nl of en.", context="language")
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
    request: Request,
    response: Response,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> Response:
    validate_password(body.new_password)
    user_id, username, stored_hash = auth.user.id, auth.user.username, auth.user.password_hash
    # A place is taken before the check and given back on success, so only failures count, also
    # when several attempts arrive at the same time (issue #41).
    key = f"user:{user_id}"
    retry = container.password_checks_by_user.hit(key)
    if retry:
        raise RateLimitedError(
            "Te veel mislukte pogingen om je wachtwoord te wijzigen. Probeer het later opnieuw.",
            retry_after=retry,
            context="change_password",
        )
    # End the transaction the session check started, so Argon2 does not run while it holds the
    # write lock (issue #40). The next statement starts a new one.
    session.commit()
    valid = verify_password(stored_hash, body.current_password)
    new_hash = hash_password(body.new_password) if valid else None
    user = session.get(User, user_id)
    # The password may also have been changed elsewhere while this one was being checked.
    if new_hash is None or user is None or user.password_hash != stored_hash:
        audit(session, user_id, "password_change_failed", username, container)
        # Commit before the error response: the request's rollback would drop the entry.
        session.commit()
        raise UnauthorizedError(
            "Het huidige wachtwoord klopt niet.", code="INVALID_CREDENTIALS", context="current_password"
        )
    container.password_checks_by_user.release(key)
    now = container.clock.now()
    user.password_hash = new_hash
    user.password_changed_at = now
    # Every session ends, this one too: after a change of credentials a session gets a new token,
    # so a cookie copied before the change stops working (issue #42). The browser gets the new
    # session and CSRF cookies with this response.
    revoke_all_for_user(session, user_id, now)
    token = create_session(session, user, session_policy(container), now, request.headers.get("user-agent"))
    _set_cookies(response, container, token)
    audit(session, user_id, "password_changed", username, container)
    response.status_code = 204
    return response
