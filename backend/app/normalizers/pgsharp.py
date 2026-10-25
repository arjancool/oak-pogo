"""PGSharp *Export Account Data* → :class:`NormalizedExport`.

The field mapping is documented in ``docs/PGSHARP_INTEGRATION.md``. Every field marked
"geverifieerd" there was observed in a real export (October 2026). The parser tolerates the
variants a different serializer could produce (enum names instead of numbers, IDs as
strings) but never guesses a value: an unreadable field becomes ``None`` plus an issue.

Pure code. No I/O, no framework imports.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from app.domain.pokemon import (
    Alignment,
    Gender,
    Issue,
    ItemCount,
    NormalizedExport,
    NormalizedPokemon,
    Severity,
    TrainerSnapshot,
)

UINT64_MODULUS = 2**64
MAX_STRING_EXTRA = 64
MS_PER_SECOND = 1000
UNSET_FORM_NAMES = frozenset({"", "Unset", "FORM_UNSET", "FormUnset"})

SpeciesResolver = Callable[[str], int | None]
MoveResolver = Callable[[str], int | None]

# Pokémon keys OAK maps explicitly. Anything else goes through the extra-field policy below.
KNOWN_POKEMON_KEYS = frozenset(
    {
        "id",
        "pokemonId",
        "pokemonDisplay",
        "cp",
        "stamina",
        "maxStamina",
        "move1",
        "move2",
        "move3",
        "individualAttack",
        "individualDefense",
        "individualStamina",
        "cpMultiplier",
        "additionalCpMultiplier",
        "numUpgrades",
        "heightM",
        "weightKg",
        "size",
        "pokeball",
        "creationTimeMs",
        "tradedTimeMs",
        "hatchedFromEgg",
        # Written by the sanitizer in place of deployedFortId: only whether it defends a gym.
        "inGym",
        "fromFort",
        "originDetail",
        "originEvents",
        "breadMoves",
        "hasMegaEvolved",
        "megaEvolvedForms",
        "nickname",
        "buddyKmWalked",
        "buddyCandyAwarded",
        "battlesAttacked",
        "battlesDefended",
        "move2IsPurifiedExclusive",
        "limitedPokemonIdentifier",
        "pokemonTagIds",
        "isLucky",
        "favorite",
        "isEgg",
        "eggType",
        "eggKmWalkedTarget",
        "eggKmWalkedStart",
        "eggIncubatorId",
        "eggSlotType",
        "eggTelemetry",
        "eggDistribution",
    }
)

# Fields that identify places, other players or devices. They are dropped on receipt and never
# stored, whatever their value (docs/PGSHARP_INTEGRATION.md, "Privacy").
SENSITIVE_POKEMON_KEYS = frozenset(
    {
        "capturedS2CellId",
        "deployedFortId",
        "deployedGymLatDegree",
        "deployedGymLngDegree",
        "deployedStationId",
        "ownerName",
        "originalOwnerNickname",
        "tradingOriginalOwnerHash",
        "pokemonContestInfo",
        "irisSocialDeployment",
        "evolutionQuestInfo",
    }
)
SENSITIVE_KEY_PATTERN = re.compile(
    r"(s2|lat|lng|lon|fort|station|gym|owner|player|account|hash|token|email|session|device|"
    r"\bip\b|cell|poi|contest|social)",
    re.IGNORECASE,
)

# Nested keys are judged word by word, because the substring pattern above is too broad below
# the top level: it would also drop "bonusIndividualAttack" ("lAt") and "megaPointDailyCounters"
# ("Poi"). A nested key is sensitive when one of its camelCase words is in this set (audit A05).
SENSITIVE_WORDS = frozenset(
    {
        "lat",
        "lng",
        "lon",
        "latitude",
        "longitude",
        "s2",
        "cell",
        "fort",
        "gym",
        "station",
        "owner",
        "player",
        "account",
        "hash",
        "token",
        "email",
        "session",
        "device",
        "ip",
        "poi",
        "contest",
        "social",
    }
)
_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")


def is_sensitive_nested_key(key: str) -> bool:
    return key in SENSITIVE_POKEMON_KEYS or any(w.lower() in SENSITIVE_WORDS for w in _WORD.findall(key))


def scrub_nested(value: Any) -> Any:
    """Drop sensitive keys at every depth below the top level of a record."""
    if isinstance(value, Mapping):
        return {k: scrub_nested(v) for k, v in value.items() if not is_sensitive_nested_key(str(k))}
    if isinstance(value, list):
        return [scrub_nested(v) for v in value]
    return value


TRAINER_STAT_KEYS = (
    "experience",
    "nextLevelExp",
    "prevLevelExp",
    "kmWalked",
    "numPokemonCaptured",
    "numPokemonEncountered",
    "numEvolutions",
    "numEggsHatched",
    "pokeStopVisits",
    "uniquePokestopsVisited",
    "numberOfPokeballThrown",
    "numRaidBattleWon",
    "numRaidBattleTotal",
    "numLegendaryBattleWon",
    "numLegendaryBattleTotal",
    "numGruntsDefeated",
    "numTrades",
    "numRemoteTrades",
    "numBestBuddies",
    "numUniquePokedexEntries",
    "numPokemonPurified",
    "numTotalMegaEvolutions",
    "numUniqueMegaEvolutions",
    "numBreadBattlesWon",
    "numBreadBattlesEntered",
    "numBreadBattlesDoughWon",
    "numMaxLevelFriends",
    "numBerriesFed",
    "numBattleAttackWon",
    "numBattleAttackTotal",
    "numBattleTrainingWon",
    "numBattleTrainingTotal",
    "numNpcCombatsWon",
    "numNpcCombatsTotal",
    "numRocketBalloonBattlesWon",
    "numRocketBalloonBattlesTotal",
    "bigMagikarpCaught",
    "smallRattataCaught",
    "numCheckIns",
    "sevenDayStreaks",
    "uniqueRaidBossesDefeated",
    "raidsWonWithFriends",
    "numPokemonFormChanges",
    "numPartyChallengesCompleted",
    "numRoutesAccepted",
    "numTotalRoutePlay",
)
LEAGUE_BADGES = {"52": "great", "53": "ultra", "54": "master"}

_TIME_PATTERN = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[ T](?P<time>\d{2}:\d{2}:\d{2})(?:\.\d+)?"
    r"\s*(?P<zone>Z|[A-Za-z]{2,5}|[+-]\d{2}:?\d{2})?$"
)
# Only unambiguous abbreviations. "CST" or "IST" mean different offsets in different
# countries; such a value yields an unknown export time plus a warning.
_ZONE_OFFSETS_HOURS = {
    "UTC": 0,
    "GMT": 0,
    "Z": 0,
    "WET": 0,
    "WEST": 1,
    "CET": 1,
    "CEST": 2,
    "BST": 1,
    "EET": 2,
    "EEST": 3,
    "MSK": 3,
    "JST": 9,
    "KST": 9,
    "AEST": 10,
    "AEDT": 11,
    "EST": -5,
    "EDT": -4,
    "PST": -8,
    "PDT": -7,
    "MST": -7,
    "MDT": -6,
}


def normalize_source_id(value: Any) -> str | None:
    """Return the decimal string form of a PGSharp 64-bit identifier, or ``None``.

    Integers and digit strings are accepted. Negative values are the signed reading of the
    same 64 bits and are folded to the unsigned value, so one Pokémon always gets one ID.
    Floats are rejected: a 64-bit ID that went through a float has already lost digits.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and re.fullmatch(r"-?\d{1,20}", value.strip()):
        number = int(value.strip())
    else:
        return None
    if number == 0 or not (-(2**63) <= number < UINT64_MODULUS):
        return None
    return str(number % UINT64_MODULUS)


def parse_export_time(value: Any) -> tuple[datetime | None, Issue | None]:
    if value is None:
        return None, Issue(Severity.WARNING, "EXPORT_TIME_MISSING", "De export bevat geen tijdstip.")
    if not isinstance(value, str):
        return None, Issue(
            Severity.WARNING,
            "EXPORT_TIME_INVALID",
            "Het exporttijdstip heeft een onbekend formaat.",
        )
    match = _TIME_PATTERN.match(value.strip())
    if not match:
        return None, Issue(
            Severity.WARNING,
            "EXPORT_TIME_INVALID",
            "Het exporttijdstip heeft een onbekend formaat.",
        )
    try:
        naive = datetime.fromisoformat(f"{match['date']}T{match['time']}")
    except ValueError:
        # Matches the pattern but is no real moment, such as month 99 (audit A06).
        return None, Issue(
            Severity.WARNING,
            "EXPORT_TIME_INVALID",
            "Het exporttijdstip is geen bestaande datum of tijd.",
        )
    zone = match["zone"]
    if zone is None:
        return None, Issue(
            Severity.WARNING,
            "EXPORT_TIME_TIMEZONE_UNKNOWN",
            "Het exporttijdstip heeft geen tijdzone en wordt daarom niet gebruikt.",
        )
    if zone[0] in "+-":
        sign = 1 if zone[0] == "+" else -1
        digits = zone[1:].replace(":", "")
        try:
            offset = timedelta(hours=int(digits[:2]), minutes=int(digits[2:] or 0))
            return naive.replace(tzinfo=timezone(sign * offset)).astimezone(UTC), None
        except ValueError:
            return None, Issue(
                Severity.WARNING,
                "EXPORT_TIME_TIMEZONE_UNKNOWN",
                f"Tijdzone '{zone}' van het exporttijdstip is geen geldige afwijking en wordt niet gebruikt.",
            )
    hours = _ZONE_OFFSETS_HOURS.get(zone.upper())
    if hours is None:
        return None, Issue(
            Severity.WARNING,
            "EXPORT_TIME_TIMEZONE_UNKNOWN",
            f"Tijdzone '{zone}' van het exporttijdstip is niet eenduidig en wordt niet gebruikt.",
        )
    return naive.replace(tzinfo=timezone(timedelta(hours=hours))).astimezone(UTC), None


def normalize_export(
    raw: Any,
    *,
    species_resolver: SpeciesResolver | None = None,
    move_resolver: MoveResolver | None = None,
) -> NormalizedExport:
    issues: list[Issue] = []
    if not isinstance(raw, Mapping):
        issues.append(Issue(Severity.ERROR, "ROOT_NOT_OBJECT", "De export is geen JSON-object."))
        return _empty_export(issues)

    export_time, time_issue = parse_export_time(raw.get("time"))
    if time_issue:
        issues.append(time_issue)

    account = raw.get("account")
    player = raw.get("player")
    # An empty section proves nothing about the account, so it counts as missing.
    has_account = isinstance(account, Mapping) and bool(account)
    has_player = isinstance(player, Mapping)
    if not has_account:
        issues.append(Issue(Severity.WARNING, "ACCOUNT_SECTION_MISSING", "Sectie 'account' ontbreekt."))
    if not has_player:
        issues.append(Issue(Severity.WARNING, "PLAYER_SECTION_MISSING", "Sectie 'player' ontbreekt."))
    trainer = _normalize_trainer(
        account if isinstance(account, Mapping) else {},
        player if isinstance(player, Mapping) else {},
    )

    items_raw = raw.get("items")
    has_items = isinstance(items_raw, list)
    items = _normalize_items(items_raw, issues) if isinstance(items_raw, list) else []
    if not has_items:
        issues.append(Issue(Severity.WARNING, "ITEMS_SECTION_MISSING", "Sectie 'items' ontbreekt."))

    records = raw.get("pokemons")
    if not isinstance(records, list):
        issues.append(
            Issue(
                Severity.ERROR,
                "POKEMON_LIST_MISSING",
                "De export bevat geen lijst 'pokemons'. Er is niets te importeren.",
            )
        )
        return NormalizedExport(
            export_time=export_time,
            export_time_raw=raw.get("time") if isinstance(raw.get("time"), str) else None,
            trainer=trainer,
            pokemon=[],
            items=items,
            eggs=0,
            has_pokemon_list=False,
            has_items_list=has_items,
            has_account=has_account,
            has_player=has_player,
            pokemon_records=0,
            unidentifiable_records=0,
            unreadable_records=[],
            issues=issues,
        )

    pokemon: list[NormalizedPokemon] = []
    seen: set[str] = set()
    eggs = 0
    unidentifiable = 0
    unreadable: list[str] = []
    for index, record in enumerate(records):
        path = f"pokemons[{index}]"
        if not isinstance(record, Mapping):
            unidentifiable += 1
            issues.append(Issue(Severity.ERROR, "RECORD_NOT_OBJECT", "Record is geen object.", path))
            continue
        if record.get("isEgg") is True:
            eggs += 1
            continue
        source_id = normalize_source_id(record.get("id"))
        if source_id is None:
            unidentifiable += 1
            code = "ID_LOSSY" if isinstance(record.get("id"), float) else "ID_INVALID"
            issues.append(
                Issue(
                    Severity.ERROR,
                    code,
                    "Pokémon-ID ontbreekt of is niet verliesvrij leesbaar.",
                    path,
                )
            )
            continue
        if source_id in seen:
            issues.append(
                Issue(
                    Severity.ERROR,
                    "ID_DUPLICATE",
                    "Dezelfde Pokémon-ID komt meerdere keren voor. Alleen het eerste record telt.",
                    path,
                    source_id,
                )
            )
            continue
        seen.add(source_id)
        normalized, record_issues = _normalize_pokemon(record, source_id, path, species_resolver, move_resolver)
        issues.extend(record_issues)
        if normalized is None:
            unreadable.append(source_id)
        else:
            pokemon.append(normalized)

    return NormalizedExport(
        export_time=export_time,
        export_time_raw=raw.get("time") if isinstance(raw.get("time"), str) else None,
        trainer=trainer,
        pokemon=pokemon,
        items=items,
        eggs=eggs,
        has_pokemon_list=True,
        has_items_list=has_items,
        has_account=has_account,
        has_player=has_player,
        pokemon_records=len(records),
        unidentifiable_records=unidentifiable,
        unreadable_records=unreadable,
        issues=issues,
    )


def player_identifier(raw: Any) -> str | None:
    """PGSharp's ``account.obfuscatedPlayerId``. Used only to compute a keyed fingerprint."""
    if not isinstance(raw, Mapping):
        return None
    account = raw.get("account")
    if not isinstance(account, Mapping):
        return None
    value = account.get("obfuscatedPlayerId")
    return value if isinstance(value, str) and value.strip() else None


# --- helpers ----------------------------------------------------------------------------------


def _empty_export(issues: list[Issue]) -> NormalizedExport:
    return NormalizedExport(
        export_time=None,
        export_time_raw=None,
        trainer=TrainerSnapshot(),
        pokemon=[],
        items=[],
        eggs=0,
        has_pokemon_list=False,
        has_items_list=False,
        has_account=False,
        has_player=False,
        pokemon_records=0,
        unidentifiable_records=0,
        unreadable_records=[],
        issues=issues,
    )


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value.strip())
    return None


def _float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def in_gym(record: Mapping[str, Any]) -> bool | None:
    """True while the Pokémon defends a gym: PGSharp then fills ``deployedFortId``. That id points
    to a place, so the sanitizer stores only this answer, as ``inGym``. Unknown when the export
    has neither field."""
    stored = record.get("inGym")
    if isinstance(stored, bool):
        return stored
    value = record.get("deployedFortId")
    if not isinstance(value, str):
        return None
    return bool(value.strip())


def _str(value: Any, limit: int = MAX_STRING_EXTRA) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()[:limit]
    return None


def _epoch_ms(value: Any) -> datetime | None:
    number = _int(value)
    if number is None or number <= 0:
        return None
    try:
        return datetime.fromtimestamp(number / MS_PER_SECOND, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _enum(value: Any, enum_type: type[Alignment] | type[Gender]) -> int | None:
    number = _int(value)
    if number is not None:
        return number
    if isinstance(value, str):
        key = value.strip().upper().removeprefix("POKEMON_").removeprefix("ALIGNMENT_")
        member = enum_type.__members__.get(key)
        return int(member) if member is not None else None
    return None


def _normalize_trainer(account: Mapping[str, Any], player: Mapping[str, Any]) -> TrainerSnapshot:
    stardust = pokecoins = None
    balances = account.get("currencyBalance")
    if isinstance(balances, list):
        for balance in balances:
            if not isinstance(balance, Mapping):
                continue
            kind = balance.get("currencyType")
            quantity = _int(balance.get("quantity"))
            if kind == "STARDUST":
                stardust = quantity
            elif kind == "POKECOIN":
                pokecoins = quantity

    stats: dict[str, Any] = {}
    for key in TRAINER_STAT_KEYS:
        value = player.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            stats[key] = round(value, 2) if isinstance(value, float) else value
    by_type = player.get("numPokemonCaughtByType")
    if isinstance(by_type, list) and all(isinstance(v, int) for v in by_type):
        stats["numPokemonCaughtByType"] = by_type
    badges = player.get("combatStats", {}).get("badges") if isinstance(player.get("combatStats"), Mapping) else None
    if isinstance(badges, Mapping):
        leagues: dict[str, dict[str, int]] = {}
        for badge, league in LEAGUE_BADGES.items():
            entry = badges.get(badge)
            if isinstance(entry, Mapping):
                total, won = _int(entry.get("numTotal")), _int(entry.get("numWon"))
                if total is not None and won is not None:
                    leagues[league] = {"battles": total, "wins": won}
        if leagues:
            stats["leagueBattles"] = leagues
    combat_log = account.get("combatLog")
    if isinstance(combat_log, Mapping):
        for name in ("currentSeasonResults", "lifetimeResults"):
            entry = combat_log.get(name)
            if isinstance(entry, Mapping):
                stats[name] = {
                    key: entry[key]
                    for key in (
                        "season",
                        "rank",
                        "rating",
                        "totalBattles",
                        "totalWins",
                        "stardustEarned",
                        "longestWinStreak",
                        "currentStreak",
                    )
                    if isinstance(entry.get(key), int | float) and not isinstance(entry.get(key), bool)
                }
    created = _epoch_ms(account.get("creationTimeMs"))
    if created:
        stats["accountCreatedAt"] = created.isoformat()

    return TrainerSnapshot(
        nickname=_str(account.get("name")),
        level=_int(player.get("level")),
        experience=_int(player.get("experience")),
        stardust=stardust,
        pokecoins=pokecoins,
        team=_int(account.get("team")),
        max_pokemon_storage=_int(account.get("maxPokemonStorage")),
        max_item_storage=_int(account.get("maxItemStorage")),
        stats=stats,
    )


def _normalize_items(records: list[Any], issues: list[Issue]) -> list[ItemCount]:
    totals: dict[int, ItemCount] = {}
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            issues.append(
                Issue(
                    Severity.WARNING,
                    "ITEM_INVALID",
                    "Itemrecord is geen object.",
                    f"items[{index}]",
                )
            )
            continue
        item_id = _int(record.get("item", record.get("itemId")))
        count = _int(record.get("count"))
        if item_id is None or count is None:
            issues.append(
                Issue(
                    Severity.WARNING,
                    "ITEM_INVALID",
                    "Item zonder geldig nummer of aantal.",
                    f"items[{index}]",
                )
            )
            continue
        name = _str(record.get("itemName"), 80)
        previous = totals.get(item_id)
        totals[item_id] = ItemCount(
            item_id,
            name or (previous.name if previous else None),
            count + (previous.count if previous else 0),
        )
    return sorted(totals.values(), key=lambda item: item.item_id)


def _resolve_move(value: Any, resolver: MoveResolver | None) -> int | None:
    number = _int(value)
    if number is not None:
        return number if number > 0 else None
    if isinstance(value, str) and resolver is not None:
        return resolver(value.strip().upper())
    return None


def _normalize_pokemon(
    record: Mapping[str, Any],
    source_id: str,
    path: str,
    species_resolver: SpeciesResolver | None,
    move_resolver: MoveResolver | None,
) -> tuple[NormalizedPokemon | None, list[Issue]]:
    issues: list[Issue] = []
    raw_species = record.get("pokemonId")
    species = _int(raw_species)
    if species is None and isinstance(raw_species, str) and species_resolver is not None:
        species = species_resolver(raw_species.strip().upper())
    if species is None or species <= 0:
        issues.append(
            Issue(
                Severity.ERROR,
                "SPECIES_INVALID",
                "Soortnummer ontbreekt of is onleesbaar. De Pokémon telt als aanwezig, maar de "
                "gegevens zijn niet bijgewerkt.",
                f"{path}.pokemonId",
                source_id,
            )
        )
        return None, issues

    display = record.get("pokemonDisplay")
    if not isinstance(display, Mapping):
        issues.append(
            Issue(
                Severity.WARNING,
                "DISPLAY_MISSING",
                "pokemonDisplay ontbreekt. Vorm, shiny en shadow zijn onbekend.",
                f"{path}.pokemonDisplay",
                source_id,
            )
        )
        display = {}

    ivs = [_int(record.get(key)) for key in ("individualAttack", "individualDefense", "individualStamina")]
    for key, value in zip(("individualAttack", "individualDefense", "individualStamina"), ivs, strict=True):
        if value is not None and not 0 <= value <= 15:
            issues.append(
                Issue(
                    Severity.ERROR,
                    "IV_OUT_OF_RANGE",
                    f"{key} valt buiten 0–15.",
                    f"{path}.{key}",
                    source_id,
                )
            )
            return None, issues

    form_name = _str(display.get("formName"), 80)
    origin = record.get("originDetail")
    origin_case = _int(origin.get("originDetailCase")) if isinstance(origin, Mapping) else None
    location = display.get("locationCard")
    location_card = _int(location.get("locationCard")) if isinstance(location, Mapping) else _int(location)
    if location_card == 0:
        location_card = None

    bread_moves: list[dict[str, int]] = []
    raw_bread = record.get("breadMoves")
    if isinstance(raw_bread, list):
        for entry in raw_bread:
            if isinstance(entry, Mapping):
                move_type, level = _int(entry.get("moveType")), _int(entry.get("moveLevel"))
                if move_type is not None and level is not None:
                    bread_moves.append({"type": move_type, "level": level})

    tag_ids = (
        [tid for tid in (normalize_source_id(t) for t in record.get("pokemonTagIds") or []) if tid is not None]
        if isinstance(record.get("pokemonTagIds"), list)
        else []
    )

    origin_events = (
        [e.strip()[:80] for e in record.get("originEvents") or [] if isinstance(e, str) and e.strip()]
        if isinstance(record.get("originEvents"), list)
        else []
    )

    mega_forms = (
        [n for n in (_int(v) for v in record.get("megaEvolvedForms") or []) if n is not None]
        if isinstance(record.get("megaEvolvedForms"), list)
        else []
    )

    move_charged_2 = _resolve_move(record.get("move3"), move_resolver)

    pokemon = NormalizedPokemon(
        source_pokemon_id=source_id,
        species_id=species,
        form_id=_int(display.get("form")),
        form_name=None if form_name in UNSET_FORM_NAMES else form_name,
        costume_id=_int(display.get("costume")),
        gender=_enum(display.get("gender"), Gender),
        shiny=_bool(display.get("shiny")),
        alignment=_enum(display.get("alignment"), Alignment),
        lucky=_bool(record.get("isLucky")),
        favorite=_bool(record.get("favorite")),
        cp=_int(record.get("cp")),
        hp=_int(record.get("stamina")),
        max_hp=_int(record.get("maxStamina")),
        iv_attack=ivs[0],
        iv_defense=ivs[1],
        iv_stamina=ivs[2],
        cp_multiplier=_float(record.get("cpMultiplier")),
        additional_cp_multiplier=_float(record.get("additionalCpMultiplier")),
        move_fast=_resolve_move(record.get("move1"), move_resolver),
        move_charged_1=_resolve_move(record.get("move2"), move_resolver),
        move_charged_2=move_charged_2,
        num_upgrades=_int(record.get("numUpgrades")),
        height_m=_float(record.get("heightM")),
        weight_kg=_float(record.get("weightKg")),
        size_class=_int(record.get("size")),
        pokeball=_int(record.get("pokeball")),
        caught_at=_epoch_ms(record.get("creationTimeMs")),
        traded_at=_epoch_ms(record.get("tradedTimeMs")),
        hatched_from_egg=_bool(record.get("hatchedFromEgg")),
        in_gym=in_gym(record),
        from_fort=_bool(record.get("fromFort")),
        origin_case=origin_case,
        origin_events=origin_events,
        location_card=location_card,
        bread_mode=_int(display.get("breadModeEnum")),
        bread_moves=bread_moves,
        has_mega_evolved=_bool(record.get("hasMegaEvolved")),
        mega_evolved_forms=mega_forms,
        temp_evolution=_int(display.get("currentTempEvolution")),
        nickname=_str(record.get("nickname")),
        buddy_km_walked=_float(record.get("buddyKmWalked")),
        buddy_candy_awarded=_int(record.get("buddyCandyAwarded")),
        battles_attacked=_int(record.get("battlesAttacked")),
        battles_defended=_int(record.get("battlesDefended")),
        purified_exclusive_move=_bool(record.get("move2IsPurifiedExclusive")),
        limited_identifier=_str(record.get("limitedPokemonIdentifier"), 80),
        tag_ids=tag_ids,
        extra=_extra_fields(record) | _display_extras(display),
    )
    if pokemon.cp is None:
        issues.append(Issue(Severity.WARNING, "CP_MISSING", "CP ontbreekt.", f"{path}.cp", source_id))
    if None in ivs:
        issues.append(Issue(Severity.WARNING, "IV_MISSING", "Eén of meer IV's ontbreken.", path, source_id))
    return pokemon, issues


_DISPLAY_EXTRA_KEYS = (
    "weatherBoostedCondition",
    "isStrongPokemon",
    "pokemonBadge",
    "originalCostume",
    "lockedTempEvolution",
    "tempEvolutionIsLocked",
    "temporaryEvolutionFinishMs",
)


def _display_extras(display: Mapping[str, Any]) -> dict[str, Any]:
    extras: dict[str, Any] = {}
    for key in _DISPLAY_EXTRA_KEYS:
        value = display.get(key)
        if value in (None, 0, False):
            continue
        if isinstance(value, bool | int) and not (isinstance(value, int) and abs(value) > 2**53):
            extras[f"display.{key}"] = value
    mega_level = display.get("megaEvolutionLevel")
    if isinstance(mega_level, Mapping) and isinstance(mega_level.get("level"), int):
        extras["display.megaEvolutionLevel"] = mega_level["level"]
    return extras


def _extra_fields(record: Mapping[str, Any]) -> dict[str, Any]:
    """Unknown, non-sensitive scalar fields, kept so later versions can interpret them."""
    extra: dict[str, Any] = {}
    for key, value in record.items():
        if key in KNOWN_POKEMON_KEYS or key in SENSITIVE_POKEMON_KEYS:
            continue
        if SENSITIVE_KEY_PATTERN.search(key):
            continue
        # Unknown fields are kept only when they carry information. A zero or false default is
        # indistinguishable from an absent field for a key OAK does not interpret yet.
        if value in (None, 0, False, "") or value == 0.0:
            continue
        if isinstance(value, bool) or (isinstance(value, float) and not math.isnan(value)):
            extra[key] = value
        elif isinstance(value, int):
            extra[key] = str(value) if abs(value) > 2**53 else value
        elif isinstance(value, str) and len(value) <= MAX_STRING_EXTRA:
            extra[key] = value
        elif isinstance(value, Mapping):
            numbers = scrub_nested(value)
            if any(numbers.values()) and all(
                isinstance(v, int) and not isinstance(v, bool) and abs(v) <= 2**53 for v in numbers.values()
            ):
                extra[key] = numbers
    return extra
