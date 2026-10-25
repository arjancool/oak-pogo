"""Server-side sessions behind an HttpOnly cookie (spec §21.1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.tokens import new_session_token, sha256_hex
from app.models import User, UserSession

SESSION_COOKIE = "oak_session"
CSRF_COOKIE = "oak_csrf"
CSRF_HEADER = "x-csrf-token"
TOUCH_INTERVAL = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class SessionPolicy:
    idle: timedelta
    absolute: timedelta


def create_session(session: Session, user: User, policy: SessionPolicy, now: datetime, user_agent: str | None) -> str:
    token = new_session_token()
    session.add(
        UserSession(
            token_hash=sha256_hex(token),
            user_id=user.id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + policy.absolute,
            user_agent=(user_agent or "")[:200] or None,
        )
    )
    user.last_login_at = now
    return token


@dataclass(frozen=True, slots=True)
class SessionCheck:
    """The outcome of looking up a session cookie. Looking up never writes: the caller stores
    ``expired`` and ``touch`` in a transaction that may write (audit A10)."""

    user: User | None = None
    record: UserSession | None = None
    expired: bool = False
    touch: bool = False

    @property
    def valid(self) -> bool:
        return self.user is not None and self.record is not None


def check_session(session: Session, token: str, policy: SessionPolicy, now: datetime) -> SessionCheck:
    record = session.scalars(select(UserSession).where(UserSession.token_hash == sha256_hex(token))).first()
    if record is None or record.revoked_at is not None:
        return SessionCheck()
    if now >= record.expires_at or now - record.last_seen_at >= policy.idle:
        return SessionCheck(record=record, expired=True)
    user = session.get(User, record.user_id)
    if user is None or user.status != "active":
        return SessionCheck()
    return SessionCheck(user=user, record=record, touch=now - record.last_seen_at >= TOUCH_INTERVAL)


def store_session_check(session: Session, check: SessionCheck, now: datetime) -> None:
    """Revoke an expired session or move ``last_seen_at``, by id, in a writing transaction."""
    if check.record is None:
        return
    if check.expired:
        session.execute(
            update(UserSession)
            .where(UserSession.id == check.record.id, UserSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
    elif check.touch:
        session.execute(update(UserSession).where(UserSession.id == check.record.id).values(last_seen_at=now))


def resolve_session(
    session: Session, token: str, policy: SessionPolicy, now: datetime
) -> tuple[User, UserSession] | None:
    """Read-only lookup: the user and session behind a valid cookie, or None."""
    check = check_session(session, token, policy, now)
    if check.user is None or check.record is None:
        return None
    return check.user, check.record


def revoke_session(session: Session, token: str, now: datetime) -> None:
    session.execute(
        update(UserSession)
        .where(UserSession.token_hash == sha256_hex(token), UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def revoke_all_for_user(session: Session, user_id: int, now: datetime, *, except_id: int | None = None) -> None:
    stmt = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_id is not None:
        stmt = stmt.where(UserSession.id != except_id)
    session.execute(stmt.values(revoked_at=now))
