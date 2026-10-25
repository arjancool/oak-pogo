"""Regressions from the external audit of 25 October 2026 (F01 to F10).

The probes were written by the auditor against synthetic data. They are adapted to the
repository's style and types, and extended where the audit asked for more cases: a catch date
that becomes unknown or known again (F01) and a hard cap on the rate limiter (F02).
"""

from __future__ import annotations

import gc
import json
import warnings
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.v1 import ingest
from app.core.migrations import backup_database
from app.core.ratelimit import SlidingWindowLimiter
from app.ingestion.receive import load_payload
from app.models import ImportJob, Pokemon, WebhookCredential
from app.repositories.settings import set_setting
from app.services.analysis import AnalysisService
from tests.conftest import Api

SYNTHETIC = "AUDIT-SYNTHETIC"


def minimal_export(caught: int | None = 2020, time: str = "2026-10-23 10:00:00 UTC") -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": "900000000000000001",
        "pokemonId": 129,
        "cp": 50,
        "individualAttack": 1,
        "individualDefense": 1,
        "individualStamina": 1,
        "favorite": False,
    }
    if caught is not None:
        record["creationTimeMs"] = int(datetime(caught, 6, 1, tzinfo=UTC).timestamp() * 1000)
    return {
        "time": time,
        "account": {"name": "SyntheticAudit", "obfuscatedPlayerId": "synthetic-audit-player"},
        "player": {},
        "items": [],
        "pokemons": [record],
    }


def _import(owner: Api, container: Any, account: int, payload: dict[str, Any]) -> None:
    response = owner.upload(account, payload)
    assert response.status_code == 202, response.text
    assert container.processor.process(response.json()["id"]) == "succeeded"


def _stored(container: Any) -> Pokemon:
    with container.db.read() as session:
        pokemon = session.scalars(select(Pokemon)).one()
        session.expunge(pokemon)
        return pokemon


# --- F01: a corrected catch date updates the catch year and the vintage protection ------------


def test_corrected_catch_date_recomputes_vintage_protection(owner: Api, container: Any) -> None:
    account = owner.account()
    _import(owner, container, account, minimal_export())
    _import(owner, container, account, minimal_export(2018, "2026-10-23 11:00:00 UTC"))
    pokemon = _stored(container)
    assert pokemon.caught_at is not None and pokemon.caught_at.year == 2018
    assert pokemon.caught_year == 2018


def test_corrected_vintage_cannot_enter_transfer_list_unconfirmed(owner: Api, container: Any) -> None:
    account = owner.account()
    _import(owner, container, account, minimal_export())
    _import(owner, container, account, minimal_export(2018, "2026-10-23 11:00:00 UTC"))
    pokemon_id = _stored(container).id
    response = owner.post("/api/v1/cleanup/action-list", {"account_id": account, "ids": [pokemon_id]})
    assert response.status_code == 200, response.text
    assert not any(item["executable"] for item in response.json()["items"])


def test_guard_reads_the_catch_date_even_when_the_stored_year_is_behind(owner: Api, container: Any) -> None:
    account = owner.account()
    _import(owner, container, account, minimal_export())
    pokemon_id = _stored(container).id
    with container.db.transaction() as session:
        pokemon = session.get(Pokemon, pokemon_id)
        assert pokemon is not None
        pokemon.caught_at = datetime(2018, 6, 1, tzinfo=UTC)  # the year column still says 2020
    response = owner.post("/api/v1/cleanup/action-list", {"account_id": account, "ids": [pokemon_id]})
    assert response.status_code == 200, response.text
    assert not any(item["executable"] for item in response.json()["items"])


@pytest.mark.parametrize(("before", "after"), [(2020, None), (None, 2018), (None, 2021)])
def test_catch_year_follows_a_date_that_appears_or_disappears(
    owner: Api, container: Any, before: int | None, after: int | None
) -> None:
    account = owner.account()
    _import(owner, container, account, minimal_export(before))
    _import(owner, container, account, minimal_export(after, "2026-10-23 11:00:00 UTC"))
    assert _stored(container).caught_year == after


# --- F02: the login throttle keeps its memory bounded -------------------------------------------


def test_login_throttle_does_not_allocate_for_blocked_ip(client: TestClient, container: Any) -> None:
    for _ in range(container.login_by_ip.limit):
        container.login_by_ip.hit("ip:testclient")
    for i in range(100):
        response = client.post("/api/v1/auth/login", json={"username": f"audit-{i}", "password": "invalid"})
        assert response.status_code == 429
    assert len(container.login_by_user) == 0


def test_expired_rate_limit_keys_are_collected() -> None:
    now = [0.0]
    limiter = SlidingWindowLimiter(1, 60, lambda: now[0])
    for i in range(10_001):
        limiter.hit(str(i))
    now[0] = 120.0
    limiter.hit("current")
    assert len(limiter) == 1


def test_rate_limiter_has_a_hard_cap_and_keeps_limiting() -> None:
    now = [0.0]
    limiter = SlidingWindowLimiter(2, 60, lambda: now[0], max_keys=100)
    for i in range(1_000):
        now[0] = i / 1000
        limiter.hit(f"key-{i}")
    assert len(limiter) <= 100
    assert limiter.hit("busy") is None and limiter.hit("busy") is None
    assert limiter.hit("busy") is not None, "the newest keys are kept and still limited"
    assert limiter.blocked("never-seen") is None and len(limiter) <= 100


# --- F03: the privacy filter covers every shape -------------------------------------------------


@pytest.mark.parametrize("shape", ["root_list", "time_object"])
def test_privacy_sanitizer_covers_all_shapes(owner: Api, container: Any, shape: str) -> None:
    account = owner.account()
    sensitive = {"latitude": f"{SYNTHETIC}-LATITUDE", "obfuscatedPlayerId": f"{SYNTHETIC}-PLAYER"}
    payload: Any = [sensitive] if shape == "root_list" else {**minimal_export(), "time": sensitive}
    response = owner.upload(account, payload)
    assert response.status_code == 202, response.text
    with container.db.read() as session:
        job = session.get(ImportJob, response.json()["id"])
        assert job is not None and job.payload_file is not None
        stored = load_payload(container.settings.imports_dir, job.payload_file)
    assert SYNTHETIC not in json.dumps(stored)


# --- F04 and F05: a webhook stops with its user and with its revocation ----------------------


def test_webhook_rechecks_revocation_after_body_read(
    owner: Api, client: TestClient, container: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    account = owner.account()
    path = owner.webhook_path(account)
    original = ingest.read_limited_body

    async def revoke_during_upload(request: Any, max_bytes: int) -> bytes:
        body = await original(request, max_bytes)
        with container.db.transaction() as session:
            credential = session.scalars(select(WebhookCredential)).one()
            credential.status = "revoked"
            credential.revoked_at = container.clock.now()
        return body

    monkeypatch.setattr(ingest, "read_limited_body", revoke_during_upload)
    response = client.post(path, json=minimal_export())
    assert response.status_code == 404, response.text
    with container.db.read() as session:
        assert session.scalars(select(ImportJob)).first() is None


def test_disabling_user_also_blocks_their_webhook(owner: Api, client: TestClient) -> None:
    member = owner.post("/api/v1/users", {"username": "auditmember", "password": "correct horse battery staple"})
    assert member.status_code == 201, member.text
    assert owner.login("auditmember", "correct horse battery staple").status_code == 200
    account = owner.account()
    path = owner.webhook_path(account)
    assert owner.login("eigenaar").status_code == 200
    assert owner.patch(f"/api/v1/users/{member.json()['id']}", {"status": "disabled"}).status_code == 200
    assert client.post(path, json=minimal_export()).status_code == 404
    # Enabling the user again brings the stored webhook back.
    assert owner.patch(f"/api/v1/users/{member.json()['id']}", {"status": "active"}).status_code == 200
    assert client.post(path, json=minimal_export()).status_code == 202


def test_negative_control_revoked_webhook_is_refused_before_read(owner: Api, client: TestClient) -> None:
    account = owner.account()
    path = owner.webhook_path(account)
    assert owner.delete(f"/api/v1/accounts/{account}/webhook").status_code == 204
    assert client.post(path, json=minimal_export()).status_code == 404


def test_negative_control_other_users_account_is_inaccessible(owner: Api) -> None:
    account = owner.account()
    member = owner.post("/api/v1/users", {"username": "othermember", "password": "correct horse battery staple"})
    assert member.status_code == 201
    assert owner.login("othermember", "correct horse battery staple").status_code == 200
    assert owner.get(f"/api/v1/accounts/{account}").status_code == 404


# --- F06: an analysis survives a writer that commits while it reads ---------------------------


def test_analysis_survives_concurrent_committed_writer(
    owner: Api, container: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    account = owner.account()
    service = AnalysisService(container.settings, container.db, container.gamedata, container.clock)
    original = service.input_fingerprint

    def concurrent_write(session: Any, account_row: Any, rules: Any) -> str:
        result = original(session, account_row, rules)
        with container.db.transaction() as writer:
            set_setting(writer, "audit.concurrent_writer", "synthetic")
        return result

    monkeypatch.setattr(service, "input_fingerprint", concurrent_write)
    assert service.run(account) is not None


# --- F10: a backup closes its connections ------------------------------------------------------


def test_database_backup_closes_connections_explicitly(owner: Api, container: Any) -> None:
    gc.collect()
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", ResourceWarning)
        assert backup_database(container.settings, "audit") is not None
        gc.collect()
    leaked = [
        str(w.message)
        for w in captured
        if issubclass(w.category, ResourceWarning) and "unclosed database" in str(w.message)
    ]
    assert not leaked
