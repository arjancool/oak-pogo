"""Reduce a raw PGSharp export to the fields OAK processes.

The stored copy of an import (needed to retry or resume after a restart) is the output of
:func:`sanitize_export`, never the original bytes. Location data, other players' names and
internal player identifiers are dropped here, at every depth, before anything is written to disk.

Every section works the same way: an explicit list of the keys OAK reads, and every value kept
under those keys goes through :func:`scrub_nested`, whatever its type. A section of an unexpected
type is scrubbed as a whole. So no value reaches the disk without the nested filter (audit A05).

Invariant (tested): ``normalize_export(sanitize_export(raw)) == normalize_export(raw)``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.normalizers.pgsharp import (
    KNOWN_POKEMON_KEYS,
    SENSITIVE_KEY_PATTERN,
    SENSITIVE_POKEMON_KEYS,
    TRAINER_STAT_KEYS,
    in_gym,
    scrub_nested,
)

# Raised whenever the filter drops more. Stored exports from an older revision are filtered again.
# 3: a root that is not an object, and a non-text export time (audit F03 of 25 October).
SANITIZER_REVISION = 3
ACCOUNT_KEYS = ("name", "team", "maxPokemonStorage", "maxItemStorage", "creationTimeMs")
COMBAT_LOG_KEYS = ("currentSeasonResults", "lifetimeResults")
PLAYER_EXTRA_KEYS = ("level", "numPokemonCaughtByType")
ITEM_KEYS = ("item", "itemId", "itemName", "count")
DISPLAY_DROP_KEYS = frozenset({"displayId"})
EGG_DROP_KEYS = frozenset({"eggDistribution", "eggTelemetry", "eggIncubatorId"})


def sanitize_export(raw: Any) -> Any:
    # Not an export, but it is stored until the import is rejected: filter it all the same.
    if not isinstance(raw, Mapping):
        return scrub_nested(raw)
    result: dict[str, Any] = {}
    if "time" in raw:
        # The export time is text. Anything else is unreadable for the normalizer either way, so
        # an empty object takes its place: the import gets the same warning, and nothing nested
        # reaches the disk.
        result["time"] = raw["time"] if isinstance(raw["time"], str) else {}
    account = raw.get("account")
    if isinstance(account, Mapping):
        clean = _pick(account, ACCOUNT_KEYS)
        balances = account.get("currencyBalance")
        if isinstance(balances, list):
            clean["currencyBalance"] = [
                _pick(b, ("currencyType", "quantity")) if isinstance(b, Mapping) else scrub_nested(b) for b in balances
            ]
        combat_log = account.get("combatLog")
        if isinstance(combat_log, Mapping):
            clean["combatLog"] = _pick(combat_log, COMBAT_LOG_KEYS)
        result["account"] = clean
    elif "account" in raw:
        result["account"] = scrub_nested(account)
    player = raw.get("player")
    if isinstance(player, Mapping):
        clean_player = _pick(player, (*TRAINER_STAT_KEYS, *PLAYER_EXTRA_KEYS))
        combat = player.get("combatStats")
        if isinstance(combat, Mapping) and isinstance(combat.get("badges"), Mapping):
            clean_player["combatStats"] = {"badges": scrub_nested(combat["badges"])}
        result["player"] = clean_player
    elif "player" in raw:
        result["player"] = scrub_nested(player)
    items = raw.get("items")
    if isinstance(items, list):
        result["items"] = [
            _pick(item, ITEM_KEYS) if isinstance(item, Mapping) else scrub_nested(item) for item in items
        ]
    elif "items" in raw:
        result["items"] = scrub_nested(items)
    pokemons = raw.get("pokemons")
    if isinstance(pokemons, list):
        result["pokemons"] = [_sanitize_pokemon(p) for p in pokemons]
    elif "pokemons" in raw:
        result["pokemons"] = scrub_nested(pokemons)
    return result


def _pick(section: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """The listed keys of a section, each value filtered at every depth."""
    return {k: scrub_nested(section[k]) for k in keys if k in section}


def _sanitize_pokemon(record: Any) -> Any:
    if not isinstance(record, Mapping):
        return scrub_nested(record)
    clean: dict[str, Any] = {}
    for key, value in record.items():
        if key in SENSITIVE_POKEMON_KEYS or key in EGG_DROP_KEYS:
            continue
        if key == "pokemonDisplay" and isinstance(value, Mapping):
            clean[key] = scrub_nested({k: v for k, v in value.items() if k not in DISPLAY_DROP_KEYS})
            continue
        # The generic pattern only applies to keys OAK does not map explicitly. It is broad on
        # purpose ("fromFort" and "individualAttack" match it), so known keys are exempt.
        if key not in KNOWN_POKEMON_KEYS and SENSITIVE_KEY_PATTERN.search(key):
            continue
        # Below the top level, location and identity fields go at every depth (audit A05).
        clean[key] = scrub_nested(value)
    deployed = in_gym(record)
    if deployed is not None:
        clean["inGym"] = deployed
    return clean
