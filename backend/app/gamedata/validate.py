"""Validation of a built dataset before it may become active (spec §6.2)."""

from __future__ import annotations

import itertools
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.gamedata.transform import SCHEMA_VERSION, TYPE_ORDER

REQUIRED_LEAGUES = ("great", "ultra", "master")


@dataclass(frozen=True, slots=True)
class ValidationLimits:
    """Lower bounds that any real Game Master meets with a wide margin. A dataset below them is
    truncated or the upstream format changed; either way it must not replace a working version.
    Tests use a reduced subset and lower limits."""

    min_species: int = 800
    min_forms: int = 1000
    min_moves: int = 200
    min_cpm_entries: int = 80


class DatasetInvalidError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def validate_dataset(dataset: Mapping[str, Any], limits: ValidationLimits | None = None) -> list[str]:
    """Return a list of warnings. Raises :class:`DatasetInvalidError` on blocking problems."""
    limits = limits or ValidationLimits()
    errors: list[str] = []
    warnings: list[str] = []
    if dataset.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version {dataset.get('schema_version')} wordt niet ondersteund")
        raise DatasetInvalidError(errors)

    mechanics = dataset.get("mechanics", {})
    cpm = mechanics.get("cpm", [])
    if len(cpm) < limits.min_cpm_entries:
        errors.append(f"CP-multipliertabel heeft {len(cpm)} regels, minimaal {limits.min_cpm_entries} verwacht")
    else:
        values = [row[1] for row in cpm]
        if any(b < a for a, b in itertools.pairwise(values)):
            errors.append("CP-multipliers zijn niet oplopend")
        if any(v <= 0 for v in values):
            errors.append("CP-multipliertabel bevat niet-positieve waarden")
    if not isinstance(mechanics.get("max_normal_level"), int | float):
        errors.append("maximale Pokémon-level ontbreekt")
    upgrade = mechanics.get("upgrade", {})
    if not upgrade.get("stardust") or not upgrade.get("candy"):
        errors.append("power-upkosten ontbreken")
    for key in (
        "shadow_stardust_multiplier",
        "purified_stardust_multiplier",
        "lucky_stardust_multiplier",
    ):
        if not isinstance(upgrade.get(key), int | float):
            warnings.append(f"kostenfactor {key} ontbreekt; kosten voor die variant worden onbekend")
    purification = mechanics.get("purification") or {}
    if not isinstance(purification.get("min_level"), int | float) or not isinstance(purification.get("iv_bonus"), int):
        warnings.append("regels voor purify ontbreken; het purify-scenario wordt onbekend")

    chart = dataset.get("type_chart", {})
    if set(chart) != set(TYPE_ORDER):
        errors.append("typeschema is onvolledig")

    species = dataset.get("species", {})
    forms = dataset.get("forms", {})
    moves = dataset.get("moves", {})
    if len(species) < limits.min_species:
        errors.append(f"slechts {len(species)} soorten, minimaal {limits.min_species} verwacht")
    if len(forms) < limits.min_forms:
        errors.append(f"slechts {len(forms)} vormen, minimaal {limits.min_forms} verwacht")
    if len(moves) < limits.min_moves:
        errors.append(f"slechts {len(moves)} aanvallen, minimaal {limits.min_moves} verwacht")

    bad_stats = [
        key
        for key, form in forms.items()
        if not all(isinstance(form["stats"].get(s), int) and form["stats"][s] > 0 for s in ("atk", "def", "sta"))
    ]
    if bad_stats:
        warnings.append(f"{len(bad_stats)} vormen zonder geldige basisstatistieken: {', '.join(bad_stats[:5])}")
        if len(bad_stats) > len(forms) // 10:
            errors.append("te veel vormen zonder basisstatistieken")

    unknown_moves = sorted(
        {m for form in forms.values() for m in (*form["fast_moves"], *form["charged_moves"]) if m not in moves}
    )
    if unknown_moves:
        warnings.append(f"{len(unknown_moves)} aanvallen zonder definitie: {', '.join(unknown_moves[:5])}")

    league_ids = {league.get("id") for league in dataset.get("leagues", [])}
    for league in REQUIRED_LEAGUES:
        if league not in league_ids:
            errors.append(f"league '{league}' ontbreekt")
    if not dataset.get("rankings"):
        warnings.append("PvPoke-rankings ontbreken; soortwaardering per league is niet beschikbaar")

    if errors:
        raise DatasetInvalidError(errors)
    return warnings


def summarize_dataset(dataset: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": dataset.get("schema_version"),
        "generated_at": dataset.get("generated_at"),
        "species": len(dataset.get("species", {})),
        "forms": len(dataset.get("forms", {})),
        "moves": len(dataset.get("moves", {})),
        "pvpoke_mapped_forms": sum(1 for f in dataset.get("forms", {}).values() if f.get("pvpoke_id")),
        "rankings": {k: v.get("count") for k, v in dataset.get("rankings", {}).items()},
        "max_normal_level": dataset.get("mechanics", {}).get("max_normal_level"),
        "sources": [
            {k: s.get(k) for k in ("id", "url", "sha256", "retrieved_at", "upstream_timestamp")}
            for s in dataset.get("sources", [])
        ],
    }
