"""Structural fingerprint of an export: key paths and JSON types, never values.

Used by the ingestion diagnostics to show what PGSharp actually sent, and to detect schema
changes in a new PGSharp version.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

MAX_LIST_SAMPLES = 200
MAX_PATHS = 1500
MAX_DEPTH = 6
# Every list in the summary keeps at most this many entries, with the full count beside it.
MAX_LIST_ITEMS = 200
# A key that looks like a field name. Anything else, such as a gym name used as a dictionary
# key, is data and shows as "*" (issue #46).
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")

# Pokémon record keys observed in a real PGSharp export (October 2026, 983 records).
REFERENCE_POKEMON_KEYS = frozenset(
    {
        "additionalCpMultiplier",
        "battlesAttacked",
        "battlesDefended",
        "bonusStatLevel",
        "breadMoves",
        "buddyCandyAwarded",
        "buddyKmWalked",
        "capturedS2CellId",
        "caughtInParty",
        "coinsReturned",
        "cp",
        "cpMultiplier",
        "cpMultiplierBeforeTrading",
        "creationTimeMs",
        "deployedDurationMs",
        "deployedFortId",
        "deployedGymLatDegree",
        "deployedGymLngDegree",
        "deployedReturnedTimestampMs",
        "deployedStationExpirationTimeMs",
        "deployedStationId",
        "displayCp",
        "displayPokemonId",
        "eggDistribution",
        "eggIncubatorId",
        "eggKmWalkedStart",
        "eggKmWalkedTarget",
        "eggSlotType",
        "eggTelemetry",
        "eggType",
        "evolutionQuestInfo",
        "favorite",
        "fromFort",
        "hasMegaEvolved",
        "hatchedFromEgg",
        "heightM",
        "id",
        "inEscrow",
        "individualAttack",
        "individualDefense",
        "individualStamina",
        "irisSocialDeployment",
        "isActivelyTraining",
        "isBad",
        "isComponent",
        "isEgg",
        "isFusion",
        "isLucky",
        "isStampCollectionReward",
        "limitedPokemonIdentifier",
        "markedRemoteTradable",
        "maxStamina",
        "megaEvolvedForms",
        "move1",
        "move2",
        "move2IsPurifiedExclusive",
        "move3",
        "nickname",
        "npcCombatStats",
        "numUpgrades",
        "originDetail",
        "originEvents",
        "originalOwnerNickname",
        "ownerName",
        "pokeball",
        "pokemonContestInfo",
        "pokemonDisplay",
        "pokemonId",
        "pokemonTagIds",
        "preBoostedAdditionalCpMultiplier",
        "preBoostedCp",
        "pvpCombatStats",
        "size",
        "stamina",
        "tempEvoCp",
        "tempEvoCpMultiplier",
        "tempEvoStaminaModifier",
        "tradedTimeMs",
        "tradingOriginalOwnerHash",
        "weightKg",
    }
)
REFERENCE_ROOT_KEYS = frozenset({"account", "items", "player", "pokemons", "time"})


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    return "object"


def summarize_structure(raw: Any, max_list_samples: int | None = None) -> dict[str, Any]:
    samples = max_list_samples or MAX_LIST_SAMPLES
    paths: dict[str, set[str]] = {}

    def walk(node: Any, path: str, depth: int) -> None:
        if len(paths) >= MAX_PATHS or depth > MAX_DEPTH:
            return
        paths.setdefault(path or "$", set()).add(_type_name(node))
        if isinstance(node, Mapping):
            for key, value in node.items():
                # Numeric dictionary keys (badge ids, souvenir ids) collapse into one path.
                segment = _segment(key)
                walk(value, f"{path}.{segment}" if path else segment, depth + 1)
        elif isinstance(node, list):
            for item in node[:samples]:
                walk(item, f"{path}[]", depth + 1)

    walk(raw, "", 0)
    summary: dict[str, Any] = {
        "root_type": _type_name(raw),
        "paths": {p: sorted(t) for p, t in sorted(paths.items())},
        "truncated": len(paths) >= MAX_PATHS,
    }
    if isinstance(raw, Mapping):
        summary["root_keys"] = sorted({_segment(k) for k in raw})
        pokemons = raw.get("pokemons")
        summary["counts"] = {
            "pokemons": len(pokemons) if isinstance(pokemons, list) else None,
            "items": len(raw["items"]) if isinstance(raw.get("items"), list) else None,
        }
        if isinstance(pokemons, list):
            keys: set[str] = set()
            for record in pokemons[:samples]:
                if isinstance(record, Mapping):
                    keys.update(_segment(k) for k in record)
            summary["pokemon_keys_new"] = sorted(keys - REFERENCE_POKEMON_KEYS)
            summary["pokemon_keys_missing"] = sorted(REFERENCE_POKEMON_KEYS - keys) if keys else []
        summary["root_keys_new"] = sorted(set(summary["root_keys"]) - REFERENCE_ROOT_KEYS)
    for name in ("root_keys", "root_keys_new", "pokemon_keys_new", "pokemon_keys_missing"):
        values = summary.get(name)
        if isinstance(values, list) and len(values) > MAX_LIST_ITEMS:
            summary[name] = values[:MAX_LIST_ITEMS]
            summary.setdefault("list_counts", {})[name] = len(values)
            summary["truncated"] = True
    return summary


def _segment(key: Any) -> str:
    text = str(key)
    if text.isdigit():
        return "#"
    return text if _NAME.fullmatch(text) else "*"
