"""No location or player identifier reaches the stored copy of an export, in any section (audit A05)."""

from __future__ import annotations

import gzip
import json
from typing import Any

import pytest

from app.ingestion.receive import load_payload, store_payload
from app.jobs.tasks import SANITIZER_KEY, resanitize_payloads
from app.models import ImportJob
from app.normalizers.pgsharp import normalize_export
from app.normalizers.sanitize import SANITIZER_REVISION, sanitize_export
from app.repositories.settings import get_setting
from tests.conftest import Api

MARKER = "synthetic-private-followup-id"
LATITUDE = 52.123456
SECRET = {"playerId": MARKER, "latitude": LATITUDE, "nested": [{"fortId": MARKER, "lng": 4.123456}]}


def _plant(export: dict[str, Any], section: str) -> None:
    if section == "account_combat_log":
        export["account"]["combatLog"]["currentSeasonResults"]["telemetry"] = SECRET
    elif section == "account_lifetime":
        export["account"]["combatLog"]["lifetimeResults"]["telemetry"] = SECRET
    elif section == "account_currency":
        export["account"]["currencyBalance"][0]["quantity"] = {"value": 1, **SECRET}
    elif section == "player_badges":
        export["player"]["combatStats"]["badges"]["52"]["telemetry"] = SECRET
    elif section == "player_stats":
        export["player"]["numPokemonCaughtByType"] = {"water": 3, **SECRET}
    elif section == "items":
        export["items"][0]["count"] = {"value": 2, **SECRET}
    else:
        export["pokemons"][0]["newMetadata"] = SECRET


def _leaks(text: str) -> bool:
    return MARKER in text or str(LATITUDE) in text or "4.123456" in text


@pytest.mark.parametrize(
    "section",
    ["account_combat_log", "account_lifetime", "account_currency", "player_badges", "player_stats", "items", "pokemon"],
)
def test_stored_export_has_no_nested_identity_or_location(
    owner: Api, container: Any, export: dict[str, Any], section: str
) -> None:
    _plant(export, section)
    response = owner.upload(owner.account(), export)
    assert response.status_code == 202
    with container.db.read() as session:
        job = session.get(ImportJob, response.json()["id"])
        assert job is not None and job.payload_file
        stored = gzip.decompress((container.settings.imports_dir / job.payload_file).read_bytes()).decode()
    assert not _leaks(stored), f"Sensitive values stored under {section}"


@pytest.mark.parametrize("value", ["text", 7, [SECRET], SECRET])
def test_sections_of_an_unexpected_type_are_filtered_too(export: dict[str, Any], value: Any) -> None:
    for section in ("account", "player", "items"):
        export[section] = value
        assert not _leaks(json.dumps(sanitize_export(export)))


def test_filtering_keeps_what_the_normalizer_reads(export: dict[str, Any]) -> None:
    for section in ("account_combat_log", "player_badges", "items", "pokemon"):
        _plant(export, section)
    clean = sanitize_export(export)
    assert normalize_export(clean) == normalize_export(export)
    assert sanitize_export(clean) == clean


def test_exports_stored_by_an_older_filter_are_filtered_again(
    owner: Api, container: Any, export: dict[str, Any]
) -> None:
    account = owner.account()
    imports_dir = container.settings.imports_dir
    imports_dir.mkdir(parents=True, exist_ok=True)
    _plant(export, "player_badges")
    old = store_payload(imports_dir, export)  # what an earlier filter could have left on disk
    with container.db.transaction() as session:
        session.add(
            ImportJob(
                trainer_account_id=account,
                source="upload",
                status="succeeded",
                payload_sha256="0" * 64,
                payload_size=1,
                payload_file=old,
                received_at=container.clock.now(),
            )
        )
    resanitize_payloads(container)
    assert not _leaks(json.dumps(load_payload(imports_dir, old)))
    with container.db.read() as session:
        assert get_setting(session, SANITIZER_KEY) == SANITIZER_REVISION
    # Once per revision: a later run leaves the files alone.
    before = (imports_dir / old).stat().st_mtime_ns
    resanitize_payloads(container)
    assert (imports_dir / old).stat().st_mtime_ns == before


# --- issue #48: only known fields in a Pokémon record ---------------------------------------------

AUDIT_FIELDS = {
    "s2Id": "synthetic-s2",
    "spawnPointId": "synthetic-spawn",
    "pokestopId": "synthetic-stop",
    "location": [12.345, 6.789],
    "geoPoint": {"x": 11.111, "y": 22.222},
    "tradePartnerNickname": "SyntheticPartner",
    "friendCodename": "SyntheticFriend",
    "trainerName": "SyntheticTrainer",
    "encounterId": "synthetic-encounter",
    "pokeStopGuid": "synthetic-guid",
    "ipv4Address": "192.0.2.44",
}


def _first_pokemon(export: dict[str, Any]) -> dict[str, Any]:
    return next(p for p in export["pokemons"] if not p.get("isEgg"))


def _assert_gone(clean: Any) -> None:
    text = json.dumps(clean)
    for value in AUDIT_FIELDS.values():
        for part in value if isinstance(value, list) else [value]:
            assert str(part) not in text, part
    for nested in ("11.111", "22.222"):
        assert nested not in text, nested


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_unknown_nested_fields_go_at_every_depth(export: dict[str, Any], depth: int) -> None:
    record = _first_pokemon(export)
    nested: dict[str, Any] = dict(AUDIT_FIELDS, keep=7)
    for _ in range(depth - 1):
        nested = {"inner": [nested]}
    record["originDetail"] = {"originDetailCase": 3, "originDetail": nested}
    clean = sanitize_export(export)
    _assert_gone(clean)
    assert "7" in json.dumps(clean["pokemons"]), "harmless nested values stay"
    assert normalize_export(clean) == normalize_export(export)


def test_unknown_top_level_fields_are_not_stored(export: dict[str, Any]) -> None:
    record = _first_pokemon(export)
    record.update(AUDIT_FIELDS)
    record["somethingNew"] = 5
    record["newObject"] = {"list": [1, 2]}
    clean = sanitize_export(export)
    _assert_gone(clean)
    stored = next(p for p in clean["pokemons"] if p["id"] == record["id"])
    assert stored["somethingNew"] == 5, "a plain unknown number is kept as an extra"
    assert "newObject" not in stored
    extra = next(p for p in normalize_export(export).pokemon if p.source_pokemon_id == str(record["id"])).extra
    assert not set(AUDIT_FIELDS) & set(extra), "sensitive names never reach the database either"
    assert normalize_export(clean) == normalize_export(export)


def test_a_location_card_is_a_background_not_a_place(export: dict[str, Any]) -> None:
    record = _first_pokemon(export)
    record["pokemonDisplay"]["locationCard"] = {"locationCard": 4}
    stored = next(p for p in sanitize_export(export)["pokemons"] if p["id"] == record["id"])
    assert stored["pokemonDisplay"]["locationCard"] == {"locationCard": 4}


def test_words_with_digits_and_joined_words_are_recognised() -> None:
    from app.normalizers.pgsharp import is_sensitive_nested_key

    for key in ("s2Id", "S2CellId", "pokeStopId", "spawnpoint", "friends", "ip4", "geoPoint", "trainerName"):
        assert is_sensitive_nested_key(key), key
    for key in ("move2", "bonusIndividualAttack", "megaPointDailyCounters", "formName", "locationCard", "numWon"):
        assert not is_sensitive_nested_key(key), key


def test_the_filter_revision_was_raised() -> None:
    assert SANITIZER_REVISION >= 4
