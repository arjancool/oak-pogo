"""Build OAK's reference dataset from PokeMiners' Game Master and PvPoke (ADR-0017).

The output is a plain, JSON-serializable dictionary (schema ``SCHEMA_VERSION``). Analyses only
ever read that format, so a change upstream touches this module and nothing else.

Pure code: the caller downloads the sources and passes them in.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

from app.gamedata.cups import build_cups
from app.gamedata.supplement import PURIFICATION

SCHEMA_VERSION = 1
# Raised whenever the transform adds data to the same schema. An active dataset built by an older
# revision is rebuilt from its sources on the next update, even when they did not change.
# 2: Max and G-Max moves (``bread.max_moves``, ``bread.gmax_moves``).
# 3: whether a form may defend a gym (``forms[*].deployable``).
# 4: purification rules from the OAK supplement (``mechanics.purification``, ADR-0022).
# 5: PvP cups from PvPoke with the species that may enter them (``cups``, ADR-0027).
TRANSFORM_REVISION = 5

# HoloPokemonType enum order. ``typeEffective.attackScalar`` lists multipliers in this order;
# the Game Master does not name the columns itself.
TYPE_ORDER = (
    "normal",
    "fighting",
    "flying",
    "poison",
    "ground",
    "rock",
    "bug",
    "ghost",
    "steel",
    "fire",
    "water",
    "grass",
    "electric",
    "psychic",
    "ice",
    "dragon",
    "dark",
    "fairy",
)
LEAGUE_TEMPLATES = {
    "great": "COMBAT_LEAGUE_DEFAULT_GREAT",
    "ultra": "COMBAT_LEAGUE_DEFAULT_ULTRA",
    "master": "COMBAT_LEAGUE_DEFAULT_MASTER",
}
LEAGUE_NAMES = {"great": "Great League", "ultra": "Ultra League", "master": "Master League"}
RANKING_FILES = {"great": "1500", "ultra": "2500", "master": "10000"}
# Order of PvPoke's per-ranking "scores" array (see pvpoke/src/js/battle/rankers).
PVPOKE_ROLE_SCORES = ("lead", "closer", "switch", "charger", "attacker", "consistency")
CLASS_MAP = {
    "POKEMON_CLASS_LEGENDARY": "legendary",
    "POKEMON_CLASS_MYTHIC": "mythical",
    "POKEMON_CLASS_ULTRA_BEAST": "ultra_beast",
}
POKEMON_TEMPLATE = re.compile(r"^V(\d{4})_POKEMON_(.+)$")
MOVE_TEMPLATE = re.compile(r"^V(\d{4})_MOVE_(.+)$")
COMBAT_MOVE_TEMPLATE = re.compile(r"^COMBAT_V(\d{4})_MOVE_(.+)$")
MAX_MOVE_TEMPLATE = re.compile(r"^VN_BM_\d+$")
MAX_RANKING_MOVES = 6
HALF_LEVEL_STEP = 0.5


def norm_key(value: str | None) -> str:
    """Comparison key that matches PGSharp's ``SmolivNormal`` to the Game Master's ``SMOLIV_NORMAL``."""
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def form_key(dex: int, form: str | None) -> str:
    return f"{dex}:{norm_key(form)}"


def _type(value: str | None) -> str | None:
    if not value:
        return None
    return value.removeprefix("POKEMON_TYPE_").lower()


def _title(value: str) -> str:
    words = value.replace("_", " ").lower().split()
    return " ".join(w.capitalize() for w in words)


def _max_move_name(key: str, vfx: object) -> str:
    """``gmax_wildfire`` becomes ``G-Max Wildfire``. The Game Master has no display names."""
    if isinstance(vfx, str) and vfx.startswith("gmax_"):
        return f"G-Max {_title(vfx.removeprefix('gmax_'))}"
    if isinstance(vfx, str) and vfx.startswith("max_"):
        return f"Max {_title(vfx.removeprefix('max_'))}"
    return key


def _templates(entries: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    index: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        template_id = entry.get("templateId")
        data = entry.get("data")
        if isinstance(template_id, str) and isinstance(data, Mapping) and template_id not in index:
            index[template_id] = data
    return index


def _cpm_table(whole_levels: list[float]) -> list[list[float]]:
    table: list[list[float]] = []
    for index, value in enumerate(whole_levels):
        level = float(index + 1)
        table.append([level, value])
        if index + 1 < len(whole_levels):
            nxt = whole_levels[index + 1]
            table.append([level + HALF_LEVEL_STEP, math.sqrt((value**2 + nxt**2) / 2)])
    return table


def _move_list(values: Any, move_ids: Mapping[int, str]) -> list[str]:
    """Move references are names, except for moves the client enum has no name for yet; those
    appear as their numeric ID and are resolved through the move templates."""
    result: list[str] = []
    for value in values or []:
        if isinstance(value, int) and not isinstance(value, bool):
            result.append(move_ids.get(value, f"MOVE_ID_{value}"))
        elif isinstance(value, str):
            result.append(value)
    return result


def _pvpoke_move_key(move_id: str, fast_ids: set[str]) -> str:
    return f"{move_id}_FAST" if move_id in fast_ids else move_id


def build_dataset(
    game_master: Iterable[Mapping[str, Any]],
    *,
    pvpoke: Mapping[str, Any] | None,
    rankings: Mapping[str, list[Mapping[str, Any]]] | None,
    sources: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    t = _templates(game_master)

    # --- mechanics ----------------------------------------------------------------------------
    player_level = t.get("PLAYER_LEVEL_SETTINGS", {}).get("playerLevel", {})
    upgrades = t.get("POKEMON_UPGRADE_SETTINGS", {}).get("pokemonUpgrades", {})
    lucky = t.get("LUCKY_POKEMON_SETTINGS", {}).get("luckyPokemonSettings", {})
    battle = t.get("BATTLE_SETTINGS", {}).get("battleSettings", {})
    combat = t.get("COMBAT_SETTINGS", {}).get("combatSettings", {})
    cpm_whole = [float(v) for v in player_level.get("cpMultiplier", [])]
    mechanics = {
        "cpm": _cpm_table(cpm_whole),
        "max_normal_level": upgrades.get("maxNormalUpgradeLevel"),
        "best_buddy_bonus_levels": upgrades.get("defaultCpBoostAdditionalLevel"),
        "allowed_levels_above_player": upgrades.get("allowedLevelsAbovePlayer"),
        "upgrades_per_level": upgrades.get("upgradesPerLevel"),
        "upgrade": {
            "stardust": upgrades.get("stardustCost", []),
            "candy": upgrades.get("candyCost", []),
            "xl_candy": upgrades.get("xlCandyCost", []),
            "xl_min_pokemon_level": upgrades.get("xlCandyMinPokemonLevel"),
            "xl_min_player_level": upgrades.get("xlCandyMinPlayerLevel"),
            "shadow_stardust_multiplier": upgrades.get("shadowStardustMultiplier"),
            "shadow_candy_multiplier": upgrades.get("shadowCandyMultiplier"),
            "purified_stardust_multiplier": upgrades.get("purifiedStardustMultiplier"),
            "purified_candy_multiplier": upgrades.get("purifiedCandyMultiplier"),
            "lucky_stardust_multiplier": lucky.get("powerUpStardustDiscountPercent"),
        },
        "pve": {
            "stab": battle.get("sameTypeAttackBonusMultiplier"),
            "shadow_attack": battle.get("shadowPokemonAttackBonusMultiplier"),
            "shadow_defense": battle.get("shadowPokemonDefenseBonusMultiplier"),
            "max_energy": battle.get("maximumEnergy"),
            "energy_per_health_lost": battle.get("energyDeltaPerHealthLost"),
        },
        "pvp": {
            "stab": combat.get("sameTypeAttackBonusMultiplier"),
            "fast_bonus": combat.get("fastAttackBonusMultiplier"),
            "charged_bonus": combat.get("chargeAttackBonusMultiplier"),
            "shadow_attack": combat.get("shadowPokemonAttackBonusMultiplier"),
            "shadow_defense": combat.get("shadowPokemonDefenseBonusMultiplier"),
            "max_energy": combat.get("maxEnergy"),
            "turn_seconds": combat.get("turnDurationSeconds"),
        },
        # Not in the Game Master or PvPoke: OAK supplies these, with their source (ADR-0022).
        "purification": dict(PURIFICATION),
    }

    # --- types --------------------------------------------------------------------------------
    type_chart: dict[str, dict[str, float]] = {}
    for data in t.values():
        effective = data.get("typeEffective")
        if isinstance(effective, Mapping):
            attack = _type(effective.get("attackType"))
            scalars = effective.get("attackScalar", [])
            if attack and len(scalars) == len(TYPE_ORDER):
                type_chart[attack] = dict(zip(TYPE_ORDER, (float(s) for s in scalars), strict=True))

    # --- PvPoke indexes -------------------------------------------------------------------------
    pv_pokemon: list[Mapping[str, Any]] = list(pvpoke.get("pokemon", [])) if pvpoke else []
    pv_moves: dict[str, Mapping[str, Any]] = (
        {m["moveId"]: m for m in pvpoke.get("moves", []) if "moveId" in m} if pvpoke else {}
    )
    pv_fast_ids = {mid for p in pv_pokemon for mid in p.get("fastMoves", [])}

    # --- moves --------------------------------------------------------------------------------
    moves: dict[str, dict[str, Any]] = {}
    for template_id, data in t.items():
        match = MOVE_TEMPLATE.match(template_id)
        settings = data.get("moveSettings")
        if not match or not isinstance(settings, Mapping):
            continue
        key = str(settings.get("movementId", match.group(2)))
        pv_id = key.removesuffix("_FAST")
        pv = pv_moves.get(pv_id)
        moves[key] = {
            "id": int(match.group(1)),
            "key": key,
            "name": pv["name"] if pv else _title(pv_id),
            "type": _type(settings.get("pokemonType")),
            "kind": "fast" if key.endswith("_FAST") else "charged",
            "pve": {
                "power": float(settings.get("power", 0.0)),
                "duration_ms": int(settings.get("durationMs", 0)),
                "energy": int(settings.get("energyDelta", 0)),
                "damage_window_ms": int(settings.get("damageWindowStartMs", 0)),
            },
            "pvp": None,
        }
    for template_id, data in t.items():
        match = COMBAT_MOVE_TEMPLATE.match(template_id)
        combat_move = data.get("combatMove")
        if not match or not isinstance(combat_move, Mapping):
            continue
        key = str(combat_move.get("uniqueId", match.group(2)))
        if key not in moves:
            continue
        buffs = combat_move.get("buffs") if isinstance(combat_move.get("buffs"), Mapping) else None
        moves[key]["pvp"] = {
            "power": float(combat_move.get("power", 0.0)),
            "energy": int(combat_move.get("energyDelta", 0)),
            "turns": int(combat_move.get("durationTurns", 0)) + 1,
            "buffs": dict(buffs) if buffs else None,
        }
    move_ids = {m["id"]: key for key, m in moves.items()}

    # --- species and forms ----------------------------------------------------------------------
    dex_by_species: dict[str, int] = {}
    settings_by_template: list[tuple[int, Mapping[str, Any]]] = []
    for template_id, data in t.items():
        match = POKEMON_TEMPLATE.match(template_id)
        settings = data.get("pokemonSettings")
        if not match or not isinstance(settings, Mapping):
            continue
        dex = int(match.group(1))
        settings_by_template.append((dex, settings))
        dex_by_species.setdefault(str(settings.get("pokemonId")), dex)

    costume_forms: dict[str, list[str]] = {}
    for template_id, data in t.items():
        form_settings = data.get("formSettings")
        if template_id.startswith("FORMS_") and isinstance(form_settings, Mapping):
            for form in form_settings.get("forms", []) or []:
                if isinstance(form, Mapping) and form.get("isCostume"):
                    costume_forms.setdefault(str(form_settings.get("pokemon")), []).append(str(form.get("form")))

    pv_by_dex: dict[int, list[Mapping[str, Any]]] = {}
    for entry in pv_pokemon:
        pv_by_dex.setdefault(int(entry.get("dex", 0)), []).append(entry)

    species: dict[str, dict[str, Any]] = {}
    forms: dict[str, dict[str, Any]] = {}
    for dex, settings in settings_by_template:
        species_key = str(settings.get("pokemonId"))
        form = settings.get("form")
        key = form_key(dex, form if isinstance(form, str) else None)
        stats = settings.get("stats", {})
        types = [tp for tp in (_type(settings.get("type")), _type(settings.get("type2"))) if tp]
        evolutions = []
        mega = []
        for branch in settings.get("evolutionBranch", []) or []:
            if not isinstance(branch, Mapping):
                continue
            if branch.get("temporaryEvolution"):
                mega.append(
                    {
                        "id": branch["temporaryEvolution"],
                        "energy": branch.get("temporaryEvolutionEnergyCost"),
                        "energy_subsequent": branch.get("temporaryEvolutionEnergyCostSubsequent"),
                    }
                )
                continue
            target = str(branch.get("evolution"))
            target_dex = dex_by_species.get(target)
            if target_dex is None:
                continue
            quest = branch.get("questDisplay")
            evolutions.append(
                {
                    "to": form_key(target_dex, branch.get("form")),
                    "to_species": target,
                    "candy": branch.get("candyCost"),
                    "candy_purified": branch.get("candyCostPurified"),
                    "item": branch.get("evolutionItemRequirement"),
                    "item_cost": branch.get("evolutionItemRequirementCost"),
                    "lure": branch.get("lureItemRequirement"),
                    "buddy_km": branch.get("kmBuddyDistanceRequirement"),
                    "must_be_buddy": bool(branch.get("mustBeBuddy")),
                    "only_day": bool(branch.get("onlyDaytime")),
                    "only_night": bool(branch.get("onlyNighttime")),
                    "only_full_moon": bool(branch.get("onlyFullMoon")),
                    "only_dusk": bool(branch.get("onlyDuskPeriod")),
                    "only_upside_down": bool(branch.get("onlyUpsideDown")),
                    "gender": branch.get("genderRequirement"),
                    "move_requirement": branch.get("evolutionMoveRequirement"),
                    "quest": quest[0].get("questRequirementTemplateId")
                    if isinstance(quest, list) and quest and isinstance(quest[0], Mapping)
                    else None,
                    "no_candy_cost_via_trade": bool(branch.get("noCandyCostViaTrade")),
                }
            )
        for override in settings.get("tempEvoOverrides", []) or []:
            if isinstance(override, Mapping) and isinstance(override.get("stats"), Mapping):
                for entry in mega:
                    if entry["id"] == override.get("tempEvoId"):
                        entry["stats"] = {
                            "atk": override["stats"].get("baseAttack"),
                            "def": override["stats"].get("baseDefense"),
                            "sta": override["stats"].get("baseStamina"),
                        }
                        entry["types"] = [
                            tp
                            for tp in (
                                _type(override.get("typeOverride1")),
                                _type(override.get("typeOverride2")),
                            )
                            if tp
                        ]
        shadow = settings.get("shadow")
        third = settings.get("thirdMove", {})
        label = None
        if isinstance(form, str):
            suffix = form.removeprefix(f"{species_key}_")
            label = None if suffix in ("NORMAL", form) else _title(suffix)
        entry = {
            "key": key,
            "dex": dex,
            "species": species_key,
            "form": form if isinstance(form, str) else None,
            "label": label,
            "name": _title(species_key),
            "types": types,
            "stats": {
                "atk": stats.get("baseAttack"),
                "def": stats.get("baseDefense"),
                "sta": stats.get("baseStamina"),
            },
            "fast_moves": _move_list(settings.get("quickMoves"), move_ids),
            "charged_moves": _move_list(settings.get("cinematicMoves"), move_ids),
            "elite_fast": _move_list(settings.get("eliteQuickMove"), move_ids),
            "elite_charged": _move_list(settings.get("eliteCinematicMove"), move_ids),
            "legacy_moves": [],
            "evolutions": evolutions,
            "parents": [],
            "mega": mega,
            "family": settings.get("familyId"),
            "class": CLASS_MAP.get(str(settings.get("pokemonClass"))),
            # The Game Master leaves out false values, so a missing isDeployable means "not allowed".
            "deployable": settings.get("isDeployable") is True,
            "shadow": {
                "purify_stardust": shadow.get("purificationStardustNeeded"),
                "purify_candy": shadow.get("purificationCandyNeeded"),
                "shadow_move": shadow.get("shadowChargeMove"),
                "purified_move": shadow.get("purifiedChargeMove"),
            }
            if isinstance(shadow, Mapping)
            else None,
            "third_move": {
                "stardust": third.get("stardustToUnlock"),
                "candy": third.get("candyToUnlock"),
            },
            "buddy_km": settings.get("kmBuddyDistance"),
            "tradable": settings.get("isTradable"),
            "transferable": settings.get("isTransferable"),
            "bread_group": settings.get("breadTierGroup"),
            "costume_forms": [],
            "pvpoke_id": None,
        }
        forms[key] = entry
        species.setdefault(
            str(dex),
            {
                "dex": dex,
                "key": species_key,
                "name": _title(species_key),
                "family": settings.get("familyId"),
                "class": entry["class"],
                "forms": [],
            },
        )["forms"].append(key)

    # Parent links and costume forms.
    for key, entry in forms.items():
        for evo in entry["evolutions"]:
            target = forms.get(evo["to"]) or forms.get(f"{evo['to'].split(':')[0]}:")
            if target is not None and key not in target["parents"]:
                target["parents"].append(key)
        entry["costume_forms"] = costume_forms.get(entry["species"], [])

    # PvPoke mapping: same dex, same base stats and types, regular (non-shadow, non-mega) entry.
    for entry in forms.values():
        candidates = [
            p
            for p in pv_by_dex.get(entry["dex"], [])
            if not str(p.get("speciesId", "")).endswith("_shadow")
            and "mega" not in (p.get("tags") or [])
            and p.get("baseStats", {}).get("atk") == entry["stats"]["atk"]
            and p.get("baseStats", {}).get("def") == entry["stats"]["def"]
            and p.get("baseStats", {}).get("hp") == entry["stats"]["sta"]
            and [tp for tp in p.get("types", []) if tp != "none"] == entry["types"]
        ]
        if len(candidates) > 1:
            label = norm_key(entry["label"] or "")
            narrowed = [c for c in candidates if label and label[:4] in norm_key(c["speciesId"])]
            if not label:
                narrowed = [c for c in candidates if norm_key(c["speciesId"]) == norm_key(entry["species"])]
            candidates = narrowed or candidates
        if candidates:
            chosen = min(candidates, key=lambda c: len(str(c["speciesId"])))
            entry["pvpoke_id"] = chosen["speciesId"]
            entry["name"] = str(chosen.get("speciesName", entry["name"])).split(" (")[0]
            pools = (
                set(entry["fast_moves"])
                | set(entry["charged_moves"])
                | set(entry["elite_fast"])
                | set(entry["elite_charged"])
            )
            legacy = []
            for move_id in [*chosen.get("legacyMoves", []), *chosen.get("eliteMoves", [])]:
                gm_key = _pvpoke_move_key(move_id, pv_fast_ids)
                if gm_key not in pools and gm_key in moves and gm_key not in legacy:
                    legacy.append(gm_key)
            entry["legacy_moves"] = legacy
    for record in species.values():
        names = [forms[k]["name"] for k in record["forms"] if forms[k]["pvpoke_id"]]
        if names:
            record["name"] = names[0]

    # --- leagues and rankings --------------------------------------------------------------------
    leagues = []
    for league_id, template_id in LEAGUE_TEMPLATES.items():
        data = t.get(template_id, {}).get("combatLeague", {})
        max_cp = None
        for condition in data.get("pokemonCondition", []) or []:
            if isinstance(condition, Mapping) and condition.get("type") == "WITH_POKEMON_CP_LIMIT":
                max_cp = condition.get("withPokemonCpLimit", {}).get("maxCp")
        leagues.append(
            {
                "id": league_id,
                "name": LEAGUE_NAMES[league_id],
                "max_cp": max_cp,
                "banned": list(data.get("bannedPokemon", []) or []),
                "source": template_id if data else None,
            }
        )

    cups, cup_notes = build_cups(pvpoke if isinstance(pvpoke, Mapping) else None)

    ranking_out: dict[str, dict[str, Any]] = {}
    for league_id, entries in (rankings or {}).items():
        table: dict[str, Any] = {}
        for position, item in enumerate(entries, start=1):
            species_id = item.get("speciesId")
            if not isinstance(species_id, str):
                continue
            moveset = [_pvpoke_move_key(m, pv_fast_ids) for m in item.get("moveset", [])]
            usage = item.get("moves", {}) if isinstance(item.get("moves"), Mapping) else {}
            raw_scores = item.get("scores")
            role_values: list[Any] = list(raw_scores) if isinstance(raw_scores, list) else []
            table[species_id] = {
                "rank": position,
                "score": item.get("score"),
                "role_scores": dict(zip(PVPOKE_ROLE_SCORES, role_values, strict=False)),
                "moveset": moveset,
                "fast_usage": [
                    _pvpoke_move_key(m["moveId"], pv_fast_ids)
                    for m in usage.get("fastMoves", [])[:MAX_RANKING_MOVES]
                    if "moveId" in m
                ],
                "charged_usage": [
                    m["moveId"] for m in usage.get("chargedMoves", [])[:MAX_RANKING_MOVES] if "moveId" in m
                ],
            }
        ranking_out[league_id] = {"count": len(table), "entries": table}

    # --- Max Battles ------------------------------------------------------------------------------
    bread_groups: dict[str, Any] = {}
    for data in t.values():
        level_settings = data.get("breadMoveLevelSettings")
        if isinstance(level_settings, Mapping):
            bread_groups[str(level_settings.get("group"))] = {
                "attack": level_settings.get("aSettings", []),
                "guard": level_settings.get("bSettings", []),
                "spirit": level_settings.get("cSettings", []),
            }
    bread_moves = {
        _type(m.get("type")): m.get("move")
        for m in t.get("BREAD_MOVE_MAPPING_SETTINGS", {}).get("breadMoveMappings", {}).get("mappings", [])
        if isinstance(m, Mapping)
    }
    max_moves: dict[str, dict[str, Any]] = {}
    for template_id, data in t.items():
        settings = data.get("moveSettings")
        if MAX_MOVE_TEMPLATE.match(template_id) and isinstance(settings, Mapping):
            max_moves[template_id] = {
                "key": template_id,
                "name": _max_move_name(template_id, settings.get("vfxName")),
                "type": _type(settings.get("pokemonType")),
            }
    # Gigantamax Pokémon have a fixed G-Max move instead of the Max move of their fast move's type.
    # None means the Game Master has no such table, so the move is unknown rather than absent.
    gmax_moves: dict[str, list[dict[str, Any]]] | None = None
    sourdough = t.get("SOURDOUGH_MOVE_MAPPING_SETTINGS")
    if isinstance(sourdough, Mapping):
        gmax_moves = {}
        for m in sourdough.get("sourdoughMoveMappingSettings", {}).get("mappings", []) or []:
            if not isinstance(m, Mapping):
                continue
            dex = dex_by_species.get(str(m.get("pokemonId")))
            move = max_moves.get(str(m.get("move")))
            if dex is None or move is None or move["type"] is None:
                continue
            form = norm_key(m["form"]) if isinstance(m.get("form"), str) else None
            gmax_moves.setdefault(str(dex), []).append({"form": form, **move})

    # --- items ---------------------------------------------------------------------------------
    items: dict[str, dict[str, Any]] = {}
    for data in t.values():
        item = data.get("itemSettings")
        if isinstance(item, Mapping) and isinstance(item.get("itemId"), str):
            items[norm_key(str(item["itemId"]).removeprefix("ITEM_"))] = {
                "key": item["itemId"],
                "category": str(item.get("category", "")).removeprefix("ITEM_CATEGORY_").lower() or None,
                "type": str(item.get("itemType", "")).removeprefix("ITEM_TYPE_").lower() or None,
            }

    return {
        "schema_version": SCHEMA_VERSION,
        "transform_revision": TRANSFORM_REVISION,
        "generated_at": generated_at,
        "sources": sources,
        "mechanics": mechanics,
        "types": list(TYPE_ORDER),
        "type_chart": type_chart,
        "moves": moves,
        "move_ids": {str(k): v for k, v in sorted(move_ids.items())},
        "species": species,
        "forms": forms,
        "leagues": leagues,
        "cups": cups,
        "cup_notes": cup_notes,
        "rankings": ranking_out,
        "bread": {
            "groups": bread_groups,
            "max_moves_by_type": bread_moves,
            "max_moves": max_moves,
            "gmax_moves": gmax_moves,
        },
        "items": items,
    }
