"""Regressions from the external audit of 23 October 2026 and its re-check of 24 October.

The assertions describe the required safe behaviour, one test per finding (A01 to A15) plus the
four follow-up scenarios of the re-check (A03 and A05). They were written by the auditor and only
adapted to the repository's style and types. The one deliberate change is marked in
``test_malformed_date_reaches_terminal_import_state``.
"""

from __future__ import annotations

import copy
import gzip
import json
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.deps import session_policy
from app.auth.sessions import resolve_session
from app.domain.classification import AccountContext, ImportKind, classify
from app.domain.pokemon import BreadMode
from app.ingestion.receive import IncomingPayload, decode_payload
from app.models import AuditLog, GameDataVersion, ImportJob, Pokemon, User, UserSession
from app.normalizers.pgsharp import normalize_export
from app.normalizers.sanitize import sanitize_export
from app.services.battles import max_battle_overview
from tests.conftest import Api, downloads


def load_one(owner: Api, container: Any, export: dict[str, Any], *, shiny: bool = False) -> tuple[int, int]:
    account = owner.account()
    p = copy.deepcopy(next(p for p in export["pokemons"] if not p.get("isEgg")))
    p.update(favorite=False, isLucky=False, creationTimeMs=1704067200000)
    p["pokemonDisplay"]["shiny"] = shiny
    export["pokemons"] = [p]
    response = owner.upload(account, export)
    assert response.status_code == 202
    # Process the import only: the analysis stays queued, as during a live background import.
    assert container.runner.run_once()
    with container.db.read() as session:
        pid = session.scalar(select(Pokemon.id).where(Pokemon.trainer_account_id == account))
    assert pid is not None
    return account, pid


# --- A01: uncertain imports must not replace the inventory --------------------------------------


def test_identityless_export_must_not_be_full(export: dict[str, Any]) -> None:
    original = normalize_export(export)
    export["account"] = {}
    export["pokemons"] = export["pokemons"][:-1]
    normalized = normalize_export(export)
    context = AccountContext(
        "known-account", original.trainer.nickname, len(original.pokemon), original.export_time, True
    )
    result = classify(normalized, context, None)
    assert result.kind is not ImportKind.FULL, f"Unverifiable identity accepted as {result.kind}"


def test_missing_timestamp_must_not_allow_full_replacement(export: dict[str, Any]) -> None:
    original = normalize_export(export)
    del export["time"]
    context = AccountContext(
        "known-account", original.trainer.nickname, len(original.pokemon), original.export_time, True
    )
    result = classify(normalize_export(export), context, "known-account")
    assert result.kind is not ImportKind.FULL, f"Unknown chronology accepted as {result.kind}"


# --- A02 and A03: protection on transfer lists ---------------------------------------------------


def test_shiny_protection_applies_before_analysis(
    owner: Api, container: Any, export: dict[str, Any], gamedata: Any
) -> None:
    account, pid = load_one(owner, container, export, shiny=True)
    response = owner.post("/api/v1/cleanup/action-list", {"account_id": account, "ids": [pid]})
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0 and data["needs_confirmation"], f"Shiny added without confirmation: {data['count']}"


def test_protecting_a_listed_pokemon_excludes_it_from_search(
    owner: Api, container: Any, export: dict[str, Any]
) -> None:
    account, pid = load_one(owner, container, export)
    added = owner.post("/api/v1/cleanup/action-list", {"account_id": account, "ids": [pid]})
    assert added.json()["count"] == 1
    assert owner.patch(f"/api/v1/pokemon/{pid}/metadata", {"protected": True}).status_code == 200
    data = owner.get("/api/v1/cleanup/action-list", account_id=account).json()
    assert data["search_hint"]["queries"] == [], "Manually protected Pokemon remains in transfer search"


# --- A04: upload limit before the body is spooled ------------------------------------------------


def test_upload_limit_applies_before_spooling_unauthorized_body(
    client: TestClient, container: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from starlette.datastructures import UploadFile

    container.settings.max_import_mb = 1
    original = UploadFile.write
    written = 0

    async def tracked(self: UploadFile, data: bytes) -> None:
        nonlocal written
        written += len(data)
        await original(self, data)

    monkeypatch.setattr(UploadFile, "write", tracked)
    response = client.post("/api/v1/imports/upload", files={"file": ("synthetic.bin", b"x" * (2 * 1024 * 1024))})
    assert response.status_code in (401, 403, 413)
    limit = container.settings.max_import_bytes
    assert written <= limit, f"Unauthenticated body spooled: {written} bytes, limit {limit}"


# --- A05: privacy at every depth -----------------------------------------------------------------


def test_nested_sensitive_fields_are_not_stored(export: dict[str, Any]) -> None:
    export["pokemons"][0]["newMetadata"] = {"latitude": 52.123, "playerId": "synthetic-private-id"}
    clean = json.dumps(sanitize_export(export))
    leaked = "synthetic-private-id" in clean or "52.123" in clean
    assert not leaked, "Nested playerId and latitude survive sanitization"


# --- A06 and A07: every import ends, an incomplete gzip is refused -------------------------------


def test_malformed_date_reaches_terminal_import_state(owner: Api, container: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    export["time"] = "2026-99-23 12:00:00 UTC"
    response = owner.upload(account, export)
    assert response.status_code == 202
    jid = response.json()["id"]
    container.runner.drain()
    state = owner.get(f"/api/v1/imports/{jid}").json()
    # Changed from the audit, which expected failed, rejected or partial. A first import has
    # nothing to replace, so "succeeded" with a date warning is a valid end as well. The
    # requirement is that the import never stays unfinished. test_sync covers the second import,
    # where an invalid date must lead to a partial import.
    assert state["status"] not in ("received", "queued", "processing"), f"Import stuck: {state['status']}"


def test_truncated_gzip_is_rejected(export: dict[str, Any]) -> None:
    body = gzip.compress(json.dumps(export).encode())[:-8]
    try:
        decoded = decode_payload(IncomingPayload(body=body, source="upload", content_encoding="gzip"), 64 * 1024 * 1024)
    except Exception:
        return
    accepted = decoded.data is not None
    assert not accepted, "gzip stream without checksum/trailer accepted"


# --- A08 and A09: audit log and owner setup ------------------------------------------------------


def test_failed_login_has_audit_entry(owner: Api, container: Any) -> None:
    assert owner.login("eigenaar", "wrong-password").status_code == 401
    with container.db.read() as session:
        count = session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "login_failed"))
    assert count == 1, f"Failed login audit count: {count}"


def test_registration_cannot_preempt_owner_setup(api: Api, container: Any) -> None:
    container.settings.allow_registration = True
    response = api.client.post(
        "/api/v1/auth/register", json={"username": "earlyuser", "password": "synthetic long password"}
    )
    assert response.status_code in (403, 409), f"Registration before owner creation accepted: {response.status_code}"


# --- A10: a GET never writes inside its read snapshot --------------------------------------------


def test_get_session_touch_tolerates_concurrent_writer(owner: Api, container: Any) -> None:
    token = owner.client.cookies.get("oak_session")
    assert token is not None
    now = container.clock.now()
    with container.db.transaction() as session:
        record = session.scalar(select(UserSession))
        assert record is not None
        record.last_seen_at = now - timedelta(minutes=6)
    with container.db.session(write=False) as reader:
        resolved = resolve_session(reader, token, session_policy(container), now)
        assert resolved is not None
        with container.db.transaction() as writer:
            user = writer.scalar(select(User))
            assert user is not None
            user.preferences = {"theme": "dark"}
        reader.commit()


# --- A11: a missing Game Data file is rebuilt ----------------------------------------------------


def test_gamedata_redownload_repairs_missing_active_file(container: Any, gamedata: Any) -> None:
    with container.db.read() as session:
        record = session.get(GameDataVersion, gamedata.version_id)
        assert record is not None
        missing_path = container.settings.gamedata_dir / record.file_name
    missing_path.unlink()
    assert container.gamedata.load_active() is None
    result = container.gamedata.update_from_downloads(downloads(), origin="download")
    assert container.gamedata.active() is not None, f"Not rebuilt: {result.status}, version={result.version_id}"


# --- A15: Gigantamax attack type -----------------------------------------------------------------


def test_gigantamax_attack_type_is_not_fast_move_type(
    owner: Api, container: Any, export: dict[str, Any], gamedata: Any
) -> None:
    account, pid = load_one(owner, container, export)
    assert gamedata.move("AIR_SLASH_FAST")["type"] == "flying"
    with container.db.transaction() as session:
        p = session.get(Pokemon, pid)
        assert p is not None
        p.species_id = 6
        p.species_name = "Charizard"
        p.form_key = "6:"
        p.move_fast_key = "AIR_SLASH_FAST"
        p.bread_mode = BreadMode.GIGANTAMAX
    with container.db.read() as session:
        result = max_battle_overview(session, gamedata, account, ["steel"])
    item = result["pokemon"][0]
    assert item["max_attack_type"] == "fire", f"G-Max Wildfire incorrectly typed {item['max_attack_type']}"


# --- Checked and rejected: searching for missing Pokémon works -----------------------------------


def test_missing_search_term_finds_missing_pokemon(owner: Api, container: Any, export: dict[str, Any]) -> None:
    account, pid = load_one(owner, container, export)
    with container.db.transaction() as session:
        pokemon = session.get(Pokemon, pid)
        assert pokemon is not None
        pokemon.inventory_status = "not_in_inventory"
    data = owner.get("/api/v1/pokemon", account_id=account, q="verdwenen").json()
    assert data["total"] == 1, data


# --- Re-check of 24 October: A03, a new reason needs a new confirmation -------------------------


def test_new_protecting_tag_requires_new_confirmation_for_previously_confirmed_shiny(
    owner: Api, container: Any, export: dict[str, Any]
) -> None:
    account, pid = load_one(owner, container, export, shiny=True)
    with container.db.transaction() as session:
        pokemon = session.get(Pokemon, pid)
        assert pokemon is not None
        pokemon.tag_ids = ["999"]
    tag = {"account_id": account, "tag_id": "999", "label": "Bewaren voor familie", "protects": False}
    assert owner.put("/api/v1/pokemon/tags/labels", tag).status_code == 200
    first = owner.post("/api/v1/cleanup/action-list", {"account_id": account, "ids": [pid]})
    assert first.json()["count"] == 0
    confirmed = owner.post(
        "/api/v1/cleanup/action-list", {"account_id": account, "ids": [pid], "confirmed_ids": [pid]}
    ).json()
    assert confirmed["items"][0]["executable"] is True
    tag["protects"] = True
    assert owner.put("/api/v1/pokemon/tags/labels", tag).status_code == 200
    result = owner.get("/api/v1/cleanup/action-list", account_id=account).json()
    assert result["items"][0]["executable"] is False, "New protecting tag reuses the old 'protected' confirmation"
    assert result["items"][0]["needs_confirmation"] is not None
    assert result["search_hint"]["queries"] == []


def test_second_protecting_tag_does_not_reuse_old_tag_confirmation(
    owner: Api, container: Any, export: dict[str, Any]
) -> None:
    account, pid = load_one(owner, container, export)
    with container.db.transaction() as session:
        pokemon = session.get(Pokemon, pid)
        assert pokemon is not None
        pokemon.tag_ids = ["999", "1000"]
    tag_a = {"account_id": account, "tag_id": "999", "label": "Ruilvoorraad", "protects": True}
    tag_b = {"account_id": account, "tag_id": "1000", "label": "Bewaren voor familie", "protects": False}
    assert owner.put("/api/v1/pokemon/tags/labels", tag_a).status_code == 200
    assert owner.put("/api/v1/pokemon/tags/labels", tag_b).status_code == 200
    add = owner.post("/api/v1/cleanup/action-list", {"account_id": account, "ids": [pid], "confirmed_ids": [pid]})
    assert add.json()["items"][0]["executable"]
    tag_b["protects"] = True
    assert owner.put("/api/v1/pokemon/tags/labels", tag_b).status_code == 200
    data = owner.get("/api/v1/cleanup/action-list", account_id=account).json()
    checklist = owner.get("/api/v1/cleanup/export", account_id=account, format="html").text
    sid = data["items"][0]["pokemon"]["source_pokemon_id"]
    done = owner.post("/api/v1/cleanup/action-list", {"account_id": account, "ids": [pid], "mode": "done"}).json()
    assert not data["items"][0]["executable"]
    assert data["search_hint"]["queries"] == []
    assert sid not in checklist
    assert done["items"][0]["status"] == "open", "A new protecting tag should need a fresh confirmation"


# --- Re-check of 24 October: A05, nested values in account and player sections -----------------


@pytest.mark.parametrize("section", ["account_combat_log", "player_badges"])
def test_sensitive_nested_account_and_player_values_not_persisted(
    owner: Api, container: Any, export: dict[str, Any], section: str
) -> None:
    marker = "synthetic-private-followup-id"
    if section == "account_combat_log":
        export["account"]["combatLog"]["currentSeasonResults"]["telemetry"] = {
            "playerId": marker,
            "latitude": 52.123456,
        }
    else:
        export["player"]["combatStats"]["badges"]["52"]["telemetry"] = {"playerId": marker, "latitude": 52.123456}
    response = owner.upload(owner.account(), export)
    assert response.status_code == 202
    with container.db.read() as session:
        job = session.get(ImportJob, response.json()["id"])
        assert job is not None and job.payload_file
        stored = gzip.decompress((container.settings.imports_dir / job.payload_file).read_bytes()).decode()
    leaked = marker in stored or "52.123456" in stored
    assert not leaked, f"Sensitive playerId and latitude persisted under {section}"
