"""The Cleanup engine (spec §11, §18, ADR-0019). Deterministic and pure.

For every Pokémon it computes two scores (see :mod:`app.recommendations.scores`), decides one
status (PROTECT, KEEP, BUILD, REVIEW, TRANSFER_CANDIDATE or UNKNOWN) and records *why*: every
reason in the output comes from a rule or a comparison made here. Nothing is ever
transferred; the result is advice.

Every Pokémon is analysed and compared, protected or not. Protection only decides the status:

* hard protection (vintage 2016–2019, manual, protecting tags and the ``protect_*`` rules)
  always gives PROTECT, whatever the scores are;
* favorites are soft: they raise the keep score, and a favorite that would otherwise be a
  transfer candidate becomes REVIEW, with the better copy named;
* a Pokémon without a usable catch date is never assumed to be new: it can be REVIEW, never
  a regular transfer candidate;
* an upcoming event can hold a transfer candidate until it ends, see
  :mod:`app.recommendations.events` (ADR-0021).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from app.analysis.league import LeagueTarget
from app.domain.pokemon import VINTAGE_FIRST_YEAR, VINTAGE_LAST_YEAR
from app.recommendations.events import EventInfo, hold_for, hold_reason, relevant, tip_reason, transfer_tip
from app.recommendations.model import PokemonView
from app.recommendations.rules import SCORE_MAX, CleanupRules
from app.recommendations.scores import (
    LEAGUE_LABELS,
    GroupPosition,
    Score,
    battle_score,
    comparison_key,
    group_positions,
    keep_score,
)

__all__ = ["CollectionContext", "Confidence", "PokemonView", "Recommendation", "Status", "evaluate"]

READINESS_ORDER = {"direct": 0, "power_up": 1, "evolution": 2}
PRIORITY_BASE = 50
PVP_LEAGUES = ("great", "ultra")
MAX_SIMILAR = 3
VINTAGE_TEXT = f"Vintage Pokémon ({VINTAGE_FIRST_YEAR}–{VINTAGE_LAST_YEAR})"
# REVIEW reasons that only express doubt about the score. The best copy of a group with such a
# REVIEW is kept instead; a REVIEW the user asked for, or one caused by unclear data, is not.
SCORE_DOUBT = {"KEEP_SCORE_DOUBT"}


class Status(StrEnum):
    PROTECT = "PROTECT"
    KEEP = "KEEP"
    BUILD = "BUILD"
    REVIEW = "REVIEW"
    TRANSFER_CANDIDATE = "TRANSFER_CANDIDATE"
    UNKNOWN = "UNKNOWN"


KEPT = (Status.PROTECT, Status.KEEP, Status.BUILD)


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(slots=True)
class Recommendation:
    pokemon_id: int
    status: Status
    priority: int
    confidence: Confidence
    protection_reasons: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[dict[str, Any]] = field(default_factory=list)
    roles: list[dict[str, Any]] = field(default_factory=list)
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    battle_score: int | None = None
    keep_score: int | None = None
    scores: dict[str, Any] = field(default_factory=dict)
    overridden: bool = False

    @property
    def codes(self) -> set[str]:
        return {r["code"] for r in self.reasons}


@dataclass(frozen=True, slots=True)
class CollectionContext:
    has_game_data: bool
    last_import_partial: bool
    # Upcoming events for this account, and the moment and time zone the analysis runs in.
    events: tuple[EventInfo, ...] = ()
    now: datetime | None = None
    timezone: str = "UTC"


def _reason(code: str, text: str, **data: Any) -> dict[str, Any]:
    return {"code": code, "text": text, **({"data": data} if data else {})}


def _decimal(value: float | None) -> str:
    return "?" if value is None else f"{value:.1f}".replace(".", ",")


def protection_reasons(view: PokemonView, rules: CleanupRules) -> list[dict[str, Any]]:
    """Hard protections. Favorites are not among them (ADR-0019)."""
    reasons: list[dict[str, Any]] = []
    if view.vintage_year is not None:
        reasons.append(_reason("VINTAGE", f"{VINTAGE_TEXT}: gevangen in {view.vintage_year}", year=view.vintage_year))
    if view.manual_protected:
        reasons.append(
            _reason(
                "MANUAL",
                "Handmatig beschermd" + (f": {view.manual_reason}" if view.manual_reason else ""),
            )
        )
    for tag in view.protecting_tags:
        reasons.append(_reason("TAG", f"Beschermende tag '{tag}'"))
    if rules.protect_shiny and view.shiny:
        reasons.append(_reason("SHINY", "Shiny"))
    if rules.protect_lucky and view.lucky:
        reasons.append(_reason("LUCKY", "Lucky"))
    if rules.protect_hundo and view.hundo:
        reasons.append(_reason("SHUNDO" if view.shiny else "HUNDO", "Shundo" if view.shiny else "Hundo (15/15/15)"))
    if rules.protect_location_card and view.location_card:
        reasons.append(_reason("LOCATION_CARD", "Speciale achtergrond"))
    if rules.protect_costume and view.costume:
        reasons.append(_reason("COSTUME", "Kostuum"))
    if rules.protect_mythical and view.species_class == "mythical":
        reasons.append(_reason("MYTHICAL", "Mythical"))
    if rules.protect_legendary and view.species_class == "legendary":
        reasons.append(_reason("LEGENDARY", "Legendary"))
    if rules.protect_ultra_beast and view.species_class == "ultra_beast":
        reasons.append(_reason("ULTRA_BEAST", "Ultra Beast"))
    if rules.protect_shadow and view.shadow:
        reasons.append(_reason("SHADOW", "Shadow"))
    if rules.protect_purified and view.purified:
        reasons.append(_reason("PURIFIED", "Purified"))
    if rules.protect_gigantamax and view.gigantamax:
        reasons.append(_reason("GIGANTAMAX", "Gigantamax"))
    elif rules.protect_dynamax and view.dynamax:
        reasons.append(_reason("DYNAMAX", "Dynamax"))
    if rules.protect_event and view.event:
        reasons.append(_reason("EVENT", "Event-Pokémon"))
    if rules.protect_nicknamed and view.nicknamed:
        reasons.append(_reason("NICKNAME", "Heeft een bijnaam"))
    if rules.protect_mega_progress and view.mega_progress:
        reasons.append(_reason("MEGA", "Mega-voortgang"))
    return reasons


def _relevant(target: LeagueTarget, rules: CleanupRules) -> bool:
    return target.species_rank is not None and target.species_rank <= rules.meta_rank_threshold


def primary_target(targets: list[LeagueTarget]) -> LeagueTarget | None:
    """The target that defines a Pokémon's potential in a league: the most competitive species
    it can become (PvPoke rank), then its IV rank for that species."""
    usable = [t for t in targets if t.readiness not in ("not_suitable", "unknown")]
    if not usable:
        return None
    return min(
        usable,
        key=lambda t: (
            t.species_rank if t.species_rank is not None else 10**6,
            t.rank,
            t.is_evolution,
        ),
    )


def _pick_key(item: tuple[PokemonView, LeagueTarget]) -> tuple[Any, ...]:
    view, target = item
    stardust = target.cost.stardust if target.cost else 0
    return (target.rank, READINESS_ORDER.get(target.readiness, 9), stardust, view.id)


def assign_roles(views: list[PokemonView], rules: CleanupRules) -> dict[int, list[dict[str, Any]]]:
    """Best copies per league target. Every Pokémon competes, protected and favorite ones too."""
    roles: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for league, enabled in (("great", rules.keep_best_great), ("ultra", rules.keep_best_ultra)):
        if not enabled:
            continue
        by_target: dict[str, list[tuple[PokemonView, LeagueTarget]]] = defaultdict(list)
        for view in views:
            for target in view.leagues.get(league, []):
                if target.readiness in ("not_suitable", "unknown") or not _relevant(target, rules):
                    continue
                if target.target_key.endswith("SHADOW") or view.shadow:
                    key = f"{target.target_key}|shadow"
                else:
                    key = target.target_key
                by_target[key].append((view, target))
        for candidates in by_target.values():
            view, target = min(candidates, key=_pick_key)
            roles[view.id].append(
                {
                    "role": f"best_{league}",
                    "league": league,
                    "target": target.target_name,
                    "target_key": target.target_key,
                    "rank": target.rank,
                    "readiness": target.readiness,
                    "competitors": len(candidates) - 1,
                }
            )
    if rules.keep_best_master or rules.keep_best_raid:
        by_master: dict[str, list[tuple[PokemonView, LeagueTarget]]] = defaultdict(list)
        for view in views:
            for target in view.leagues.get("master", []):
                if _relevant(target, rules) and target.readiness != "unknown":
                    by_master[f"{target.target_key}|{'shadow' if view.shadow else 'regular'}"].append((view, target))
        for candidates in by_master.values():
            if rules.keep_best_master:
                view, target = max(candidates, key=lambda c: (c[1].percent, c[0].level or 0, -c[0].id))
                roles[view.id].append(
                    {
                        "role": "best_master",
                        "league": "master",
                        "target": target.target_name,
                        "target_key": target.target_key,
                        "percent": target.percent,
                        "competitors": len(candidates) - 1,
                    }
                )
            if rules.keep_best_raid:
                view, target = max(
                    candidates,
                    key=lambda c: (
                        c[0].iv_attack or 0,
                        c[0].iv_percent or 0,
                        c[0].level or 0,
                        -c[0].id,
                    ),
                )
                roles[view.id].append(
                    {
                        "role": "best_raid",
                        "league": None,
                        "target": target.target_name,
                        "target_key": target.target_key,
                        "competitors": len(candidates) - 1,
                    }
                )
    return roles


def _unknown_battle(view: PokemonView, context: CollectionContext) -> str | None:
    if not context.has_game_data:
        return "Geen actieve Game Data"
    if not view.has_ivs or view.level is None:
        return "IV's of level ontbreken in de export"
    if view.form_resolution == "unknown_species":
        return "Soort onbekend in de Game Data"
    return None


def evaluate(views: list[PokemonView], rules: CleanupRules, context: CollectionContext) -> list[Recommendation]:
    for view in views:
        view.primary = {league: primary_target(view.leagues.get(league, [])) for league in view.leagues}
    roles = assign_roles(views, rules) if context.has_game_data else {}

    battle: dict[int, Score] = {}
    for view in views:
        missing = _unknown_battle(view, context)
        battle[view.id] = (
            Score(None, [{"code": "UNKNOWN", "text": missing, "value": 0.0}]) if missing else battle_score(view, rules)
        )
    groups: dict[str, list[PokemonView]] = defaultdict(list)
    for view in views:
        if view.group_key:
            groups[view.group_key].append(view)
    positions: dict[int, GroupPosition] = {}
    for members in groups.values():
        positions.update(group_positions(members, battle))
    keep = {view.id: keep_score(view, battle[view.id], positions.get(view.id), rules) for view in views}

    results = {view.id: _decide(view, roles.get(view.id, []), keep[view.id], rules, context) for view in views}
    _keep_best_of_group(groups, results, battle, rules)
    _soften(views, results, rules, context)
    _apply_events(views, results, rules, context)
    _compare(groups, results, battle, keep)
    _warn_favorites(views, results)
    for view in views:
        result = results[view.id]
        result.battle_score = battle[view.id].score
        result.keep_score = keep[view.id].score
        position = positions.get(view.id)
        result.scores = {
            "battle": battle[view.id].to_dict(),
            "keep": {
                **keep[view.id].to_dict(),
                "keep_threshold": rules.keep_threshold,
                "review_threshold": rules.review_threshold,
            },
            "position": {"rank": position.rank, "of": position.size} if position else None,
        }
        if result.status in (Status.TRANSFER_CANDIDATE, Status.REVIEW) and not result.overridden:
            result.priority = max(1, SCORE_MAX - (keep[view.id].score or 0))
    return [results[view.id] for view in views]


def _base_warnings(view: PokemonView, rules: CleanupRules) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if view.purified and not rules.protect_purified:
        warnings.append(_reason("PURIFIED", "Purified: lagere power-upkosten en mogelijk Return"))
    if view.traded:
        warnings.append(_reason("TRADED", "Is eerder geruild"))
    if not view.catch_date_known:
        warnings.append(_reason("UNKNOWN_DATE", "Vangstdatum onbekend: OAK neemt niet aan dat deze Pokémon nieuw is"))
    return warnings


def _decide(
    view: PokemonView,
    roles: list[dict[str, Any]],
    keep: Score,
    rules: CleanupRules,
    context: CollectionContext,
) -> Recommendation:
    protections = protection_reasons(view, rules)
    warnings = _base_warnings(view, rules)

    if view.override_status:
        status = Status(view.override_status)
        if view.vintage_year is not None and status in (Status.TRANSFER_CANDIDATE, Status.REVIEW):
            warnings.insert(
                0,
                _reason(
                    "VINTAGE_OVERRIDE",
                    f"Vintage {view.vintage_year}: je hebt de bescherming zelf opgeheven",
                    year=view.vintage_year,
                ),
            )
        return Recommendation(
            view.id,
            status,
            PRIORITY_BASE,
            Confidence.HIGH,
            protections,
            [_reason("OVERRIDE", "Handmatig vastgestelde status")],
            roles,
            [],
            warnings,
            overridden=True,
        )
    if protections:
        return Recommendation(
            view.id,
            Status.PROTECT,
            0,
            Confidence.HIGH,
            protections,
            [_reason("PROTECTED", "Beschermd: " + " + ".join(r["text"] for r in protections))],
            roles,
            [],
            warnings,
        )
    missing = _unknown_battle(view, context)
    if missing:
        code = {
            "Geen actieve Game Data": "NO_GAME_DATA",
            "Soort onbekend in de Game Data": "UNKNOWN_SPECIES",
        }.get(missing, "MISSING_DATA")
        return Recommendation(
            view.id, Status.UNKNOWN, 0, Confidence.LOW, [], [_reason(code, missing + ".")], [], [], warnings
        )

    reasons: list[dict[str, Any]] = []
    if roles:
        return _role_recommendation(view, roles, rules, context, warnings)

    score = keep.score or 0
    if score >= rules.keep_threshold:
        reasons.append(
            _reason(
                "HIGH_KEEP_SCORE",
                f"Bewaarscore {score} (bewaren vanaf {rules.keep_threshold})",
                keep_score=score,
            )
        )
        return Recommendation(
            view.id, Status.KEEP, PRIORITY_BASE, _confidence(view, context), [], reasons, [], [], warnings
        )

    good = [
        (league, target)
        for league in PVP_LEAGUES
        if (target := view.primary.get(league)) is not None
        and target.rank <= rules.good_iv_rank_threshold
        and _relevant(target, rules)
    ]
    if good or view.review_requested or view.form_resolution == "fallback_default_form":
        for league, target in good:
            reasons.append(
                _reason(
                    "GOOD_PVP_IVS",
                    f"Goede {LEAGUE_LABELS[league]}-IV's voor {target.target_name} (rang {target.rank}), "
                    "maar er is een beter exemplaar",
                    league=league,
                    rank=target.rank,
                )
            )
        if view.review_requested:
            reasons.append(_reason("REVIEW_REQUESTED", "Gemarkeerd voor review"))
        if view.form_resolution == "fallback_default_form":
            reasons.append(_reason("FORM_FALLBACK", "Vorm onbekend in de Game Data; standaardvorm gebruikt"))
        return Recommendation(view.id, Status.REVIEW, PRIORITY_BASE, Confidence.MEDIUM, [], reasons, [], [], warnings)

    if score >= rules.review_threshold:
        reasons.append(
            _reason(
                "KEEP_SCORE_DOUBT",
                f"Bewaarscore {score}: twijfelgeval (tussen {rules.review_threshold} en {rules.keep_threshold})",
                keep_score=score,
            )
        )
        return Recommendation(
            view.id, Status.REVIEW, PRIORITY_BASE, _confidence(view, context), [], reasons, [], [], warnings
        )

    reasons.append(_reason("NO_PROTECTION", "Geen harde bescherming"))
    reasons.append(_reason("NO_ROLE", "Geen unieke rol binnen de collectie"))
    reasons.append(
        _reason(
            "LOW_KEEP_SCORE",
            f"Bewaarscore {score} (onder {rules.review_threshold})",
            keep_score=score,
        )
    )
    for league in PVP_LEAGUES:
        target = view.primary.get(league)
        if target is not None and _relevant(target, rules):
            reasons.append(
                _reason(
                    "WEAK_PVP",
                    f"{LEAGUE_LABELS[league]}: IV-rang {target.rank} voor {target.target_name} "
                    f"({_decimal(target.percent)}% van de beste)",
                    league=league,
                    rank=target.rank,
                    percent=target.percent,
                )
            )
    return Recommendation(
        view.id,
        Status.TRANSFER_CANDIDATE,
        PRIORITY_BASE,
        _confidence(view, context),
        [],
        reasons,
        [],
        [],
        warnings,
    )


def _role_recommendation(
    view: PokemonView,
    roles: list[dict[str, Any]],
    rules: CleanupRules,
    context: CollectionContext,
    warnings: list[dict[str, Any]],
) -> Recommendation:
    reasons: list[dict[str, Any]] = []
    build_roles = [r for r in roles if r.get("readiness") in ("power_up", "evolution")]
    for role in roles:
        reasons.append(
            _reason(
                role["role"].upper(),
                _role_text(role),
                **{k: v for k, v in role.items() if k != "role"},
            )
        )
    pvp_roles = [r for r in roles if r["role"] in ("best_great", "best_ultra")]
    only_future_pvp = (
        bool(pvp_roles)
        and len(pvp_roles) == len(roles)
        and all(
            r.get("readiness") in ("power_up", "evolution") and r["rank"] <= rules.build_iv_rank_threshold
            for r in pvp_roles
        )
    )
    weak_best = (
        pvp_roles
        and not only_future_pvp
        and all(r["rank"] > rules.build_iv_rank_threshold for r in pvp_roles)
        and not any(r["role"] in ("best_master", "best_raid") for r in roles)
    )
    if weak_best:
        reasons.append(
            _reason("WEAK_BEST_COPY", "Beste beschikbare exemplaar, maar de IV's zijn te zwak om in te investeren")
        )
    status = Status.BUILD if only_future_pvp else Status.KEEP
    for role in build_roles if status is Status.BUILD else []:
        target = _target_for(view, role)
        if target and target.cost:
            reasons.append(
                _reason(
                    "INVESTMENT",
                    f"{target.target_name} {LEAGUE_LABELS[role['league']]}: {target.cost.stardust:,} stardust, "
                    f"{target.cost.candy} candy, {target.cost.xl_candy} XL candy".replace(",", "."),
                    stardust=target.cost.stardust,
                    candy=target.cost.candy,
                    xl_candy=target.cost.xl_candy,
                )
            )
    return Recommendation(view.id, status, PRIORITY_BASE, _confidence(view, context), [], reasons, roles, [], warnings)


def _role_text(role: dict[str, Any]) -> str:
    kind = role["role"]
    if kind == "best_great":
        return f"Beste Great League-kandidaat voor {role['target']} (IV-rang {role['rank']})"
    if kind == "best_ultra":
        return f"Beste Ultra League-kandidaat voor {role['target']} (IV-rang {role['rank']})"
    if kind == "best_master":
        return f"Beste Master League-exemplaar voor {role['target']}"
    if kind == "best_raid":
        return f"Beste raid-aanvaller (Attack-IV) voor {role['target']}"
    if kind == "minimum":
        return "Minimaal aantal exemplaren per soort"
    return kind


def _target_for(view: PokemonView, role: dict[str, Any]) -> LeagueTarget | None:
    for target in view.leagues.get(role.get("league") or "", []):
        if target.target_key == role.get("target_key"):
            return target
    return None


def _confidence(view: PokemonView, context: CollectionContext) -> Confidence:
    if context.last_import_partial or view.form_resolution == "fallback_default_form":
        return Confidence.LOW
    if view.form_resolution in ("exact", "base"):
        return Confidence.HIGH
    return Confidence.MEDIUM


def _promote(result: Recommendation, reason: dict[str, Any]) -> None:
    result.status = Status.KEEP
    result.priority = PRIORITY_BASE
    result.reasons = [reason, *[r for r in result.reasons if r["code"] == "WEAK_PVP"]]
    result.roles.append({"role": "minimum", "league": None})


def _keep_best_of_group(
    groups: dict[str, list[PokemonView]],
    results: dict[int, Recommendation],
    battle: dict[int, Score],
    rules: CleanupRules,
) -> None:
    """The best copy of every group is kept, and at least ``keep_min_per_species`` copies.

    This guarantees that every transfer candidate has a better or equal copy that stays."""
    if rules.keep_min_per_species <= 0:
        return
    for members in groups.values():
        ordered = sorted(members, key=lambda m: comparison_key(m, battle[m.id]))
        best = results[ordered[0].id]
        if not best.overridden and (
            best.status is Status.TRANSFER_CANDIDATE or (best.status is Status.REVIEW and best.codes <= SCORE_DOUBT)
        ):
            text = "Beste exemplaar van deze soort in je collectie"
            if len(members) == 1:
                text = "Enige exemplaar van deze soort in je collectie"
            _promote(best, _reason("BEST_COPY", text, size=len(members)))
        missing = rules.keep_min_per_species - sum(1 for m in members if results[m.id].status in KEPT)
        for member in ordered[1:]:
            if missing <= 0:
                break
            result = results[member.id]
            if result.status is Status.TRANSFER_CANDIDATE and not result.overridden:
                _promote(
                    result,
                    _reason(
                        "MINIMUM",
                        f"Minimaal {rules.keep_min_per_species} exemplaren per soort bewaren",
                    ),
                )
                missing -= 1


def _soften(
    views: list[PokemonView],
    results: dict[int, Recommendation],
    rules: CleanupRules,
    context: CollectionContext,
) -> None:
    """Transfer advice OAK will not give directly: after a partial import, for a favorite, and
    for a Pokémon with an unknown catch date. These become REVIEW and say why."""
    for view in views:
        result = results[view.id]
        if result.overridden or result.status is not Status.TRANSFER_CANDIDATE:
            continue
        softened: list[dict[str, Any]] = []
        if context.last_import_partial and not rules.allow_transfer_on_partial_import:
            softened.append(_reason("PARTIAL_IMPORT", "De laatste import was niet volledig; geen transferadvies"))
            result.confidence = Confidence.LOW
        if view.favorite:
            softened.append(
                _reason(
                    "FAVORITE_REVIEW",
                    "Favoriet: OAK stelt een favoriet nooit direct voor als transfer. Beoordeel hem zelf.",
                )
            )
        if not view.catch_date_known:
            softened.append(_reason("UNKNOWN_DATE", "Vangstdatum onbekend: dit kan een vintage Pokémon zijn"))
        if softened:
            result.status = Status.REVIEW
            result.reasons = [*softened, *result.reasons]


def _apply_events(
    views: list[PokemonView],
    results: dict[int, Recommendation],
    rules: CleanupRules,
    context: CollectionContext,
) -> None:
    """Hold transfer candidates for an upcoming event, and give a timing tip (ADR-0021).

    Event data is not official, so advice that rests on it is at most of medium confidence.
    """
    if not rules.use_events or not context.events or context.now is None:
        return
    events = relevant(context.events, context.now, rules.event_hold_days)
    if not events:
        return
    tz = ZoneInfo(context.timezone)
    tip = transfer_tip(events)
    for view in views:
        result = results[view.id]
        if result.overridden or result.status not in (Status.TRANSFER_CANDIDATE, Status.REVIEW):
            continue
        hold = hold_for(view.family, events)
        if hold is not None:
            if result.status is Status.TRANSFER_CANDIDATE:
                result.status = Status.KEEP
                result.priority = PRIORITY_BASE
            result.reasons = [hold_reason(hold, tz), *result.reasons]
            if result.confidence is Confidence.HIGH:
                result.confidence = Confidence.MEDIUM
        elif tip is not None and result.status is Status.TRANSFER_CANDIDATE:
            result.reasons = [*result.reasons, tip_reason(tip, tz)]


def _differences(view: PokemonView, better: PokemonView, battle: dict[int, Score]) -> str:
    details: list[str] = []
    mine, theirs = battle[view.id].score, battle[better.id].score
    if mine is not None and theirs is not None and theirs != mine:
        details.append(f"bruikbaarheid {theirs} tegen {mine}")
    for league in (*PVP_LEAGUES, "master"):
        own, other = view.primary.get(league), better.primary.get(league)
        if own and other and own.target_key == other.target_key and other.rank < own.rank:
            details.append(f"{LEAGUE_LABELS[league]} IV-rang {other.rank} tegen {own.rank}")
            break
    if better.iv_percent is not None and view.iv_percent is not None and better.iv_percent > view.iv_percent:
        details.append(f"IV {_decimal(better.iv_percent)}% tegen {_decimal(view.iv_percent)}%")
    return ", ".join(details) if details else "minstens even goed"


def _describe(view: PokemonView) -> str:
    cp = view.cp if view.cp is not None else "?"
    year = f", gevangen in {view.caught_year}" if view.catch_date_known else ""
    return f"{view.name} (CP {cp}{year})"


def _similar(
    member: PokemonView,
    others: list[PokemonView],
    results: dict[int, Recommendation],
    battle: dict[int, Score],
    keep: dict[int, Score],
) -> list[dict[str, Any]]:
    own = comparison_key(member, battle[member.id])
    return [
        {
            "pokemon_id": m.id,
            "name": m.name,
            "cp": m.cp,
            "iv_percent": m.iv_percent,
            "status": results[m.id].status.value,
            "battle_score": battle[m.id].score,
            "keep_score": keep[m.id].score,
            "caught_year": m.caught_year,
            "favorite": m.favorite,
            "better": comparison_key(m, battle[m.id]) < own,
        }
        for m in others[:MAX_SIMILAR]
    ]


def _compare(
    groups: dict[str, list[PokemonView]],
    results: dict[int, Recommendation],
    battle: dict[int, Score],
    keep: dict[int, Score],
) -> None:
    """Similar Pokémon for every result, and the explanation why another copy is better."""
    for members in groups.values():
        ordered = sorted(members, key=lambda m: comparison_key(m, battle[m.id]))
        rank = {m.id: index for index, m in enumerate(ordered)}
        for member in members:
            result = results[member.id]
            result.alternatives = _similar(member, [m for m in ordered if m.id != member.id], results, battle, keep)
            better_kept = next(
                (m for m in ordered if rank[m.id] < rank[member.id] and results[m.id].status in KEPT),
                None,
            )
            softened = result.codes & {"FAVORITE_REVIEW", "UNKNOWN_DATE", "PARTIAL_IMPORT"}
            review = result.status is Status.REVIEW and not result.overridden
            if result.status is Status.TRANSFER_CANDIDATE or review:
                position = max(1, len(softened)) if review else 0
                if better_kept is not None:
                    text = (
                        f"Een andere {_describe(better_kept)} blijft bewaard en is beter: "
                        f"{_differences(member, better_kept, battle)}"
                    )
                    result.reasons.insert(position, _reason("BETTER_DUPLICATE", text, pokemon_id=better_kept.id))
                elif member.favorite:
                    result.reasons.insert(
                        position, _reason("NO_BETTER_COPY", "Er is geen beter exemplaar dat bewaard blijft")
                    )
            if result.status is Status.PROTECT and member.vintage_year is not None and len(members) > 1:
                newer_better = next(
                    (m for m in ordered if rank[m.id] < rank[member.id] and m.vintage_year is None), None
                )
                if newer_better is not None:
                    text = (
                        f"Ter vergelijking: {_describe(newer_better)} is beter voor gevechten: "
                        f"{_differences(member, newer_better, battle)}. Deze vintage Pokémon blijft beschermd."
                    )
                    result.reasons.append(_reason("VINTAGE_COMPARISON", text, pokemon_id=newer_better.id))
                elif rank[member.id] == 0:
                    result.reasons.append(
                        _reason("VINTAGE_BEST", "Ook vergeleken met nieuwere exemplaren het beste van zijn soort")
                    )


def _warn_favorites(views: list[PokemonView], results: dict[int, Recommendation]) -> None:
    """A favorite that is not kept always carries a clear warning (ADR-0019)."""
    for view in views:
        result = results[view.id]
        warned = "FAVORITE" in {w["code"] for w in result.warnings}
        if view.favorite and result.status in (Status.REVIEW, Status.TRANSFER_CANDIDATE) and not warned:
            result.warnings.insert(0, _reason("FAVORITE", "Favoriet: controleer zelf of je hem echt kwijt wilt"))
