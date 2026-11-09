"""League analysis of one Pokémon: IV rank for itself and every evolution, readiness and cost
(spec §12.1–12.4). Pure code on top of :class:`GameData`.

Three different things are kept apart, as §10.2 requires:

* ``rank`` / ``percent`` — how good the IVs are *within the species* for that league;
* ``species_rank`` / ``species_score`` — how competitive the *species* is (PvPoke rankings);
* ``readiness`` — whether *this individual* is usable now, after power-ups or after evolving.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.analysis.evolution import evolution_paths
from app.analysis.moves import Availability, availability
from app.analysis.powerup import Cost, power_up_cost, reachable_max_level
from app.analysis.pvp import RANK_TABLES
from app.analysis.stats import BaseStats, IVs, base_stats_of, combat_power
from app.gamedata.model import GameData

LEAGUES = ("great", "ultra", "master")
NO_CAP_THRESHOLD = 9999


@dataclass(frozen=True, slots=True)
class Subject:
    """What the analysis needs to know about one Pokémon."""

    form_key: str | None
    ivs: IVs | None
    level: float | None
    cp: int | None
    shadow: bool
    purified: bool
    lucky: bool
    trainer_level: int | None
    # The moves it knows now, fast and charged. A move it already knows needs no TM.
    moves: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MovesetAdvice:
    moveset: list[str]
    source: str  # pvpoke_ranking | pvpoke_usage_filtered | none
    elite_moves: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)
    # Elite, legacy or special moves of the PvPoke moveset the Pokémon already knows, which is
    # why the advice keeps that moveset although an Elite TM is not available.
    known_special: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class LeagueTarget:
    league: str
    target_key: str
    target_name: str
    is_evolution: bool
    evolution_candy: int | None
    evolution_item: str | None
    rank: int
    percent: float
    stat_product: float
    best_cp: int
    best_level: float
    cp_now: int | None
    readiness: str  # direct | power_up | evolution | not_suitable | unknown
    readiness_reason: dict[str, Any]  # {"code", "text"}: a sentence for the interface (ADR-0025)
    cost: Cost | None
    species_rank: int | None
    species_score: float | None
    moveset: MovesetAdvice | None


def _levels(gd: GameData, maximum: float) -> list[tuple[float, float]]:
    return [(lv, cpm) for lv in gd.levels(1.0, maximum) if (cpm := gd.cpm(lv)) is not None]


def league_cap(gd: GameData, league: str) -> int | None:
    cap = (gd.leagues.get(league) or gd.cups.get(league) or {}).get("max_cp")
    if cap is None or cap >= NO_CAP_THRESHOLD:
        return None
    return int(cap)


def recommended_moveset(
    gd: GameData,
    form: Mapping[str, Any],
    league: str,
    *,
    shadow: bool,
    elite_tm_available: bool,
    known: Collection[str] = (),
) -> MovesetAdvice | None:
    """The PvPoke moveset, or the best one a normal TM can give when part of it is out of reach.

    ``known`` holds the moves the Pokémon already knows. Such a move needs no TM, so an elite
    or legacy move it knows never pushes the advice to another moveset. Only pass it for the
    form the Pokémon has now: an evolution does not keep its moves."""
    entry = gd.ranking(league, form.get("pvpoke_id"), shadow=shadow)
    if entry is None:
        return None
    moveset = list(entry.get("moveset", []))
    elite = [m for m in moveset if availability(form, m) is Availability.ELITE_TM]
    unavailable = [m for m in moveset if availability(form, m) in (Availability.LEGACY, Availability.NOT_LEARNABLE)]
    out_of_reach = [*([] if elite_tm_available else elite), *unavailable]
    known_special = [m for m in out_of_reach if m in known]
    if any(m not in known for m in out_of_reach):
        fast = next(
            (m for m in entry.get("fast_usage", []) if availability(form, m) is Availability.NORMAL_TM),
            None,
        )
        charged = [m for m in entry.get("charged_usage", []) if availability(form, m) is Availability.NORMAL_TM][:2]
        if fast and charged:
            return MovesetAdvice([fast, *charged], "pvpoke_usage_filtered", elite, unavailable)
        return MovesetAdvice(moveset, "pvpoke_ranking", elite, unavailable)
    return MovesetAdvice(moveset, "pvpoke_ranking", elite, unavailable, known_special)


def analyze_leagues(
    gd: GameData,
    subject: Subject,
    *,
    max_level: float,
    include_best_buddy: bool,
    ready_cp_fraction: float,
    elite_tm_available: bool,
    leagues: Sequence[str] = LEAGUES,
) -> dict[str, list[LeagueTarget]]:
    """Targets per league. A cup (``gd.cups``) only takes forms its rules allow, and caps the
    level where the cup does (ADR-0027)."""
    result: dict[str, list[LeagueTarget]] = {league: [] for league in leagues}
    form = gd.forms.get(subject.form_key) if subject.form_key else None
    if form is None or subject.ivs is None:
        return result
    ceiling = min(
        max_level + (gd.best_buddy_bonus if include_best_buddy else 0.0),
        reachable_max_level(gd.mechanics, subject.trainer_level, best_buddy=include_best_buddy),
    )
    levels = _levels(gd, ceiling)
    targets: list[tuple[Mapping[str, Any], bool, int | None, str | None]] = [(form, False, 0, None)]
    for path in evolution_paths(gd.forms, form["key"]):
        target_form = gd.forms.get(path.target_key)
        if target_form is None:
            continue
        candy = (
            sum(
                (s.candy_purified if subject.purified and s.candy_purified is not None else (s.candy or 0))
                for s in path.steps
            )
            if all(s.candy is not None for s in path.steps)
            else None
        )
        item = next((s.item for s in path.steps if s.item), None)
        targets.append((target_form, True, candy, item))

    for league in leagues:
        cap = league_cap(gd, league)
        banned = set(gd.leagues.get(league, {}).get("banned", []))
        cup = gd.cups.get(league)
        level_cap = cup.get("level_cap") if cup else None
        league_levels = [lv for lv in levels if lv[0] <= level_cap] if level_cap else levels
        for target_form, is_evolution, candy, item in targets:
            if target_form["species"] in banned:
                continue
            if cup is not None and gd.cup_allows(league, target_form, shadow=subject.shadow) is not True:
                continue
            base = base_stats_of(dict(target_form))
            if base is None:
                continue
            table = RANK_TABLES.get(gd.version_id, base, cap, league_levels)
            entry = table.lookup(subject.ivs.attack, subject.ivs.defense, subject.ivs.stamina)
            if entry is None:
                continue
            cp_now = None
            current_cpm = gd.cpm(subject.level) if subject.level is not None else None
            if current_cpm is not None:
                cp_now = combat_power(base, subject.ivs, current_cpm)
            _ready, ready_cp = ready_point(gd, cap, base, subject.ivs, entry.level, entry.cp)
            readiness, reason = _readiness(
                cap, ready_cp, entry.level, cp_now, subject.level, is_evolution, ready_cp_fraction
            )
            cost = None
            if subject.level is not None and entry.level > subject.level and readiness != "not_suitable":
                cost = power_up_cost(
                    gd.mechanics,
                    subject.level,
                    entry.level,
                    shadow=subject.shadow,
                    purified=subject.purified,
                    lucky=subject.lucky,
                )
            ranking = gd.ranking(league, target_form.get("pvpoke_id"), shadow=subject.shadow)
            result[league].append(
                LeagueTarget(
                    league=league,
                    target_key=target_form["key"],
                    target_name=_display_name(target_form),
                    is_evolution=is_evolution,
                    evolution_candy=candy if is_evolution else None,
                    evolution_item=item,
                    rank=entry.rank,
                    percent=round(entry.percent_of_best, 2),
                    stat_product=round(entry.stat_product, 1),
                    best_cp=entry.cp,
                    best_level=entry.level,
                    cp_now=cp_now,
                    readiness=readiness,
                    readiness_reason=reason,
                    cost=cost,
                    species_rank=ranking.get("rank") if ranking else None,
                    species_score=ranking.get("score") if ranking else None,
                    moveset=recommended_moveset(
                        gd,
                        target_form,
                        league,
                        shadow=subject.shadow,
                        elite_tm_available=elite_tm_available,
                        known=() if is_evolution else subject.moves,
                    ),
                )
            )
    return result


def ready_level(gd: GameData, cap: int | None, best_level: float) -> float:
    """The level at which a Pokémon counts as usable in a league.

    With a CP cap that is the best level under the cap. Without one, such as the Master League,
    the best level is the highest there is, and the last levels take XL Candy. Usable then means
    the level reachable without XL Candy (``xlCandyMinPokemonLevel`` in the Game Master, 40),
    when that is lower. The best level stays the goal for the future team."""
    xl_from = gd.mechanics.get("upgrade", {}).get("xl_min_pokemon_level")
    if cap is None and isinstance(xl_from, int | float) and not isinstance(xl_from, bool):
        return min(float(xl_from), best_level)
    return best_level


def ready_point(
    gd: GameData, cap: int | None, base: BaseStats, ivs: IVs, best_level: float, best_cp: int
) -> tuple[float, int]:
    """The level from ``ready_level`` and the CP there. Without the multiplier for that level in
    the dataset it stays the best level and its CP."""
    level = ready_level(gd, cap, best_level)
    cpm = gd.cpm(level) if level < best_level else None
    return (level, combat_power(base, ivs, cpm)) if cpm is not None else (best_level, best_cp)


def _display_name(form: Mapping[str, Any]) -> str:
    label = form.get("label")
    return f"{form['name']} ({label})" if label else str(form["name"])


def _reason(code: str, text: str) -> dict[str, Any]:
    """Why a target has its readiness: a code for the interface, and the Dutch text as fallback."""
    return {"code": code, "text": text}


def _readiness(
    cap: int | None,
    ready_cp: int,
    best_level: float,
    cp_now: int | None,
    level: float | None,
    is_evolution: bool,
    ready_fraction: float,
) -> tuple[str, dict[str, Any]]:
    if cp_now is None or level is None:
        return "unknown", _reason("LEVEL_UNKNOWN", "Level onbekend")
    if cap is not None and cp_now > cap:
        if is_evolution:
            return "not_suitable", _reason("OVER_CAP_AFTER_EVOLUTION", "Na evolutie boven de CP-limiet")
        return "not_suitable", _reason("OVER_CAP", "Boven de CP-limiet")
    if level > best_level:
        return "not_suitable", _reason("ABOVE_BEST_LEVEL", "Al boven het optimale level")
    usable = cp_now >= ready_cp * ready_fraction
    if is_evolution:
        if usable:
            return "evolution", _reason("READY_AFTER_EVOLUTION", "Inzetbaar na evolutie")
        return "evolution", _reason("READY_AFTER_EVOLUTION_AND_POWER_UP", "Inzetbaar na evolutie en power-up")
    if usable:
        return "direct", _reason("READY_NOW", "Direct inzetbaar")
    return "power_up", _reason("READY_AFTER_POWER_UP", "Inzetbaar na power-up")


def best_target(targets: list[LeagueTarget]) -> LeagueTarget | None:
    usable = [t for t in targets if t.readiness not in ("not_suitable", "unknown")]
    pool = usable or []
    if not pool:
        return None
    return min(pool, key=lambda t: (t.rank, t.is_evolution, t.target_key))
