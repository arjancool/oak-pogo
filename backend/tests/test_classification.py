"""Full versus partial imports (spec §4.7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.classification import AccountContext, CompletenessPolicy, ImportKind, classify
from app.normalizers.pgsharp import normalize_export

NOW = datetime(2026, 10, 23, tzinfo=UTC)


def context(**overrides: Any) -> AccountContext:
    values: dict[str, Any] = {
        "known_fingerprint": "fp",
        "known_nickname": "TestTrainer",
        "in_inventory_count": 67,
        "last_export_time": NOW - timedelta(days=10),
        "has_previous_sync": True,
    }
    values.update(overrides)
    return AccountContext(**values)


def test_valid_export_is_full(export: dict[str, Any]) -> None:
    assert classify(normalize_export(export), context(), "fp").kind is ImportKind.FULL


def test_first_import_is_full(export: dict[str, Any]) -> None:
    ctx = context(
        known_fingerprint=None,
        known_nickname=None,
        in_inventory_count=0,
        last_export_time=None,
        has_previous_sync=False,
    )
    assert classify(normalize_export(export), ctx, "fp").kind is ImportKind.FULL


def test_other_account_is_invalid(export: dict[str, Any]) -> None:
    result = classify(normalize_export(export), context(), "other")
    assert result.kind is ImportKind.INVALID and result.reasons[0].code == "ACCOUNT_MISMATCH"


def test_missing_list_is_invalid(export: dict[str, Any]) -> None:
    del export["pokemons"]
    assert classify(normalize_export(export), context(), "fp").kind is ImportKind.INVALID


def test_older_export_is_stale(export: dict[str, Any]) -> None:
    result = classify(normalize_export(export), context(last_export_time=NOW + timedelta(days=30)), "fp")
    assert result.kind is ImportKind.STALE


def test_unidentifiable_record_makes_partial(export: dict[str, Any]) -> None:
    next(p for p in export["pokemons"] if not p.get("isEgg"))["id"] = "not-a-number"
    result = classify(normalize_export(export), context(), "fp", confirm_full=True)
    assert result.kind is ImportKind.PARTIAL
    assert not result.confirmable  # unknown records can never be confirmed away


def test_suspicious_drop_is_partial_until_confirmed(export: dict[str, Any]) -> None:
    normalized = normalize_export(export)
    ctx = context(in_inventory_count=200)
    result = classify(normalized, ctx, "fp")
    assert result.kind is ImportKind.PARTIAL and result.reasons[0].code == "SUSPICIOUS_DROP" and result.confirmable
    assert classify(normalized, ctx, "fp", confirm_full=True).kind is ImportKind.FULL


def test_small_drop_is_full(export: dict[str, Any]) -> None:
    ctx = context(in_inventory_count=80)  # 13 missing: below both thresholds
    assert classify(normalize_export(export), ctx, "fp").kind is ImportKind.FULL


def test_drop_policy_is_configurable(export: dict[str, Any]) -> None:
    policy = CompletenessPolicy(max_drop_fraction=0.05, max_drop_absolute=5)
    assert (
        classify(normalize_export(export), context(in_inventory_count=80), "fp", policy=policy).kind
        is ImportKind.PARTIAL
    )


def test_empty_list_after_inventory_is_partial(export: dict[str, Any]) -> None:
    export["pokemons"] = []
    result = classify(normalize_export(export), context(), "fp")
    assert result.kind is ImportKind.PARTIAL and result.reasons[0].code == "EMPTY_POKEMON_LIST"


def test_nickname_change_without_fingerprint(export: dict[str, Any]) -> None:
    export["account"]["name"] = "AndereNaam"
    result = classify(normalize_export(export), context(known_fingerprint=None), None)
    assert result.kind is ImportKind.PARTIAL and result.reasons[0].code == "NICKNAME_CHANGED"
