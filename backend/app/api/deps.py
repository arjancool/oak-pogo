"""Request-scoped dependencies: database session, authentication, account authorization."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.auth.sessions import CSRF_HEADER, SESSION_COOKIE, SessionPolicy, check_session, store_session_check
from app.auth.tokens import constant_time_equal, csrf_token_for
from app.core.container import Container
from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.models import Pokemon, TrainerAccount, User, UserSession

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
log = logging.getLogger("oak.auth")


def get_container(request: Request) -> Container:
    return request.app.state.container  # type: ignore[no-any-return]


def get_session(request: Request, container: Container = Depends(get_container)) -> Iterator[Session]:
    # Safe methods read; everything else may write and takes the write lock at its first query.
    with container.db.session(write=request.method in UNSAFE_METHODS) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def session_policy(container: Container) -> SessionPolicy:
    settings = container.settings
    return SessionPolicy(
        idle=timedelta(hours=settings.session_idle_hours),
        absolute=timedelta(days=settings.session_max_days),
    )


@dataclass(frozen=True, slots=True)
class AuthContext:
    user: User
    record: UserSession
    token: str


def get_auth(
    request: Request,
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> AuthContext:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise UnauthorizedError("Je bent niet ingelogd.", context="not_logged_in")
    now = container.clock.now()
    check = check_session(session, token, session_policy(container), now)
    if check.expired or check.touch:
        if request.method in UNSAFE_METHODS:
            # This request's transaction already holds the write lock.
            store_session_check(session, check, now)
        else:
            # A read request never upgrades its own snapshot to a write: a writer that committed
            # in between would make that fail with "database is locked" (audit A10). Moving
            # last_seen_at is best effort; a busy database only delays it.
            try:
                with container.db.transaction() as writer:
                    store_session_check(writer, check, now)
            except OperationalError:
                # An expired session stays refused anyway; the revocation follows next time.
                log.debug("session update skipped: database busy")
    if check.user is None or check.record is None:
        session.commit()
        raise UnauthorizedError("Je sessie is verlopen. Log opnieuw in.", context="session_expired")
    user, record = check.user, check.record
    if request.method in UNSAFE_METHODS:
        expected = csrf_token_for(container.secret, token)
        provided = request.headers.get(CSRF_HEADER, "")
        if not provided or not constant_time_equal(provided, expected):
            raise ForbiddenError("Ongeldige of ontbrekende CSRF-token.", code="CSRF_FAILED")
    # Release the write lock taken by the session lookup. Endpoints that hand work to their own
    # transactions (uploads, backups) would otherwise wait on the request's own lock.
    session.commit()
    return AuthContext(user, record, token)


def require_owner(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    if auth.user.role != "owner":
        raise ForbiddenError("Alleen de eigenaar mag dit doen.")
    return auth


def owned_account(session: Session, user: User, account_id: int) -> TrainerAccount:
    account = session.scalars(
        select(TrainerAccount).where(TrainerAccount.id == account_id, TrainerAccount.user_id == user.id)
    ).first()
    if account is None:
        raise NotFoundError("Traineraccount niet gevonden.", context="account")
    return account


def owned_pokemon(session: Session, user: User, pokemon_id: int) -> Pokemon:
    row = session.scalars(
        select(Pokemon)
        .join(TrainerAccount, TrainerAccount.id == Pokemon.trainer_account_id)
        .where(Pokemon.id == pokemon_id, TrainerAccount.user_id == user.id)
    ).first()
    if row is None:
        raise NotFoundError("Pokémon niet gevonden.", context="pokemon")
    return row
