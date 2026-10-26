"""Battle analyses on top of the stored projection and the active Game Data (spec §12–§14).

Every result states its method. Team proposals and Rocket/Max advice are heuristics on
rankings, typing and stats; none of them is a battle simulation, and the API says so.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.moves import Availability, availability
from app.analysis.pve import boss_defense, moveset_dps
from app.analysis.stats import IVs, base_stats_of
from app.domain.pokemon import Alignment, BreadMode
from app.gamedata.model import GameData
from app.models import Pokemon, PvpRanking
from app.recommendations.rules import CleanupRules

TEAM_POOL = 24
TEAM_SIZE = 3
READINESS_BY_MODE = {
    "direct": ("direct",),
    "limited": ("direct", "power_up", "evolution"),
    "future": ("direct", "power_up", "evolution"),
}
SUPER_EFFECTIVE = 1.0
MAX_COUNTERS = 25
MAX_MOVE_TYPES = {1: "attack", 2: "guard", 3: "spirit"}


def _text(code: str, text: str, **data: Any) -> dict[str, Any]:
    """A sentence for the interface: a code with its data, and the Dutch text as fallback (ADR-0025)."""
    return {"code": code, "text": text, **({"data": data} if data else {})}


TEAM_METHOD = _text(
    "TEAM_METHOD",
    "Heuristiek: PvPoke-soortscore × IV-kwaliteit, met een straf voor gedeelde zwaktes en een bonus voor "
    "typedekking. Geen gevechtssimulatie.",
)
TEAM_VARIANTS = (
    ("direct", _text("TEAM_DIRECT", "Beste direct inzetbare team")),
    ("limited", _text("TEAM_LIMITED", "Beste team met beperkte upgrades")),
    ("future", _text("TEAM_FUTURE", "Beste toekomstige team")),
)
MAX_NOTES = [
    _text(
        "MAX_ATTACK_TYPE",
        "Bij Dynamax heeft Max Attack het type van de snelle aanval. Gigantamax gebruikt in plaats daarvan "
        "een vaste G-Max-aanval. Type en naam daarvan komen uit de actieve Game Data.",
    ),
    _text(
        "MAX_MOVE_TYPES",
        "Aanvalstype 1 in de export is Max Attack (bevestigd in een echte export). Type 2 (Max Guard) en "
        "3 (Max Spirit) volgen de community-protocoldefinities en zijn niet geverifieerd.",
    ),
    _text(
        "MAX_RESOURCES",
        "Max Particles en candy komen niet in de export voor; beschikbaarheid is daarom onbekend.",
    ),
]


@dataclass(slots=True)
class Candidate:
    pokemon: Pokemon
    ranking: PvpRanking
    form: Mapping[str, Any]
    score: float
    role_scores: Mapping[str, float]
    moveset_quality: str
    recommended: list[str]


def _shadow(p: Pokemon) -> bool:
    return p.alignment == Alignment.SHADOW


def weaknesses(gd: GameData, types: list[str]) -> set[str]:
    return {attack for attack in gd.type_chart if gd.effectiveness(attack, types) > SUPER_EFFECTIVE}


def moveset_quality(current: list[str | None], recommended: list[str]) -> str:
    if not recommended:
        return "unknown"
    fast, charged = current[0], {m for m in current[1:] if m}
    rec_fast, rec_charged = recommended[0], set(recommended[1:])
    if fast == rec_fast and rec_charged <= charged:
        return "optimal"
    if fast == rec_fast or charged & rec_charged:
        return "partial"
    return "poor"


def league_candidates(
    session: Session,
    gd: GameData,
    account_id: int,
    league: str,
    *,
    readiness: tuple[str, ...] | None = None,
    max_stardust: int | None = None,
) -> list[Candidate]:
    rows = session.execute(
        select(Pokemon, PvpRanking)
        .join(PvpRanking, PvpRanking.pokemon_id == Pokemon.id)
        .where(
            Pokemon.trainer_account_id == account_id,
            Pokemon.inventory_status == "in_inventory",
            PvpRanking.league == league,
        )
    ).all()
    # A cup PvPoke has no ranking for still lists its Pokémon, ordered by IV quality only.
    ranked = league in gd.rankings
    best: dict[int, tuple[Pokemon, PvpRanking]] = {}
    for pokemon, ranking in rows:
        if (ranked and ranking.species_rank is None) or ranking.readiness in ("not_suitable", "unknown"):
            continue
        if readiness and ranking.readiness not in readiness:
            continue
        if max_stardust is not None and (ranking.stardust_cost or 0) > max_stardust:
            continue
        current = best.get(pokemon.id)
        if current is None or (ranking.species_rank or 0, ranking.rank) < (
            current[1].species_rank or 0,
            current[1].rank,
        ):
            best[pokemon.id] = (pokemon, ranking)
    candidates = []
    for pokemon, ranking in best.values():
        form = gd.forms.get(ranking.target_form_key)
        if form is None:
            continue
        entry = gd.ranking(league, form.get("pvpoke_id"), shadow=_shadow(pokemon)) or {}
        species_score = float(entry.get("score") or 0) if ranked else 100.0
        recommended = list(entry.get("moveset", []))
        current = [pokemon.move_fast_key, pokemon.move_charged_1_key, pokemon.move_charged_2_key]
        quality = moveset_quality(current, recommended) if not ranking.is_evolution else "after_evolution"
        candidates.append(
            Candidate(
                pokemon=pokemon,
                ranking=ranking,
                form=form,
                score=species_score * ranking.percent_of_best / 100,
                role_scores=entry.get("role_scores") or {},
                moveset_quality=quality,
                recommended=recommended,
            )
        )
    candidates.sort(key=lambda c: -c.score)
    return candidates


READINESS_ORDER = {"direct": 0, "power_up": 1, "evolution": 2}
MOVESET_ORDER = {"optimal": 0, "partial": 1, "after_evolution": 2, "poor": 3}
LEAGUE_SORTS: dict[str, Callable[[Candidate], Any]] = {
    "suitability": lambda c: c.score,
    "name": lambda c: (c.pokemon.species_name or "").lower() or None,
    "target": lambda c: c.ranking.target_name.lower(),
    "species_rank": lambda c: c.ranking.species_rank,
    "iv_rank": lambda c: c.ranking.rank,
    "percent": lambda c: c.ranking.percent_of_best,
    "cp": lambda c: c.pokemon.cp,
    "best_cp": lambda c: c.ranking.best_cp,
    "readiness": lambda c: READINESS_ORDER.get(c.ranking.readiness),
    "stardust": lambda c: c.ranking.stardust_cost,
    "moveset": lambda c: MOVESET_ORDER.get(c.moveset_quality),
}


def sort_candidates(candidates: list[Candidate], sort: str) -> list[Candidate]:
    """Sort on one column, '-' for descending. Unknown values always come last, and equal
    values keep the suitability order. Raises KeyError for an unknown column."""
    descending = sort.startswith("-")
    key = LEAGUE_SORTS[sort.removeprefix("-")]
    known = [c for c in candidates if key(c) is not None]
    unknown = [c for c in candidates if key(c) is None]
    return sorted(known, key=key, reverse=descending) + unknown


def _team_value(gd: GameData, team: tuple[Candidate, ...]) -> tuple[float, dict[str, Any]]:
    weak = [weaknesses(gd, list(c.form.get("types", []))) for c in team]
    shared = {t for t in gd.type_chart if sum(t in w for w in weak) >= 2}
    coverage = set()
    for c in team:
        for key in (
            c.pokemon.move_fast_key,
            c.pokemon.move_charged_1_key,
            c.pokemon.move_charged_2_key,
        ):
            move = gd.move(key)
            if move and move.get("type"):
                coverage.add(move["type"])
    value = sum(c.score for c in team) * (1 - 0.06 * len(shared)) + 0.5 * len(coverage)
    return value, {"shared_weaknesses": sorted(shared), "move_type_coverage": sorted(coverage)}


def _assign_roles(team: tuple[Candidate, ...]) -> list[tuple[str, Candidate]]:
    """Pick the order that maximises PvPoke's lead, switch and closer scores."""
    roles = ["lead", "switch", "closer"]
    best: list[tuple[str, Candidate]] = []
    best_value = -1.0
    for perm in itertools.permutations(team):
        pairs = [(role, candidate) for role, candidate in zip(roles, perm, strict=True)]
        value = sum(float(c.role_scores.get(role, 0) or 0) for role, c in pairs)
        if value > best_value:
            best_value, best = value, pairs
    return best


def build_teams(
    session: Session,
    gd: GameData,
    account_id: int,
    league: str,
    *,
    budget: int | None,
    include: list[int] | None = None,
) -> list[dict[str, Any]]:
    variants = []
    for mode, label in TEAM_VARIANTS:
        pool = league_candidates(
            session,
            gd,
            account_id,
            league,
            readiness=READINESS_BY_MODE[mode],
            max_stardust=budget if mode == "limited" else None,
        )
        # One copy per target species keeps the team varied.
        seen: set[str] = set()
        unique: list[Candidate] = []
        for candidate in pool:
            if candidate.ranking.target_form_key in seen:
                continue
            seen.add(candidate.ranking.target_form_key)
            unique.append(candidate)
        pool = unique[:TEAM_POOL]
        forced = [c for c in pool if include and c.pokemon.id in include]
        if len(pool) < TEAM_SIZE:
            variants.append(
                {
                    "mode": mode,
                    "label": label,
                    "team": None,
                    "message": _text("TEAM_TOO_FEW", "Te weinig geschikte Pokémon voor deze variant."),
                }
            )
            continue
        best_value, best_team, best_info = -1.0, None, {}
        for team in itertools.combinations(pool, TEAM_SIZE):
            if forced and not all(f in team for f in forced):
                continue
            value, info = _team_value(gd, team)
            if value > best_value:
                best_value, best_team, best_info = value, team, info
        if best_team is None:
            variants.append(
                {"mode": mode, "label": label, "team": None, "message": _text("TEAM_NONE", "Geen team gevonden.")}
            )
            continue
        members = []
        total_dust = 0
        for role, candidate in _assign_roles(best_team):
            r = candidate.ranking
            total_dust += r.stardust_cost or 0
            members.append(
                {
                    "role": role,
                    "pokemon_id": candidate.pokemon.id,
                    "name": candidate.pokemon.species_name,
                    "target": r.target_name,
                    "is_evolution": r.is_evolution,
                    "cp": candidate.pokemon.cp,
                    "best_cp": r.best_cp,
                    "iv_rank": r.rank,
                    "species_rank": r.species_rank,
                    "readiness": r.readiness,
                    "stardust": r.stardust_cost,
                    "candy": r.candy_cost,
                    "xl_candy": r.xl_candy_cost,
                    "moveset_quality": candidate.moveset_quality,
                    "recommended_moveset": [str((gd.move(m) or {}).get("name", m)) for m in candidate.recommended],
                    "types": list(candidate.form.get("types", [])),
                }
            )
        variants.append(
            {
                "mode": mode,
                "label": label,
                "team": members,
                "score": round(best_value, 1),
                "investment": {"stardust": total_dust},
                **best_info,
            }
        )
    return variants


def _attack_stat(gd: GameData, pokemon: Pokemon, form: Mapping[str, Any]) -> float | None:
    base = base_stats_of(dict(form))
    cpm = gd.cpm(pokemon.level) if pokemon.level is not None else None
    if base is None or cpm is None or pokemon.iv_attack is None:
        return None
    bonus = float(gd.mechanics.get("pve", {}).get("shadow_attack") or 1.0) if _shadow(pokemon) else 1.0
    return (base.attack + pokemon.iv_attack) * cpm * bonus


def raid_counters(
    session: Session,
    gd: GameData,
    account_id: int,
    boss: Mapping[str, Any] | None,
    boss_types: list[str],
    rules: CleanupRules,
    limit: int = MAX_COUNTERS,
) -> list[dict[str, Any]]:
    """Rank the user's own Pokémon against a boss (or neutral, when ``boss`` is None)."""
    stab = float(gd.mechanics.get("pve", {}).get("stab") or 1.0)
    defense = boss_defense(int(boss["stats"]["def"])) if boss else boss_defense(int(_median_defense(gd)))

    def effectiveness(move_type: str) -> float:
        return gd.effectiveness(move_type, boss_types) if boss_types else 1.0

    results = []
    pokemon_rows = session.scalars(
        select(Pokemon).where(
            Pokemon.trainer_account_id == account_id,
            Pokemon.inventory_status == "in_inventory",
            Pokemon.form_key.is_not(None),
            Pokemon.level.is_not(None),
        )
    ).all()
    for pokemon in pokemon_rows:
        form = gd.forms.get(pokemon.form_key or "")
        if form is None or not pokemon.move_fast_key:
            continue
        attack = _attack_stat(gd, pokemon, form)
        if attack is None:
            continue
        types = list(form.get("types", []))
        current = max(
            (
                r
                for r in (
                    moveset_dps(
                        gd.moves,
                        pokemon.move_fast_key,
                        c,
                        attack=attack,
                        defense=defense,
                        attacker_types=types,
                        effectiveness=effectiveness,
                        stab_multiplier=stab,
                    )
                    for c in (pokemon.move_charged_1_key, pokemon.move_charged_2_key, None)
                )
                if r is not None
            ),
            key=lambda r: r.dps,
            default=None,
        )
        if current is None:
            continue
        pool_fast = list(form.get("fast_moves", [])) + (
            list(form.get("elite_fast", [])) if rules.elite_tm_available else []
        )
        pool_charged = list(form.get("charged_moves", [])) + (
            list(form.get("elite_charged", [])) if rules.elite_tm_available else []
        )
        best = current
        for fast in pool_fast:
            for charged in [*pool_charged, None]:
                result = moveset_dps(
                    gd.moves,
                    fast,
                    charged,
                    attack=attack,
                    defense=defense,
                    attacker_types=types,
                    effectiveness=effectiveness,
                    stab_multiplier=stab,
                )
                if result and result.dps > best.dps:
                    best = result
        results.append(
            {
                "pokemon_id": pokemon.id,
                "name": pokemon.species_name,
                "form_label": pokemon.form_label,
                "shadow": _shadow(pokemon),
                "cp": pokemon.cp,
                "level": pokemon.level,
                "types": types,
                "current": {
                    "dps": round(current.dps, 2),
                    "fast": _move_name(gd, current.fast),
                    "charged": _move_name(gd, current.charged),
                    "effectiveness": current.effectiveness_charged or current.effectiveness_fast,
                },
                "best_moveset": {
                    "dps": round(best.dps, 2),
                    "fast": _move_name(gd, best.fast),
                    "charged": _move_name(gd, best.charged),
                    "needs_tm": (best.fast, best.charged) != (current.fast, current.charged),
                    "needs_elite_tm": any(
                        m and availability(form, m) is Availability.ELITE_TM for m in (best.fast, best.charged)
                    ),
                },
                "weak_to_boss": bool(boss_types)
                and any(gd.effectiveness(t, types) > SUPER_EFFECTIVE for t in boss_types),
            }
        )
    results.sort(key=lambda r: -r["current"]["dps"])
    return results[:limit]


def _median_defense(gd: GameData) -> float:
    values = sorted(f["stats"]["def"] for f in gd.forms.values() if isinstance(f["stats"].get("def"), int))
    return values[len(values) // 2] if values else 1.0


def _move_name(gd: GameData, key: str | None) -> str | None:
    if key is None:
        return None
    return str((gd.move(key) or {}).get("name", key))


def rocket_counters(
    session: Session,
    gd: GameData,
    account_id: int,
    opponents: Sequence[Mapping[str, Any]],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Per opponent, the user's Pokémon with the best typing and stats against it (heuristic)."""
    stab = float(gd.mechanics.get("pvp", {}).get("stab") or 1.0)
    pokemon_rows = session.scalars(
        select(Pokemon).where(
            Pokemon.trainer_account_id == account_id,
            Pokemon.inventory_status == "in_inventory",
            Pokemon.form_key.is_not(None),
            Pokemon.level.is_not(None),
        )
    ).all()
    output = []
    for opponent in opponents:
        opp_types = list(opponent.get("types", []))
        ranked = []
        for pokemon in pokemon_rows:
            form = gd.forms.get(pokemon.form_key or "")
            if form is None:
                continue
            base = base_stats_of(dict(form))
            cpm = gd.cpm(pokemon.level) if pokemon.level is not None else None
            if base is None or cpm is None or None in (pokemon.iv_attack, pokemon.iv_defense, pokemon.iv_stamina):
                continue
            ivs = IVs(pokemon.iv_attack, pokemon.iv_defense, pokemon.iv_stamina)  # type: ignore[arg-type]
            types = list(form.get("types", []))
            offense = 0.0
            for key in (
                pokemon.move_fast_key,
                pokemon.move_charged_1_key,
                pokemon.move_charged_2_key,
            ):
                move = gd.move(key)
                if not move or not move.get("pvp"):
                    continue
                pvp = move["pvp"]
                eff = gd.effectiveness(move["type"], opp_types)
                bonus = stab if move["type"] in types else 1.0
                if move["kind"] == "fast":
                    offense += pvp["power"] / max(pvp["turns"], 1) * eff * bonus
                else:
                    offense += pvp["power"] / max(-pvp["energy"], 1) * 4 * eff * bonus
            incoming = max((gd.effectiveness(t, types) for t in opp_types), default=1.0)
            attack = (base.attack + ivs.attack) * cpm
            bulk = (base.defense + ivs.defense) * cpm * (base.stamina + ivs.stamina) * cpm
            score = offense * attack * (bulk**0.5) / incoming
            ranked.append(
                {
                    "pokemon_id": pokemon.id,
                    "name": pokemon.species_name,
                    "form_label": pokemon.form_label,
                    "cp": pokemon.cp,
                    "types": types,
                    "score": round(score / 1000, 1),
                    "resists": incoming < 1.0,
                    "weak": incoming > 1.0,
                    "moves": [
                        _move_name(gd, k)
                        for k in (
                            pokemon.move_fast_key,
                            pokemon.move_charged_1_key,
                            pokemon.move_charged_2_key,
                        )
                        if k
                    ],
                }
            )
        ranked.sort(key=lambda r: -r["score"])
        output.append({"opponent": opponent.get("name"), "types": opp_types, "counters": ranked[:limit]})
    return output


def max_attack(gd: GameData, pokemon: Pokemon) -> dict[str, Any]:
    """Type and name of the attack a Dynamax or Gigantamax Pokémon uses in a Max Battle (audit A15).

    Dynamax: the Max move of the fast move's type. Gigantamax: the species' fixed G-Max move from
    the Game Data. Without that data the type is unknown, never the fast move's type.
    """
    if pokemon.bread_mode == BreadMode.GIGANTAMAX:
        move = gd.gmax_move(pokemon.species_id, pokemon.form_key)
        if move is not None:
            return {"type": move["type"], "name": move["name"], "source": "gmax_move", "unknown_reason": None}
        reason = (
            _text("NO_GMAX_MOVES", "De actieve Game Data bevat nog geen G-Max-aanvallen. Werk de Game Data bij.")
            if gd.gmax_moves is None
            else _text("NO_GMAX_MOVE", "Voor deze Pokémon en vorm staat geen G-Max-aanval in de Game Data.")
        )
        return {"type": None, "name": None, "source": None, "unknown_reason": reason}
    fast = gd.move(pokemon.move_fast_key)
    attack_type = fast.get("type") if fast else None
    if attack_type is None:
        reason = _text("FAST_MOVE_UNKNOWN", "De snelle aanval is onbekend.")
        return {"type": None, "name": None, "source": None, "unknown_reason": reason}
    bread = gd.dataset.get("bread", {})
    move = (bread.get("max_moves") or {}).get(bread.get("max_moves_by_type", {}).get(attack_type) or "")
    return {"type": attack_type, "name": move["name"] if move else None, "source": "fast_move", "unknown_reason": None}


def max_battle_overview(session: Session, gd: GameData, account_id: int, boss_types: list[str]) -> dict[str, Any]:
    rows = session.scalars(
        select(Pokemon).where(
            Pokemon.trainer_account_id == account_id,
            Pokemon.inventory_status == "in_inventory",
            Pokemon.bread_mode.in_((BreadMode.DYNAMAX, BreadMode.GIGANTAMAX)),
        )
    ).all()
    groups = gd.dataset.get("bread", {}).get("groups", {})
    items = []
    for pokemon in rows:
        form = gd.forms.get(pokemon.form_key or "") or {}
        attack = max_attack(gd, pokemon)
        attack_type = attack["type"]
        types = list(form.get("types", []))
        levels = {MAX_MOVE_TYPES.get(m["type"], str(m["type"])): m["level"] for m in pokemon.bread_moves}
        group = groups.get(str(form.get("bread_group"))) if form else None
        next_costs = {}
        for name in ("attack", "guard", "spirit"):
            level = levels.get(name, 0)
            table = (group or {}).get(name) or []
            next_costs[name] = table[level] if level < len(table) else None
        base = base_stats_of(dict(form)) if form else None
        items.append(
            {
                "pokemon_id": pokemon.id,
                "name": pokemon.species_name,
                "cp": pokemon.cp,
                "level": pokemon.level,
                "gigantamax": pokemon.bread_mode == BreadMode.GIGANTAMAX,
                "types": types,
                "max_attack_type": attack_type,
                "max_attack_name": attack["name"],
                "max_attack_source": attack["source"],
                "max_attack_unknown_reason": attack["unknown_reason"],
                "fast_move": _move_name(gd, pokemon.move_fast_key),
                "max_moves": levels,
                "next_upgrade_cost": next_costs,
                "bread_group": form.get("bread_group"),
                "attack_effectiveness": gd.effectiveness(attack_type, boss_types)
                if attack_type and boss_types
                else None,
                "incoming_effectiveness": max((gd.effectiveness(t, types) for t in boss_types), default=None)
                if boss_types
                else None,
                "defense_stat": base.defense if base else None,
            }
        )
    attackers = (
        sorted(
            [i for i in items if i["attack_effectiveness"] is not None],
            key=lambda i: (-(i["attack_effectiveness"] or 0), -(i["cp"] or 0)),
        )[:6]
        if boss_types
        else []
    )
    defenders = (
        sorted(
            [i for i in items if i["incoming_effectiveness"] is not None],
            key=lambda i: ((i["incoming_effectiveness"] or 9), -(i["defense_stat"] or 0)),
        )[:6]
        if boss_types
        else []
    )
    return {
        "pokemon": items,
        "advice": {"attackers": attackers, "defenders": defenders} if boss_types else None,
        "notes": MAX_NOTES,
    }
