"""Pokédex: any species from the active Game Data, with what the own collection can do with it.

Everything about the species comes from the active dataset. The collection part only reads the
trainer account the user asks for, and only advises: nothing here changes the game.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.evolution import EvolutionStep, evolution_paths, path_candy
from app.analysis.gym import gym_potential
from app.analysis.league import LEAGUES, league_cap
from app.analysis.pokedex import (
    evolves_from,
    paths_into,
    same_pokemon,
    search_species,
    shown_key,
    species_forms,
)
from app.analysis.stats import IVs, base_stats_of, combat_power, hit_points
from app.api.deps import AuthContext, get_auth, get_container, get_session, owned_account
from app.api.v1.account_data import ITEM_NAMES
from app.api.v1.pokemon import sync_bounds, tag_label_map
from app.core.container import Container
from app.core.errors import NotFoundError, ServiceUnavailableError
from app.domain.pokemon import IV_MAX, Alignment
from app.gamedata.model import GameData
from app.gamedata.transform import norm_key
from app.models import ItemInventory, ManualResource, Pokemon, PokemonAnalysis, PokemonUserMetadata, TrainerAccount
from app.services.pokemon_view import summarize

router = APIRouter(prefix="/pokedex", tags=["pokedex"])


def _text(code: str, text: str, **data: Any) -> dict[str, Any]:
    """A label for the interface: a code with its data, and the Dutch text as fallback (ADR-0025)."""
    return {"code": code, "text": text, **({"data": data} if data else {})}


def _level_label(level: float) -> dict[str, Any]:
    return _text("LEVEL", f"Level {level:g}", level=level)


# Levels for the CP table with perfect IVs: research and raids, the same with weather boost,
# the old level cap, and the dataset's maximum.
CP_LEVELS = (
    (20.0, _text("RAID_RESEARCH", "Raid en onderzoek")),
    (25.0, _text("WEATHER_BOOST", "Met weerbonus")),
    (40.0, _level_label(40.0)),
)
OWNED_LIMIT = 50
CANDIDATE_LIMIT = 100
ITEM_LABELS = {norm_key(name): label for name, (label, _group) in ITEM_NAMES.items()}


def _gd(container: Container) -> GameData:
    gd = container.gamedata.active()
    if gd is None:
        raise ServiceUnavailableError(
            "Geen actieve Game Data. Werk de Game Data bij onder Beheer.", code="NO_GAME_DATA"
        )
    return gd


def _form_label(form: Mapping[str, Any]) -> str:
    return f"{form['name']} ({form['label']})" if form.get("label") else str(form["name"])


def _item_label(item: str | None) -> str | None:
    if not item:
        return None
    key = norm_key(item.removeprefix("ITEM_"))
    return ITEM_LABELS.get(key) or item.removeprefix("ITEM_").replace("_", " ").title()


def _step(step: EvolutionStep, gd: GameData) -> dict[str, Any]:
    target = gd.forms.get(step.to_key)
    return {
        **asdict(step),
        "to_name": _form_label(target) if target else step.to_key,
        "item_name": _item_label(step.item),
        "lure_name": _item_label(step.lure),
    }


def _moves(gd: GameData, form: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    legacy = set(form.get("legacy_moves", []))
    result: dict[str, list[dict[str, Any]]] = {"fast": [], "charged": []}
    pools = (
        ("fast", form.get("fast_moves", []), False),
        ("charged", form.get("charged_moves", []), False),
        ("fast", form.get("elite_fast", []), True),
        ("charged", form.get("elite_charged", []), True),
    )
    seen: set[str] = set()
    for kind, keys, elite in pools:
        for key in keys:
            if key in seen:
                continue
            seen.add(key)
            move = gd.move(key)
            result[kind].append(
                {
                    "key": key,
                    "name": move["name"] if move else key,
                    "type": move["type"] if move else None,
                    "elite": elite,
                    "legacy": key in legacy,
                }
            )
    for key in sorted(legacy - seen):
        move = gd.move(key)
        if move is not None:
            result[move["kind"]].append(
                {"key": key, "name": move["name"], "type": move["type"], "elite": False, "legacy": True}
            )
    return result


def _cp_table(gd: GameData, form: Mapping[str, Any]) -> list[dict[str, Any]]:
    base = base_stats_of(dict(form))
    if base is None:
        return []
    perfect = IVs(IV_MAX, IV_MAX, IV_MAX)
    rows = []
    for level, label in (*CP_LEVELS, (gd.max_level, _level_label(gd.max_level))):
        cpm = gd.cpm(level)
        if cpm is None or any(r["level"] == level for r in rows):
            continue
        rows.append({"level": level, "label": label, "cp": combat_power(base, perfect, cpm)})
    return rows


def _leagues(gd: GameData, form: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = []
    for league in LEAGUES:
        entry = gd.ranking(league, form.get("pvpoke_id"))
        shadow = gd.ranking(league, form.get("pvpoke_id"), shadow=True)
        result.append(
            {
                "league": league,
                "name": gd.leagues.get(league, {}).get("name", league),
                "max_cp": league_cap(gd, league),
                "species_rank": entry.get("rank") if entry else None,
                "shadow_rank": shadow.get("rank") if shadow and shadow is not entry else None,
                "moveset": [(gd.move(m) or {}).get("name", m) for m in entry.get("moveset", [])] if entry else [],
            }
        )
    return result


def _gym(gd: GameData, key: str) -> dict[str, Any] | None:
    potential = gym_potential(gd, key, IV_MAX, IV_MAX, level=gd.max_level, shadow=False)
    if potential is None:
        return None
    return {
        "rank": potential.rank,
        "target_key": potential.target_key,
        "target_name": potential.target_name,
        "is_evolution": potential.is_evolution,
    }


def _form_info(gd: GameData, key: str, form: Mapping[str, Any]) -> dict[str, Any]:
    shadow = form.get("shadow")
    return {
        "key": key,
        "name": _form_label(form),
        "label": form.get("label"),
        "types": form.get("types", []),
        "stats": form.get("stats"),
        "class": form.get("class"),
        "family": form.get("family"),
        "deployable": form.get("deployable"),
        "tradable": form.get("tradable"),
        "transferable": form.get("transferable"),
        "buddy_km": form.get("buddy_km"),
        "third_move": form.get("third_move"),
        "shadow": {"purify_stardust": shadow.get("purify_stardust"), "purify_candy": shadow.get("purify_candy")}
        if shadow
        else None,
        "mega": [m["id"].removeprefix("TEMP_EVOLUTION_").replace("_", " ").title() for m in form.get("mega", [])],
    }


def _item_counts(session: Session, account_id: int) -> dict[str, int] | None:
    rows = session.scalars(select(ItemInventory).where(ItemInventory.trainer_account_id == account_id)).all()
    if not rows:
        return None  # no item bag imported yet: unknown, not zero
    return {norm_key(r.item_name or ""): r.count for r in rows if r.item_name}


def _collection(session: Session, gd: GameData, account: TrainerAccount, dex: int, key: str) -> dict[str, Any]:
    in_inventory = (Pokemon.trainer_account_id == account.id, Pokemon.inventory_status == "in_inventory")
    latest, first = sync_bounds(session, account.id)
    labels = tag_label_map(session, account.id)

    def rows(*conditions: Any, order: Any, limit: int) -> list[Any]:
        stmt = (
            select(Pokemon, PokemonUserMetadata, PokemonAnalysis)
            .outerjoin(PokemonUserMetadata, PokemonUserMetadata.pokemon_id == Pokemon.id)
            .outerjoin(PokemonAnalysis, PokemonAnalysis.pokemon_id == Pokemon.id)
            .where(*in_inventory, *conditions)
            .order_by(*order, Pokemon.id)
            .limit(limit)
        )
        return list(session.execute(stmt).all())

    def summary(pokemon: Pokemon, meta: Any, analysis: Any) -> dict[str, Any]:
        return summarize(
            pokemon, meta, analysis, gd, tag_labels=labels, latest_sync_id=latest, first_sync_id=first
        ).model_dump(mode="json")

    same_form = same_pokemon(gd, key)
    owned_total = session.scalar(select(func.count()).where(*in_inventory, Pokemon.species_id == dex)) or 0
    owned = [
        {**summary(p, m, a), "same_form": p.form_key in same_form}
        for p, m, a in rows(Pokemon.species_id == dex, order=[Pokemon.cp.desc()], limit=OWNED_LIMIT)
    ]

    starts = paths_into(gd, key)
    items = _item_counts(session, account.id)
    target = gd.forms[key]
    base = base_stats_of(dict(target))
    candidates = []
    for pokemon, meta, analysis in rows(Pokemon.form_key.in_(list(starts)), order=[], limit=10_000):
        path = starts[pokemon.form_key][0]
        ivs = (
            IVs(pokemon.iv_attack, pokemon.iv_defense, pokemon.iv_stamina)
            if None not in (pokemon.iv_attack, pokemon.iv_defense, pokemon.iv_stamina)
            else None
        )
        cpm = gd.cpm(pokemon.level) if pokemon.level is not None else None
        steps = []
        for step in path.steps:
            info = _step(step, gd)
            if step.item:
                info["item_have"] = None if items is None else items.get(norm_key(step.item.removeprefix("ITEM_")), 0)
            steps.append(info)
        candidates.append(
            {
                "pokemon": summary(pokemon, meta, analysis),
                "steps": steps,
                "total_candy": path_candy(path.steps, purified=pokemon.alignment == Alignment.PURIFIED),
                "cp_after": combat_power(base, ivs, cpm) if base and ivs and cpm else None,
                "hp_after": hit_points(base, ivs, cpm) if base and ivs and cpm else None,
            }
        )
    candidates.sort(key=lambda c: (c["cp_after"] is None, -(c["cp_after"] or 0), c["pokemon"]["id"]))

    family = target.get("family")
    candy = session.get(ManualResource, (account.id, "candy", family)) if isinstance(family, str) else None
    return {
        "account_id": account.id,
        "owned_total": owned_total,
        "owned": owned,
        "candidate_total": len(candidates),
        "candidates": candidates[:CANDIDATE_LIMIT],
        "candy": {"family": family, "quantity": candy.quantity if candy else None},
        "items_known": items is not None,
    }


@router.get("/search", response_model=dict[str, Any])
def search(
    q: str = Query(min_length=1, max_length=40),
    auth: AuthContext = Depends(get_auth),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    gd = _gd(container)
    return {"game_data_version": gd.version_id, "results": [asdict(hit) for hit in search_species(gd, q)]}


@router.get("/{dex}", response_model=dict[str, Any])
def species(
    dex: int,
    form: str | None = Query(default=None, max_length=80),
    account_id: int | None = None,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    gd = _gd(container)
    record = gd.species_record(dex)
    if record is None:
        raise NotFoundError("Deze Pokémon staat niet in de actieve Game Data.", context="species")
    keys = species_forms(gd, dex)
    key = shown_key(gd, form) if form else (keys[0] if keys else None)
    if key is None or key not in keys:
        raise NotFoundError("Deze vorm staat niet in de actieve Game Data.", context="form")
    data = gd.forms[key]
    direct = [p for p in evolution_paths(gd.forms, key) if len(p.steps) == 1]
    result: dict[str, Any] = {
        "game_data_version": gd.version_id,
        "dex": dex,
        "name": record["name"],
        "forms": [{"key": k, "name": _form_label(gd.forms[k])} for k in keys],
        "form": _form_info(gd, key, data),
        "moves": _moves(gd, data),
        "cp_table": _cp_table(gd, data),
        "leagues": _leagues(gd, data),
        "gym": _gym(gd, key),
        "evolves_from": [
            {"key": k, "dex": gd.forms[k]["dex"], "name": _form_label(gd.forms[k])} for k in evolves_from(gd, key)
        ],
        "evolves_to": [
            {**_step(p.steps[0], gd), "dex": gd.forms[p.target_key]["dex"]} for p in direct if p.target_key in gd.forms
        ],
        "collection": None,
    }
    if account_id is not None:
        account = owned_account(session, auth.user, account_id)
        result["collection"] = _collection(session, gd, account, dex, key)
    return result
