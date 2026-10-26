"""Pokémon Box, detail, metadata and exports (spec §9, §10, §20.4)."""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.evolution import evolution_paths, path_candy
from app.analysis.league import LEAGUES, Subject, analyze_leagues, league_cap
from app.analysis.moves import availability, moveset_needs
from app.analysis.powerup import power_up_cost, reachable_max_level
from app.analysis.purify import purify
from app.analysis.stats import IVs, base_stats_of, combat_power, hit_points
from app.api.deps import (
    AuthContext,
    get_auth,
    get_container,
    get_session,
    owned_account,
    owned_pokemon,
)
from app.core.container import Container
from app.core.errors import ConflictError, ValidationFailedError
from app.domain.changes import change_labels
from app.domain.pokemon import Alignment, vintage_year
from app.domain.query import QuerySyntaxError, parse_query
from app.gamedata.model import GameData
from app.jobs.tasks import enqueue
from app.models import (
    PlannedAction,
    Pokemon,
    PokemonAnalysis,
    PokemonChangeEvent,
    PokemonUserMetadata,
    PvpRanking,
    SyncRun,
    TagLabel,
)
from app.recommendations.cleanup import primary_target
from app.repositories.pokemon_query import (
    BoxFilters,
    base_query,
    filter_conditions,
    order_by,
    term_condition,
)
from app.services.analysis import rules_for
from app.services.pokemon_view import PokemonSummary, detail_extras, summarize
from app.services.transfer_guard import check_transfer, confirmation_item, guard_context

router = APIRouter(prefix="/pokemon", tags=["pokemon"])
MAX_PAGE_SIZE = 500
MAX_BULK = 2000
MAX_COMPARE = 6
PLANNED_ACTIONS = {
    "keep",
    "transfer",
    "evolve",
    "power_up",
    "trade",
    "purify",
    "tm",
    "mega",
    "buddy",
}
REVIEW_STATUSES = {"none", "to_review", "reviewed"}
OVERRIDE_STATUSES = {"PROTECT", "KEEP", "BUILD", "REVIEW", "TRANSFER_CANDIDATE"}
# Overrides that lift the hard protection of a vintage Pokémon.
VINTAGE_OVERRIDES = {"REVIEW", "TRANSFER_CANDIDATE"}
LEAGUE_IDS = {"great", "ultra", "master"}
FLAG_PARAMS = (
    "shiny",
    "lucky",
    "shadow",
    "purified",
    "favorite",
    "legendary",
    "mythical",
    "ultrabeast",
    "costume",
    "background",
    "dynamax",
    "gigantamax",
    "hundo",
    "shundo",
    "traded",
    "new",
    "protected",
    "untagged",
    "duplicate",
    "nicknamed",
    "egg_hatched",
    "mega",
    "vintage",
    "unknown_date",
)
CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sync_bounds(session: Session, account_id: int) -> tuple[int | None, int | None]:
    latest = session.scalar(select(func.max(SyncRun.id)).where(SyncRun.trainer_account_id == account_id))
    first = session.scalar(select(func.min(SyncRun.id)).where(SyncRun.trainer_account_id == account_id))
    return latest, first


def tag_label_map(session: Session, account_id: int) -> dict[str, str]:
    return {
        t.tag_id: t.label for t in session.scalars(select(TagLabel).where(TagLabel.trainer_account_id == account_id))
    }


def _bool_param(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    if value.lower() in ("1", "true", "yes", "ja"):
        return True
    if value.lower() in ("0", "false", "no", "nee"):
        return False
    raise ValidationFailedError(f"'{value}' is geen ja/nee-waarde.", context="boolean", data={"value": value})


def build_filters(params: dict[str, Any]) -> BoxFilters:
    flags: dict[str, bool] = {}
    for flag in FLAG_PARAMS:
        value = _bool_param(params.get(flag))
        if value is not None:
            flags[flag] = value

    def ints(name: str) -> list[int]:
        raw = params.get(name) or ""
        try:
            return [int(v) for v in str(raw).split(",") if v.strip()]
        except ValueError as exc:
            raise ValidationFailedError(
                f"{name} moet een lijst getallen zijn.", context="number_list", data={"field": name}
            ) from exc

    return BoxFilters(
        status=params.get("status") or "in_inventory",
        species=ints("species"),
        cp_min=params.get("cp_min"),
        cp_max=params.get("cp_max"),
        iv_min=params.get("iv_min"),
        iv_max=params.get("iv_max"),
        level_min=params.get("level_min"),
        level_max=params.get("level_max"),
        years=ints("years"),
        flags=flags,
        cleanup_status=[s for s in (params.get("cleanup") or "").split(",") if s],
        league=params.get("league"),
        move=params.get("move"),
        family=params.get("family"),
        type=params.get("type"),
        tag=params.get("tag"),
        planned_action=params.get("planned"),
    )


class BoxQuery(BaseModel):
    account_id: int
    q: str | None = None
    status: str | None = Field(default=None, pattern="^(in_inventory|not_in_inventory|all)$")
    species: str | None = None
    cp_min: int | None = None
    cp_max: int | None = None
    iv_min: float | None = None
    iv_max: float | None = None
    level_min: float | None = None
    level_max: float | None = None
    years: str | None = None
    cleanup: str | None = None
    league: str | None = Field(default=None, pattern="^(great|ultra|master)$")
    move: str | None = None
    family: str | None = None
    type: str | None = None
    tag: str | None = None
    planned: str | None = None
    sort: str = "-cp"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=MAX_PAGE_SIZE)
    shiny: str | None = None
    lucky: str | None = None
    shadow: str | None = None
    purified: str | None = None
    favorite: str | None = None
    legendary: str | None = None
    mythical: str | None = None
    ultrabeast: str | None = None
    costume: str | None = None
    background: str | None = None
    dynamax: str | None = None
    gigantamax: str | None = None
    hundo: str | None = None
    shundo: str | None = None
    traded: str | None = None
    new: str | None = None
    protected: str | None = None
    untagged: str | None = None
    duplicate: str | None = None
    nicknamed: str | None = None
    egg_hatched: str | None = None
    mega: str | None = None
    vintage: str | None = None
    unknown_date: str | None = None


def _conditions(query: BoxQuery, account_id: int, latest_sync_id: int | None) -> list[Any]:
    terms = []
    if query.q:
        try:
            terms = parse_query(query.q)
        except QuerySyntaxError as exc:
            raise ValidationFailedError(exc.message, code="QUERY_SYNTAX", context=exc.context, data=exc.data) from exc
    filters = build_filters(query.model_dump())
    # 'verdwenen' in the search box means: look beyond the current inventory.
    if any(t.kind == "flag" and t.field == "missing" and not t.negate for t in terms) and query.status is None:
        filters.status = "all"
    conditions = filter_conditions(filters, account_id, latest_sync_id)
    conditions.extend(term_condition(term, account_id, latest_sync_id) for term in terms)
    return conditions


@router.get("", response_model=dict[str, Any])
def list_pokemon(
    query: BoxQuery = Depends(),
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    account = owned_account(session, auth.user, query.account_id)
    latest, first = sync_bounds(session, account.id)
    conditions = _conditions(query, account.id, latest)
    stmt = base_query().where(*conditions)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.execute(
        stmt.order_by(*order_by(query.sort)).offset((query.page - 1) * query.page_size).limit(query.page_size)
    ).all()
    gd = container.gamedata.active()
    labels = tag_label_map(session, account.id)
    items = [
        summarize(p, m, a, gd, tag_labels=labels, latest_sync_id=latest, first_sync_id=first).model_dump(mode="json")
        for p, m, a in rows
    ]
    return {
        "total": total,
        "page": query.page,
        "page_size": query.page_size,
        "items": items,
        "game_data_version": gd.version_id if gd else None,
    }


@router.get("/facets", response_model=dict[str, Any])
def facets(
    account_id: int,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    account = owned_account(session, auth.user, account_id)
    base = (Pokemon.trainer_account_id == account.id, Pokemon.inventory_status == "in_inventory")
    species = session.execute(
        select(Pokemon.species_id, func.max(Pokemon.species_name), func.count())
        .where(*base)
        .group_by(Pokemon.species_id)
        .order_by(Pokemon.species_id)
    ).all()
    years = session.execute(
        select(Pokemon.caught_year, func.count())
        .where(*base)
        .group_by(Pokemon.caught_year)
        .order_by(Pokemon.caught_year)
    ).all()
    families = session.scalars(
        select(Pokemon.family_id).where(*base, Pokemon.family_id.is_not(None)).distinct().order_by(Pokemon.family_id)
    ).all()
    types = sorted(
        {
            t
            for pair in session.execute(select(Pokemon.type_1, Pokemon.type_2).where(*base).distinct())
            for t in pair
            if t
        }
    )
    tag_counts: dict[str, int] = {}
    for tags in session.scalars(select(Pokemon.tag_ids).where(*base)):
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    labels = {
        t.tag_id: {"label": t.label, "protects": t.protects}
        for t in session.scalars(select(TagLabel).where(TagLabel.trainer_account_id == account.id))
    }
    return {
        "species": [{"species_id": s, "name": n, "count": c} for s, n, c in species],
        "years": [{"year": y, "count": c} for y, c in years if y is not None],
        "families": list(families),
        "types": types,
        "tags": [
            {"tag_id": t, "count": c, **labels.get(t, {"label": None, "protects": False})}
            for t, c in sorted(tag_counts.items(), key=lambda kv: -kv[1])
        ],
    }


def _subject(pokemon: Pokemon, trainer_level: int | None) -> Subject:
    ivs = None
    if None not in (pokemon.iv_attack, pokemon.iv_defense, pokemon.iv_stamina):
        ivs = IVs(pokemon.iv_attack, pokemon.iv_defense, pokemon.iv_stamina)  # type: ignore[arg-type]
    return Subject(
        form_key=pokemon.form_key,
        ivs=ivs,
        level=pokemon.level,
        cp=pokemon.cp,
        shadow=pokemon.alignment == Alignment.SHADOW,
        purified=pokemon.alignment == Alignment.PURIFIED,
        lucky=bool(pokemon.lucky),
        trainer_level=trainer_level,
    )


Scenario = Literal["current", "purified"]
# Why purify() cannot calculate, with the context of each reason for the error message (ADR-0025).
PURIFY_ERRORS = {
    "Alleen een Shadow Pokémon kan worden gepurifyd.": "purify_not_shadow",
    "De regels voor purify ontbreken in deze Game Data-versie.": "purify_rules_missing",
    "IV's of level onbekend.": "purify_stats_unknown",
}


def _text(code: str, text: str, **data: Any) -> dict[str, Any]:
    """A sentence for the interface: a code with its data, and the Dutch text as fallback (ADR-0025)."""
    return {"code": code, "text": text, **({"data": data} if data else {})}


# What the columns of the battle analysis mean.
ANALYSIS_METHOD = {
    "iv_rank": _text(
        "METHOD_IV_RANK",
        "Rang van de IV-combinatie binnen deze soort en league (1–4096), op het hoogste level onder "
        "de CP-limiet, gesorteerd op stat product.",
    ),
    "species_rank": _text("METHOD_SPECIES_RANK", "Positie van de soort in de PvPoke-ranking voor deze league."),
    "readiness": _text("METHOD_READINESS", "Of dit exemplaar nu, na power-up of na evolutie inzetbaar is."),
}
CP_AFTER_UNKNOWN = _text("CP_AFTER_EVOLUTION_UNKNOWN", "CP na evolutie onbekend: level of IV's ontbreken.")
CANDY_ROUNDING = _text(
    "CANDY_ROUNDING",
    "Candy-kosten voor Shadow en Purified worden naar boven afgerond; de game documenteert de afronding niet.",
)


def _scenario(
    gd: GameData, pokemon: Pokemon, trainer_level: int | None, scenario: Scenario
) -> tuple[Subject, dict[str, Any] | None]:
    """The Pokémon as it is, or as it would be after purification (ADR-0022)."""
    subject = _subject(pokemon, trainer_level)
    if scenario == "current":
        return subject, None
    form = gd.forms.get(pokemon.form_key) if pokemon.form_key else None
    result = purify(subject, form, gd.mechanics.get("purification"))
    if isinstance(result, str):
        # An unknown reason gets a context without a catalog text, so the Dutch reason is shown.
        raise ValidationFailedError(result, context=PURIFY_ERRORS.get(result, "purify"))
    base = base_stats_of(dict(form)) if form else None
    cpm = gd.cpm(result.level)
    return result.subject, {
        "key": "purified",
        "level": result.level,
        "ivs": asdict(result.ivs),
        "cp": combat_power(base, result.ivs, cpm) if base and cpm else None,
        "hp": hit_points(base, result.ivs, cpm) if base and cpm else None,
        "cost": {"stardust": result.stardust, "candy": result.candy},
        "assumption": result.assumption,
        "source": result.source,
    }


def _purified_moves(form: Mapping[str, Any] | None, charged: list[str]) -> list[str]:
    """After purification the Shadow charged move becomes the Purified one (Frustration → Return)."""
    shadow = (form or {}).get("shadow") or {}
    old, new = shadow.get("shadow_move"), shadow.get("purified_move")
    return [new if old and new and key == old else key for key in charged]


@router.get("/{pokemon_id}", response_model=dict[str, Any])
def get_pokemon(
    pokemon_id: int,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    pokemon = owned_pokemon(session, auth.user, pokemon_id)
    metadata = session.get(PokemonUserMetadata, pokemon.id)
    analysis = session.get(PokemonAnalysis, pokemon.id)
    latest, first = sync_bounds(session, pokemon.trainer_account_id)
    gd = container.gamedata.active()
    summary = summarize(
        pokemon,
        metadata,
        analysis,
        gd,
        tag_labels=tag_label_map(session, pokemon.trainer_account_id),
        latest_sync_id=latest,
        first_sync_id=first,
    )
    planned = session.scalars(select(PlannedAction).where(PlannedAction.pokemon_id == pokemon.id)).all()
    return {
        **summary.model_dump(mode="json"),
        "details": detail_extras(pokemon),
        "recommendation": {
            "status": analysis.status,
            "priority": analysis.priority,
            "confidence": analysis.confidence,
            "battle_score": analysis.battle_score,
            "keep_score": analysis.keep_score,
            "scores": analysis.scores or {},
            "protection_reasons": analysis.protection_reasons,
            "reasons": analysis.reasons,
            "roles": analysis.roles,
            "alternatives": analysis.alternatives,
            "warnings": analysis.warnings,
            "computed_at": analysis.computed_at.isoformat(),
        }
        if analysis
        else None,
        "planned_actions": [{"list": p.list_name, "action": p.action, "status": p.status} for p in planned],
    }


@router.get("/{pokemon_id}/analysis", response_model=dict[str, Any])
def pokemon_analysis(
    pokemon_id: int,
    scenario: Scenario = "current",
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    pokemon = owned_pokemon(session, auth.user, pokemon_id)
    account = owned_account(session, auth.user, pokemon.trainer_account_id)
    gd = container.gamedata.active()
    if gd is None:
        return {"available": False, "reason": _text("NO_GAME_DATA", "Geen actieve Game Data.")}
    rules = rules_for(account)
    subject, scenario_info = _scenario(gd, pokemon, account.trainer_level, scenario)
    leagues = analyze_leagues(
        gd,
        subject,
        max_level=rules.max_level,
        include_best_buddy=rules.include_best_buddy,
        ready_cp_fraction=rules.ready_cp_fraction,
        elite_tm_available=rules.elite_tm_available,
    )
    form = gd.forms.get(pokemon.form_key) if pokemon.form_key else None
    current_fast = pokemon.move_fast_key
    current_charged = [m for m in (pokemon.move_charged_1_key, pokemon.move_charged_2_key) if m]
    if scenario_info is not None:
        current_charged = _purified_moves(form, current_charged)
    output: dict[str, Any] = {}
    for league in LEAGUES:
        targets = leagues.get(league, [])
        primary = primary_target(targets)
        entries = []
        for target in targets:
            item = asdict(target)
            item["cost"] = asdict(target.cost) if target.cost else None
            target_form = gd.forms.get(target.target_key)
            if target.moveset and target_form is not None:
                needs = moveset_needs(
                    target_form,
                    current_fast,
                    current_charged,
                    target.moveset.moveset,
                    second_move_unlocked=pokemon.move_charged_2 is not None,
                )
                item["moveset"] = {
                    **asdict(target.moveset),
                    "names": [str((gd.move(m) or {}).get("name", m)) for m in target.moveset.moveset],
                    "needs": [asdict(n) for n in needs],
                }
            entries.append(item)
        output[league] = {
            "cap": league_cap(gd, league),
            "primary_target": primary.target_key if primary else None,
            "targets": entries,
        }
    current_moves = []
    if form is not None:
        for key in [current_fast, *current_charged]:
            if key:
                current_moves.append(
                    {
                        "key": key,
                        "name": (gd.move(key) or {}).get("name", key),
                        "availability": availability(form, key).value,
                    }
                )
    third = (form or {}).get("third_move") or {}
    return {
        "available": True,
        "game_data_version": gd.version_id,
        "rules": {
            "max_level": rules.max_level,
            "include_best_buddy": rules.include_best_buddy,
            "elite_tm_available": rules.elite_tm_available,
            "ready_cp_fraction": rules.ready_cp_fraction,
        },
        "method": ANALYSIS_METHOD,
        "scenario": scenario_info,
        "leagues": output,
        "current_moves": current_moves,
        "second_move_cost": {"stardust": third.get("stardust"), "candy": third.get("candy")} if third else None,
        "form_resolution": pokemon.form_resolution,
    }


@router.get("/{pokemon_id}/evolutions", response_model=dict[str, Any])
def pokemon_evolutions(
    pokemon_id: int,
    scenario: Scenario = "current",
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    pokemon = owned_pokemon(session, auth.user, pokemon_id)
    account = owned_account(session, auth.user, pokemon.trainer_account_id)
    gd = container.gamedata.active()
    if gd is None or pokemon.form_key is None:
        reason = _text("NO_GAME_DATA_OR_FORM", "Geen Game Data of onbekende vorm.")
        return {"available": False, "paths": [], "reason": reason}
    subject, scenario_info = _scenario(gd, pokemon, account.trainer_level, scenario)
    cpm = gd.cpm(subject.level) if subject.level is not None else None
    ivs = subject.ivs
    rankings: dict[tuple[str, str], dict[str, Any]]
    if scenario_info is None:
        rankings = {
            (r.league, r.target_form_key): {
                "rank": r.rank,
                "percent": r.percent_of_best,
                "readiness": r.readiness,
                "species_rank": r.species_rank,
            }
            for r in session.scalars(select(PvpRanking).where(PvpRanking.pokemon_id == pokemon.id))
        }
    else:
        # The stored rankings describe the Pokémon as it is, so the purified one is calculated here.
        rules = rules_for(account)
        analysed = analyze_leagues(
            gd,
            subject,
            max_level=rules.max_level,
            include_best_buddy=rules.include_best_buddy,
            ready_cp_fraction=rules.ready_cp_fraction,
            elite_tm_available=rules.elite_tm_available,
        )
        rankings = {
            (league, t.target_key): {
                "rank": t.rank,
                "percent": t.percent,
                "readiness": t.readiness,
                "species_rank": t.species_rank,
            }
            for league, targets in analysed.items()
            for t in targets
        }
    paths = []
    for path in evolution_paths(gd.forms, pokemon.form_key):
        target = gd.forms.get(path.target_key)
        if target is None:
            continue
        base = base_stats_of(dict(target))
        cp_after = combat_power(base, ivs, cpm) if base and ivs and cpm else None
        hp_after = hit_points(base, ivs, cpm) if base and ivs and cpm else None
        leagues = {}
        for league in LEAGUES:
            cap = league_cap(gd, league)
            ranking = rankings.get((league, path.target_key)) or {}
            leagues[league] = {
                "rank": ranking.get("rank"),
                "percent": ranking.get("percent"),
                "readiness": ranking.get("readiness"),
                "over_cap": cap is not None and cp_after is not None and cp_after > cap,
                "species_rank": ranking.get("species_rank"),
            }
        moves_note = [*target.get("elite_charged", []), *target.get("elite_fast", [])]
        paths.append(
            {
                "target_key": path.target_key,
                "target_name": f"{target['name']} ({target['label']})" if target.get("label") else target["name"],
                "types": target.get("types", []),
                "steps": [asdict(s) for s in path.steps],
                "total_candy": path_candy(path.steps, purified=subject.purified),
                "cp_after": cp_after,
                "hp_after": hp_after,
                "leagues": leagues,
                "elite_moves": moves_note,
                "note": None if cp_after is not None else CP_AFTER_UNKNOWN,
            }
        )
    return {"available": True, "game_data_version": gd.version_id, "scenario": scenario_info, "paths": paths}


@router.get("/{pokemon_id}/powerups", response_model=dict[str, Any])
def pokemon_powerups(
    pokemon_id: int,
    target_level: float | None = Query(default=None, ge=1, le=60),
    scenario: Scenario = "current",
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    pokemon = owned_pokemon(session, auth.user, pokemon_id)
    account = owned_account(session, auth.user, pokemon.trainer_account_id)
    gd = container.gamedata.active()
    if gd is None or pokemon.level is None or pokemon.form_key is None:
        return {"available": False, "reason": _text("NO_GAME_DATA_OR_LEVEL", "Geen Game Data of level onbekend.")}
    rules = rules_for(account)
    form = gd.forms[pokemon.form_key]
    base = base_stats_of(dict(form))
    subject, scenario_info = _scenario(gd, pokemon, account.trainer_level, scenario)
    ivs = subject.ivs
    ceiling = reachable_max_level(gd.mechanics, account.trainer_level, best_buddy=rules.include_best_buddy)
    shadow, purified = subject.shadow, subject.purified
    start = subject.level if subject.level is not None else pokemon.level
    steps = []
    level = start
    for target in gd.levels(start + 0.5, ceiling):
        cost = power_up_cost(gd.mechanics, level, target, shadow=shadow, purified=purified, lucky=bool(pokemon.lucky))
        cpm = gd.cpm(target)
        steps.append(
            {
                "level": target,
                "cp": combat_power(base, ivs, cpm) if base and ivs and cpm else None,
                "cost": asdict(cost) if cost else None,
            }
        )
    chosen = None
    if target_level is not None:
        cost = power_up_cost(
            gd.mechanics,
            start,
            target_level,
            shadow=shadow,
            purified=purified,
            lucky=bool(pokemon.lucky),
        )
        cpm = gd.cpm(target_level)
        chosen = {
            "level": target_level,
            "cp": combat_power(base, ivs, cpm) if base and ivs and cpm else None,
            "cost": asdict(cost) if cost else None,
        }
    return {
        "available": True,
        "current": {"level": start, "cp": scenario_info["cp"] if scenario_info else pokemon.cp},
        "scenario": scenario_info,
        "max_level": ceiling,
        "modifiers": {"shadow": shadow, "purified": purified, "lucky": bool(pokemon.lucky)},
        "note": CANDY_ROUNDING,
        "steps": steps,
        "target": chosen,
        "candy_available": None,
    }


@router.get("/{pokemon_id}/history", response_model=list[dict[str, Any]])
def pokemon_history(
    pokemon_id: int,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    pokemon = owned_pokemon(session, auth.user, pokemon_id)
    events = session.execute(
        select(PokemonChangeEvent, SyncRun.applied_at)
        .join(SyncRun, SyncRun.id == PokemonChangeEvent.sync_run_id)
        .where(PokemonChangeEvent.pokemon_id == pokemon.id)
        .order_by(PokemonChangeEvent.id.desc())
    ).all()
    return [
        {
            "id": e.id,
            "type": e.event_type,
            "sync_run_id": e.sync_run_id,
            "at": applied.isoformat(),
            "labels": change_labels(e.changes) if e.event_type == "CHANGED" else [],
            "changes": e.changes if e.event_type != "APPEARED" else {},
        }
        for e, applied in events
    ]


class MetadataPatch(BaseModel):
    protected: bool | None = None
    protection_reason: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)
    tags: list[str] | None = Field(default=None, max_length=30)
    planned_action: str | None = None
    planned_league: str | None = None
    priority: int | None = Field(default=None, ge=0, le=100)
    review_status: str | None = None
    override_status: str | None = None
    clear: list[str] = Field(default_factory=list)
    # Lifting the protection of a vintage Pokémon needs this explicit confirmation (ADR-0019).
    confirm_vintage_override: bool = False


def _metadata(session: Session, pokemon: Pokemon, now: Any) -> PokemonUserMetadata:
    metadata = session.get(PokemonUserMetadata, pokemon.id)
    if metadata is None:
        metadata = PokemonUserMetadata(
            pokemon_id=pokemon.id,
            trainer_account_id=pokemon.trainer_account_id,
            protected=False,
            tags=[],
            review_status="none",
            updated_at=now,
        )
        session.add(metadata)
    return metadata


def _validate_patch(body: MetadataPatch) -> None:
    if body.planned_action is not None and body.planned_action not in PLANNED_ACTIONS:
        raise ValidationFailedError("Onbekende geplande actie.", context="planned_action")
    if body.planned_league is not None and body.planned_league not in LEAGUE_IDS:
        raise ValidationFailedError("Onbekende league.", context="planned_league")
    if body.review_status is not None and body.review_status not in REVIEW_STATUSES:
        raise ValidationFailedError("Onbekende reviewstatus.", context="review_status")
    if body.override_status is not None and body.override_status not in OVERRIDE_STATUSES:
        raise ValidationFailedError("Onbekende status.", context="override_status")
    if body.tags is not None and any(len(t) > 40 or not t.strip() for t in body.tags):
        raise ValidationFailedError("Een tag heeft 1–40 tekens.", context="tag_length")


def apply_metadata(metadata: PokemonUserMetadata, body: MetadataPatch, now: Any) -> None:
    clearable = {
        "protection_reason",
        "notes",
        "planned_action",
        "planned_league",
        "priority",
        "override_status",
    }
    for name in body.clear:
        if name in clearable:
            setattr(metadata, name, None)
    for name in (
        "protected",
        "protection_reason",
        "notes",
        "planned_action",
        "planned_league",
        "priority",
        "review_status",
        "override_status",
    ):
        value = getattr(body, name)
        if value is not None:
            setattr(metadata, name, value)
    if body.override_status == "TRANSFER_CANDIDATE" and metadata.protected:
        raise ValidationFailedError(
            "Deze Pokémon is handmatig beschermd. Hef eerst de bescherming op.", code="PROTECTED"
        )
    if body.tags is not None:
        metadata.tags = sorted({t.strip() for t in body.tags})
    if body.review_status == "reviewed":
        metadata.last_reviewed_at = now
    metadata.updated_at = now


@router.patch("/{pokemon_id}/metadata", response_model=dict[str, Any])
def update_metadata(
    pokemon_id: int,
    body: MetadataPatch,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Changes OAK metadata only. Nothing is ever sent to the game."""
    _validate_patch(body)
    pokemon = owned_pokemon(session, auth.user, pokemon_id)
    year = vintage_year(pokemon.caught_year)
    if year is not None and body.override_status in VINTAGE_OVERRIDES and not body.confirm_vintage_override:
        raise ConflictError(
            f"Dit is een vintage Pokémon uit {year}. OAK beschermt vintage Pokémon altijd. "
            "Bevestig dat je de bescherming van deze ene Pokémon wilt opheffen.",
            code="VINTAGE_CONFIRMATION_REQUIRED",
            data={"year": year},
            details={"year": year},
        )
    now = container.clock.now()
    metadata = _metadata(session, pokemon, now)
    apply_metadata(metadata, body, now)
    session.commit()
    enqueue(container, "analysis", pokemon.trainer_account_id)
    return get_pokemon(pokemon_id, auth, session, container)


class BulkRequest(BaseModel):
    account_id: int
    ids: list[int] = Field(min_length=1, max_length=MAX_BULK)
    action: str
    value: str | None = None
    # Favorites and other Pokémon that need a confirmation, confirmed one by one.
    confirmed_ids: list[int] = Field(default_factory=list, max_length=MAX_BULK)


@router.post("/bulk", response_model=dict[str, Any])
def bulk_action(
    body: BulkRequest,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Bulk changes to OAK metadata (spec §9.5). Never a game action."""
    account = owned_account(session, auth.user, body.account_id)
    rows = session.scalars(
        select(Pokemon).where(Pokemon.trainer_account_id == account.id, Pokemon.id.in_(body.ids))
    ).all()
    if len(rows) != len(set(body.ids)):
        raise ValidationFailedError("Een of meer Pokémon horen niet bij dit account.", context="bulk_pokemon")
    now = container.clock.now()
    skipped: list[dict[str, Any]] = []
    needs_confirmation: list[dict[str, Any]] = []
    confirmed = set(body.confirmed_ids)
    transfer_actions = body.action == "transfer_candidate" or (
        body.action == "add_to_list" and (body.value or "cleanup") == "cleanup"
    )
    guard = guard_context(session, account, container.settings.tz)
    for pokemon in rows:
        metadata = _metadata(session, pokemon, now)
        confirmed_kinds: list[str] = []
        if transfer_actions:
            year = vintage_year(pokemon.caught_year)
            if year is not None:
                # Vintage Pokémon never enter a transfer list in bulk; only one by one, after the
                # protection was lifted with a confirmation.
                skipped.append({"pokemon_id": pokemon.id, "reason": f"Vintage {year}: nooit via een bulkactie"})
                continue
            check = check_transfer(pokemon, metadata, guard)
            if check.blocked:
                skipped.append({"pokemon_id": pokemon.id, "reason": check.blocked})
                continue
            if check.needs and pokemon.id not in confirmed:
                needs_confirmation.append(confirmation_item(pokemon, check))
                continue
            confirmed_kinds = check.confirmation
        if body.action == "protect":
            metadata.protected = True
            metadata.protection_reason = body.value or metadata.protection_reason
        elif body.action == "unprotect":
            metadata.protected = False
        elif body.action == "add_tag":
            if not body.value or len(body.value) > 40:
                raise ValidationFailedError("Geef een tag van 1–40 tekens.", context="bulk_tag")
            metadata.tags = sorted({*metadata.tags, body.value.strip()})
        elif body.action == "remove_tag":
            metadata.tags = [t for t in metadata.tags if t != body.value]
        elif body.action == "review":
            metadata.review_status = "to_review"
        elif body.action == "reviewed":
            metadata.review_status = "reviewed"
            metadata.last_reviewed_at = now
        elif body.action == "transfer_candidate":
            metadata.override_status = "TRANSFER_CANDIDATE"
        elif body.action == "clear_override":
            metadata.override_status = None
        elif body.action in ("add_to_list", "remove_from_list"):
            list_name = body.value or "cleanup"
            existing = session.scalars(
                select(PlannedAction).where(
                    PlannedAction.pokemon_id == pokemon.id, PlannedAction.list_name == list_name
                )
            ).first()
            if body.action == "add_to_list" and existing is None:
                session.add(
                    PlannedAction(
                        trainer_account_id=account.id,
                        pokemon_id=pokemon.id,
                        list_name=list_name,
                        action="transfer" if list_name == "cleanup" else "other",
                        status="open",
                        confirmed=confirmed_kinds,
                        created_at=now,
                        updated_at=now,
                    )
                )
            elif body.action == "add_to_list" and existing is not None:
                existing.confirmed = confirmed_kinds
                existing.updated_at = now
            elif body.action == "remove_from_list" and existing is not None:
                session.delete(existing)
            continue
        else:
            raise ValidationFailedError("Onbekende bulkactie.", context="bulk_action")
        metadata.updated_at = now
    session.commit()
    enqueue(container, "analysis", account.id)
    not_done = len(skipped) + len(needs_confirmation)
    return {
        "updated": len(rows) - not_done,
        "skipped": skipped,
        "skipped_protected": [item["pokemon_id"] for item in skipped],
        "needs_confirmation": needs_confirmation,
    }


class CompareRequest(BaseModel):
    ids: list[int] = Field(min_length=2, max_length=MAX_COMPARE)


@router.post("/compare", response_model=list[dict[str, Any]])
def compare(
    body: CompareRequest,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> list[dict[str, Any]]:
    result = []
    for pokemon_id in body.ids:
        detail = get_pokemon(pokemon_id, auth, session, container)
        rankings = session.scalars(select(PvpRanking).where(PvpRanking.pokemon_id == pokemon_id)).all()
        detail["rankings"] = [
            {
                "league": r.league,
                "target": r.target_name,
                "rank": r.rank,
                "percent": r.percent_of_best,
                "best_cp": r.best_cp,
                "readiness": r.readiness,
                "stardust": r.stardust_cost,
                "species_rank": r.species_rank,
            }
            for r in rankings
        ]
        result.append(detail)
    return result


def _csv_safe(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(CSV_INJECTION_PREFIXES):
        return "'" + value
    return value


@router.get("/export/csv")
def export_csv(
    query: BoxQuery = Depends(),
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> StreamingResponse:
    account = owned_account(session, auth.user, query.account_id)
    latest, first = sync_bounds(session, account.id)
    rows = session.execute(
        base_query().where(*_conditions(query, account.id, latest)).order_by(*order_by(query.sort))
    ).all()
    gd = container.gamedata.active()
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        [
            "oak_id",
            "pokemon_id",
            "soort",
            "vorm",
            "bijnaam",
            "cp",
            "level",
            "atk",
            "def",
            "sta",
            "iv_pct",
            "snelle_aanval",
            "geladen_aanval_1",
            "geladen_aanval_2",
            "shiny",
            "lucky",
            "shadow",
            "purified",
            "favoriet",
            "dynamax",
            "gevangen",
            "cleanup_status",
            "great_rang",
            "ultra_rang",
            "beschermd",
            "notities",
            "oak_tags",
        ]
    )
    for pokemon, meta, analysis in rows:
        s = summarize(pokemon, meta, analysis, gd, latest_sync_id=latest, first_sync_id=first)
        writer.writerow(
            [
                _csv_safe(v)
                for v in (
                    s.id,
                    s.source_pokemon_id,
                    s.species_name,
                    s.form_label,
                    s.nickname,
                    s.cp,
                    s.level,
                    s.iv_attack,
                    s.iv_defense,
                    s.iv_stamina,
                    s.iv_percent,
                    s.fast_move.name if s.fast_move else None,
                    s.charged_moves[0].name if s.charged_moves else None,
                    s.charged_moves[1].name if len(s.charged_moves) > 1 else None,
                    s.shiny,
                    s.lucky,
                    s.shadow,
                    s.purified,
                    s.favorite,
                    s.dynamax,
                    s.caught_at.date().isoformat() if s.caught_at else None,
                    s.cleanup.status if s.cleanup else None,
                    s.pvp["great"].rank,
                    s.pvp["ultra"].rank,
                    meta.protected if meta else False,
                    meta.notes if meta else None,
                    ",".join(meta.tags) if meta else None,
                )
            ]
        )
    data = "﻿" + buffer.getvalue()
    return StreamingResponse(
        iter([data]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="oak-pokemon.csv"'},
    )


class TagLabelIn(BaseModel):
    account_id: int
    tag_id: str = Field(pattern=r"^\d{1,20}$")
    label: str = Field(min_length=1, max_length=64)
    protects: bool = False


@router.put("/tags/labels", response_model=dict[str, Any])
def set_tag_label(
    body: TagLabelIn,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    account = owned_account(session, auth.user, body.account_id)
    row = session.get(TagLabel, (account.id, body.tag_id))
    if row is None:
        row = TagLabel(
            trainer_account_id=account.id,
            tag_id=body.tag_id,
            label=body.label,
            protects=body.protects,
        )
        session.add(row)
    else:
        row.label = body.label
        row.protects = body.protects
    session.commit()
    enqueue(container, "analysis", account.id)
    return {"tag_id": row.tag_id, "label": row.label, "protects": row.protects}


SummaryList = list[PokemonSummary]
