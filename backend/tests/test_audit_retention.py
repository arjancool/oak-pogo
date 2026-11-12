"""The audit log and ended sessions are purged after a retention period, and a failed login for an
unknown username keeps only part of that name (issue #55)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select

from app.api.v1.auth import masked
from app.jobs.tasks import ENDED_SESSION_DAYS, purge_audit_and_sessions
from app.models import AuditLog, UserSession
from tests.conftest import Api


def test_old_audit_entries_and_ended_sessions_go(owner: Api, container: Any) -> None:
    now = container.clock.now()
    old = now - timedelta(days=container.settings.audit_retention_days + 1)
    long_ago = now - timedelta(days=ENDED_SESSION_DAYS + 1)
    with container.db.transaction() as session:
        user_id = session.scalars(select(UserSession.user_id)).first()
        session.add(AuditLog(user_id=None, action="old", target=None, details=None, created_at=old))
        session.add(AuditLog(user_id=None, action="recent", target=None, details=None, created_at=now))
        for name, values in {
            "revoked": {"revoked_at": long_ago, "expires_at": now + timedelta(days=1), "last_seen_at": now},
            "expired": {"revoked_at": None, "expires_at": long_ago, "last_seen_at": long_ago},
            "idle": {
                "revoked_at": None,
                "expires_at": now + timedelta(days=1),
                "last_seen_at": long_ago - timedelta(hours=container.settings.session_idle_hours),
            },
            "recently_revoked": {"revoked_at": now, "expires_at": now + timedelta(days=1), "last_seen_at": now},
        }.items():
            session.add(UserSession(token_hash=name.ljust(64, "0"), user_id=user_id, created_at=long_ago, **values))
    purge_audit_and_sessions(container)
    with container.db.read() as session:
        actions = set(session.scalars(select(AuditLog.action)).all())
        hashes = {h.rstrip("0") for h in session.scalars(select(UserSession.token_hash)).all()}
    assert "old" not in actions and "recent" in actions
    assert "recently_revoked" in hashes, "a recent logout stays for a while"
    assert not {"revoked", "expired", "idle"} & hashes
    assert owner.get("/api/v1/auth/me").status_code == 200, "the live session of the owner stays"


def test_an_unknown_username_is_kept_only_in_part(owner: Api, container: Any) -> None:
    assert owner.login("mijn geheime wachtwoord", "iets").status_code == 401
    assert owner.login("eigenaar", "een verkeerd wachtwoord").status_code == 401
    with container.db.read() as session:
        targets = list(
            session.scalars(select(AuditLog.target).where(AuditLog.action == "login_failed").order_by(AuditLog.id))
        )
        count = session.scalar(select(func.count()).select_from(AuditLog)) or 0
    assert targets == [masked("mijn geheime wachtwoord"), "eigenaar"]
    assert targets[0] == "mi… (23)" and count >= 2


def test_masked_keeps_two_characters() -> None:
    assert masked("x") == "x… (1)"
    assert "wachtwoord" not in masked("wachtwoord123")
