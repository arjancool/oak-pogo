"""PGSharp parsing (spec §24.1)."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest

from app.normalizers.pgsharp import (
    normalize_export,
    normalize_source_id,
    parse_export_time,
    player_identifier,
)
from app.normalizers.sanitize import sanitize_export
from app.normalizers.schema import summarize_structure

BIG_ID = 18422578575544311028  # > 2^63, as seen in real exports


def _first(export: dict[str, Any]) -> dict[str, Any]:
    return next(p for p in export["pokemons"] if not p.get("isEgg"))


def test_sample_export_parses_without_issues(export: dict[str, Any]) -> None:
    result = normalize_export(export)
    assert result.has_pokemon_list and result.has_account and result.has_player and result.has_items_list
    assert len(result.pokemon) == 67
    assert result.eggs == 3
    assert result.unidentifiable_records == 0
    assert result.issues == []
    assert result.trainer.nickname == "TestTrainer"
    assert result.trainer.stardust == 1234567
    assert result.trainer.level == 45
    assert result.trainer.stats["leagueBattles"]["great"] == {"battles": 60, "wins": 35}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (BIG_ID, str(BIG_ID)),
        (str(BIG_ID), str(BIG_ID)),
        (2**53 + 1, str(2**53 + 1)),
        (-1, str(2**64 - 1)),  # signed reading of the same 64 bits
        (1.8e19, None),  # went through a float: digits are already lost
        (0, None),
        (True, None),
        ("abc", None),
        (2**64, None),
    ],
)
def test_source_id_is_lossless(value: object, expected: str | None) -> None:
    assert normalize_source_id(value) == expected


def test_big_ids_survive_json_roundtrip(export: dict[str, Any]) -> None:
    _first(export)["id"] = BIG_ID
    text = json.dumps(export)
    result = normalize_export(json.loads(text))
    assert str(BIG_ID) in {p.source_pokemon_id for p in result.pokemon}


def test_flags_and_unknown_vs_false(export: dict[str, Any]) -> None:
    record = _first(export)
    record["pokemonDisplay"].update(
        {"shiny": True, "alignment": 1, "locationCard": {"locationCard": 224}, "breadModeEnum": 1}
    )
    record["isLucky"] = True
    record["favorite"] = False
    del record["individualAttack"]
    pokemon = next(p for p in normalize_export(export).pokemon if p.source_pokemon_id == str(record["id"]))
    assert pokemon.shiny is True
    assert pokemon.alignment == 1
    assert pokemon.location_card == 224
    assert pokemon.bread_mode == 1
    assert pokemon.lucky is True
    assert pokemon.favorite is False  # explicit false
    assert pokemon.iv_attack is None  # missing stays unknown
    assert pokemon.iv_percent is None


def test_enum_names_are_accepted(export: dict[str, Any]) -> None:
    record = _first(export)
    record["pokemonDisplay"]["alignment"] = "SHADOW"
    record["pokemonDisplay"]["gender"] = "FEMALE"
    record["pokemonId"] = "GYARADOS"
    result = normalize_export(export, species_resolver=lambda name: 130 if name == "GYARADOS" else None)
    pokemon = next(p for p in result.pokemon if p.source_pokemon_id == str(record["id"]))
    assert (pokemon.species_id, pokemon.alignment, pokemon.gender) == (130, 1, 2)


def test_unknown_fields_are_kept_but_sensitive_ones_are_not(export: dict[str, Any]) -> None:
    record = _first(export)
    record["brandNewField"] = 42
    record["ownerLatitude"] = 52.1
    pokemon = next(p for p in normalize_export(export).pokemon if p.source_pokemon_id == str(record["id"]))
    assert pokemon.extra["brandNewField"] == 42
    assert "ownerLatitude" not in pokemon.extra
    assert "capturedS2CellId" not in pokemon.extra


def test_missing_optional_fields(export: dict[str, Any]) -> None:
    record = _first(export)
    for key in (
        "heightM",
        "weightKg",
        "originDetail",
        "breadMoves",
        "pokemonTagIds",
        "nickname",
        "tradedTimeMs",
    ):
        record.pop(key)
    result = normalize_export(export)
    pokemon = next(p for p in result.pokemon if p.source_pokemon_id == str(record["id"]))
    assert pokemon.height_m is None and pokemon.tag_ids == [] and pokemon.traded_at is None


def test_invalid_records_are_reported(export: dict[str, Any]) -> None:
    pokemons = [p for p in export["pokemons"] if not p.get("isEgg")]
    pokemons[0]["id"] = None
    pokemons[1]["individualDefense"] = 99
    pokemons[2]["id"] = pokemons[3]["id"]
    result = normalize_export(export)
    codes = {i.code for i in result.issues}
    assert {"ID_INVALID", "IV_OUT_OF_RANGE", "ID_DUPLICATE"} <= codes
    assert result.unidentifiable_records == 1
    assert str(pokemons[1]["id"]) in result.unreadable_records


def test_empty_and_missing_lists(export: dict[str, Any]) -> None:
    export["pokemons"] = []
    empty = normalize_export(export)
    assert empty.has_pokemon_list and empty.pokemon == []
    del export["pokemons"]
    missing = normalize_export(export)
    assert not missing.has_pokemon_list
    assert any(i.code == "POKEMON_LIST_MISSING" for i in missing.issues)
    assert normalize_export([1, 2]).issues[0].code == "ROOT_NOT_OBJECT"


def test_display_missing_on_non_egg(export: dict[str, Any]) -> None:
    _first(export)["pokemonDisplay"] = None
    result = normalize_export(export)
    assert any(i.code == "DISPLAY_MISSING" for i in result.issues)


@pytest.mark.parametrize(
    ("raw", "iso"),
    [
        ("2026-10-23 15:13:20 CEST", "2026-10-23T13:13:20+00:00"),
        ("2026-01-05 08:00:00 CET", "2026-01-05T07:00:00+00:00"),
        ("2026-10-23T15:13:20+02:00", "2026-10-23T13:13:20+00:00"),
        ("2026-10-23 15:13:20 UTC", "2026-10-23T15:13:20+00:00"),
    ],
)
def test_export_time(raw: str, iso: str) -> None:
    value, issue = parse_export_time(raw)
    assert issue is None and value is not None and value.isoformat() == iso


@pytest.mark.parametrize("raw", ["2026-10-23 15:13:20 IST", "2026-10-23 15:13:20", "gisteren", None, 12])
def test_export_time_without_reliable_zone(raw: object) -> None:
    value, issue = parse_export_time(raw)
    assert value is None and issue is not None


def test_sanitize_removes_sensitive_data_and_keeps_meaning(export: dict[str, Any]) -> None:
    sanitized = sanitize_export(export)
    text = json.dumps(sanitized)
    for secret in (
        "capturedS2CellId",
        "obfuscatedPlayerId",
        "helpshiftUserId",
        "playerSupportId",
        "quagoPlayerId",
        "attractivePoiId",
        "originalOwnerNickname",
        "tradingOriginalOwnerHash",
        "deployedGymLatDegree",
        "displayId",
        "timeZoneOffsetMs",
        "Ruilvriend",
    ):
        assert secret not in text, secret
    assert dataclasses.asdict(normalize_export(sanitized)) == dataclasses.asdict(normalize_export(export))


def test_player_identifier_and_schema_summary(export: dict[str, Any]) -> None:
    assert player_identifier(export) == "synthetic-obfuscated-player-0001"
    export["pokemons"][0]["somethingNew"] = 1
    summary = summarize_structure(export)
    assert "somethingNew" in summary["pokemon_keys_new"]
    assert summary["counts"]["pokemons"] == 70
    assert "Ruilvriend" not in json.dumps(summary)  # structure only, never values


def test_large_export_performance(export: dict[str, Any]) -> None:
    template = _first(export)
    export["pokemons"] = [dict(template, id=2**63 + i) for i in range(6000)]
    result = normalize_export(export)
    assert len(result.pokemon) == 6000


def test_sensitive_fields_are_dropped_at_every_depth(export: dict[str, Any]) -> None:
    record = next(p for p in export["pokemons"] if not p.get("isEgg"))
    record["newMetadata"] = {
        "latitude": 52.123,
        "playerId": "synthetic-private-id",
        "nested": [{"fortId": "synthetic-fort", "keep": 1}],
        "bonusIndividualAttack": 2,
    }
    record["pokemonDisplay"]["locationInfo"] = {"lng": 4.567, "s2CellId": "synthetic-cell"}
    record["counts"] = {"lat": 52, "lng": 4, "wins": 3}
    clean = sanitize_export(export)
    text = json.dumps(clean)
    for secret in ("52.123", "synthetic-private-id", "synthetic-fort", "4.567", "synthetic-cell"):
        assert secret not in text, secret
    stored = next(p for p in clean["pokemons"] if p["id"] == record["id"])
    assert stored["newMetadata"] == {"nested": [{"keep": 1}], "bonusIndividualAttack": 2}
    assert normalize_export(clean) == normalize_export(export)
    pokemon = next(p for p in normalize_export(export).pokemon if p.source_pokemon_id == str(record["id"]))
    assert pokemon.extra["counts"] == {"wins": 3}
