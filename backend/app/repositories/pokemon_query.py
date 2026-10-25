"""Translating Box filters and the search syntax into SQL. Every query is scoped to one trainer
account; callers have already checked that the user owns it (ADR-0016)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Select,
    String,
    and_,
    exists,
    func,
    not_,
    or_,
    select,
    type_coerce,
)
from sqlalchemy.orm import aliased

from app.domain.pokemon import FIRST_GAME_YEAR, VINTAGE_FIRST_YEAR, VINTAGE_LAST_YEAR, Alignment, BreadMode
from app.domain.query import Term
from app.models import Pokemon, PokemonAnalysis, PokemonUserMetadata, SyncRun

IV_MAX = 15
SORTS: dict[str, Any] = {
    "cp": Pokemon.cp,
    "name": Pokemon.species_name,
    "dex": Pokemon.species_id,
    "iv": Pokemon.iv_percent,
    "atk": Pokemon.iv_attack,
    "def": Pokemon.iv_defense,
    "sta": Pokemon.iv_stamina,
    "level": Pokemon.level,
    "caught": Pokemon.caught_at,
    "changed": Pokemon.last_changed_at,
    "seen": Pokemon.first_seen_at,
    "great": PokemonAnalysis.great_rank,
    "ultra": PokemonAnalysis.ultra_rank,
    "master": PokemonAnalysis.master_percent,
    "cleanup": PokemonAnalysis.priority,
    "battle": PokemonAnalysis.battle_score,
    "keep": PokemonAnalysis.keep_score,
}
NUMERIC_COLUMNS: dict[str, Any] = {
    "cp": Pokemon.cp,
    "max_hp": Pokemon.max_hp,
    "iv_percent": Pokemon.iv_percent,
    "iv_attack": Pokemon.iv_attack,
    "iv_defense": Pokemon.iv_defense,
    "iv_stamina": Pokemon.iv_stamina,
    "level": Pokemon.level,
    "caught_year": Pokemon.caught_year,
    "species_id": Pokemon.species_id,
    "great_rank": PokemonAnalysis.great_rank,
    "ultra_rank": PokemonAnalysis.ultra_rank,
    "battle": PokemonAnalysis.battle_score,
    "keep": PokemonAnalysis.keep_score,
}


@dataclass(slots=True)
class BoxFilters:
    status: str = "in_inventory"  # in_inventory | not_in_inventory | all
    species: list[int] = field(default_factory=list)
    cp_min: int | None = None
    cp_max: int | None = None
    iv_min: float | None = None
    iv_max: float | None = None
    level_min: float | None = None
    level_max: float | None = None
    years: list[int] = field(default_factory=list)
    flags: dict[str, bool] = field(default_factory=dict)
    cleanup_status: list[str] = field(default_factory=list)
    league: str | None = None  # great | ultra | master: suitable in that league
    move: str | None = None
    family: str | None = None
    type: str | None = None
    tag: str | None = None
    planned_action: str | None = None


def flag_condition(flag: str, account_id: int, latest_sync_id: int | None) -> ColumnElement[bool]:
    hundo = and_(Pokemon.iv_attack == IV_MAX, Pokemon.iv_defense == IV_MAX, Pokemon.iv_stamina == IV_MAX)
    if flag == "shiny":
        return Pokemon.shiny.is_(True)
    if flag == "lucky":
        return Pokemon.lucky.is_(True)
    if flag == "shadow":
        return Pokemon.alignment == Alignment.SHADOW
    if flag == "purified":
        return Pokemon.alignment == Alignment.PURIFIED
    if flag == "favorite":
        return Pokemon.favorite.is_(True)
    if flag == "legendary":
        return Pokemon.pokemon_class == "legendary"
    if flag == "mythical":
        return Pokemon.pokemon_class == "mythical"
    if flag == "ultrabeast":
        return Pokemon.pokemon_class == "ultra_beast"
    if flag == "dynamax":
        return Pokemon.bread_mode.in_((BreadMode.DYNAMAX, BreadMode.GIGANTAMAX))
    if flag == "gigantamax":
        return Pokemon.bread_mode == BreadMode.GIGANTAMAX
    if flag == "costume":
        return and_(Pokemon.costume_id.is_not(None), Pokemon.costume_id != 0)
    if flag == "background":
        return Pokemon.location_card.is_not(None)
    if flag == "hundo":
        return hundo
    if flag == "shundo":
        return and_(hundo, Pokemon.shiny.is_(True))
    if flag == "nundo":
        return and_(Pokemon.iv_attack == 0, Pokemon.iv_defense == 0, Pokemon.iv_stamina == 0)
    if flag == "traded":
        return Pokemon.traded_at.is_not(None)
    if flag == "egg_hatched":
        return Pokemon.hatched_from_egg.is_(True)
    if flag == "nicknamed":
        return Pokemon.nickname.is_not(None)
    if flag == "mega":
        return Pokemon.has_mega_evolved.is_(True)
    if flag == "buddy":
        return Pokemon.buddy_km_walked > 0
    if flag == "vintage":
        return and_(Pokemon.caught_year >= VINTAGE_FIRST_YEAR, Pokemon.caught_year <= VINTAGE_LAST_YEAR)
    if flag == "unknown_date":
        return or_(Pokemon.caught_year.is_(None), Pokemon.caught_year < FIRST_GAME_YEAR)
    if flag == "missing":
        return Pokemon.inventory_status == "not_in_inventory"
    if flag == "untagged":
        return or_(_text(Pokemon.tag_ids) == "[]", Pokemon.tag_ids.is_(None))
    if flag == "protected":
        return or_(PokemonUserMetadata.protected.is_(True), PokemonAnalysis.status == "PROTECT")
    if flag == "new":
        if latest_sync_id is None:
            return Pokemon.id < 0
        return and_(Pokemon.first_seen_sync_id == latest_sync_id, _has_previous_sync(latest_sync_id))
    if flag == "duplicate":
        other = aliased(Pokemon)
        return exists(
            select(other.id).where(
                other.trainer_account_id == account_id,
                other.inventory_status == "in_inventory",
                other.id != Pokemon.id,
                func.coalesce(other.form_key, type_coerce(other.species_id, String))
                == func.coalesce(Pokemon.form_key, type_coerce(Pokemon.species_id, String)),
                func.coalesce(other.alignment, 0) == func.coalesce(Pokemon.alignment, 0),
            )
        )
    msg = f"unknown flag {flag}"
    raise ValueError(msg)


def _text(column: Any) -> Any:
    """JSON columns compared as their stored text, bypassing the JSON bind processor."""
    return type_coerce(column, String)


def _has_previous_sync(latest_sync_id: int) -> ColumnElement[bool]:
    return exists(select(SyncRun.id).where(SyncRun.id == latest_sync_id, SyncRun.previous_sync_run_id.is_not(None)))


def _numeric(column: Any, term: Term) -> ColumnElement[bool]:
    if term.op == "range":
        low, high = term.value  # type: ignore[misc]
        return and_(column >= low, column <= high)
    value = term.value
    if term.op == ">":
        return column > value
    if term.op == ">=":
        return column >= value
    if term.op == "<":
        return column < value
    if term.op == "<=":
        return column <= value
    return column == value


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def term_condition(term: Term, account_id: int, latest_sync_id: int | None) -> ColumnElement[bool]:
    if term.kind == "numeric":
        condition = _numeric(NUMERIC_COLUMNS[term.field], term)
    elif term.kind == "flag":
        condition = flag_condition(term.field, account_id, latest_sync_id)
    elif term.kind == "ivs":
        a, d, s = term.value  # type: ignore[misc]
        condition = and_(Pokemon.iv_attack == a, Pokemon.iv_defense == d, Pokemon.iv_stamina == s)
    elif term.kind == "text":
        pattern = f"%{_escape_like(str(term.value)).replace(' ', '_')}%"
        if term.field == "move":
            condition = or_(
                Pokemon.move_fast_key.ilike(pattern, escape="\\"),
                Pokemon.move_charged_1_key.ilike(pattern, escape="\\"),
                Pokemon.move_charged_2_key.ilike(pattern, escape="\\"),
            )
        elif term.field == "family":
            condition = Pokemon.family_id.ilike(pattern, escape="\\")
        elif term.field == "type":
            value = str(term.value)
            condition = or_(Pokemon.type_1 == value, Pokemon.type_2 == value)
        elif term.field == "tag":
            condition = or_(
                _text(Pokemon.tag_ids).like(f'%"{_escape_like(str(term.value))}"%', escape="\\"),
                _text(PokemonUserMetadata.tags).ilike(f'%"{_escape_like(str(term.value))}%', escape="\\"),
            )
        elif term.field == "status":
            condition = PokemonAnalysis.status == str(term.value).upper().replace(" ", "_")
        elif term.field == "league":
            column = {"great": PokemonAnalysis.great_rank, "ultra": PokemonAnalysis.ultra_rank}.get(str(term.value))
            condition = column.is_not(None) if column is not None else PokemonAnalysis.master_percent.is_not(None)
        elif term.field == "form":
            condition = or_(
                Pokemon.form_label.ilike(f"%{_escape_like(str(term.value))}%", escape="\\"),
                Pokemon.form_name.ilike(f"%{_escape_like(str(term.value))}%", escape="\\"),
            )
        else:  # name
            value = f"%{_escape_like(str(term.value))}%"
            condition = or_(
                Pokemon.species_name.ilike(value, escape="\\"),
                Pokemon.nickname.ilike(value, escape="\\"),
            )
    else:  # free text
        value = f"%{_escape_like(str(term.value))}%"
        condition = or_(
            Pokemon.species_name.ilike(value, escape="\\"),
            Pokemon.nickname.ilike(value, escape="\\"),
            Pokemon.form_label.ilike(value, escape="\\"),
        )
    return not_(condition) if term.negate else condition


def filter_conditions(filters: BoxFilters, account_id: int, latest_sync_id: int | None) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Pokemon.trainer_account_id == account_id]
    if filters.status != "all":
        conditions.append(Pokemon.inventory_status == filters.status)
    if filters.species:
        conditions.append(Pokemon.species_id.in_(filters.species))
    for column, low, high in (
        (Pokemon.cp, filters.cp_min, filters.cp_max),
        (Pokemon.iv_percent, filters.iv_min, filters.iv_max),
        (Pokemon.level, filters.level_min, filters.level_max),
    ):
        if low is not None:
            conditions.append(column >= low)
        if high is not None:
            conditions.append(column <= high)
    if filters.years:
        conditions.append(Pokemon.caught_year.in_(filters.years))
    for flag, wanted in filters.flags.items():
        condition = flag_condition(flag, account_id, latest_sync_id)
        conditions.append(condition if wanted else not_(condition))
    if filters.cleanup_status:
        conditions.append(PokemonAnalysis.status.in_(filters.cleanup_status))
    if filters.league == "great":
        conditions.append(PokemonAnalysis.great_rank.is_not(None))
    elif filters.league == "ultra":
        conditions.append(PokemonAnalysis.ultra_rank.is_not(None))
    elif filters.league == "master":
        conditions.append(PokemonAnalysis.master_percent.is_not(None))
    for term_field, value in (
        ("move", filters.move),
        ("family", filters.family),
        ("type", filters.type),
        ("tag", filters.tag),
    ):
        if value:
            conditions.append(
                term_condition(Term("text", term_field, "contains", value.lower()), account_id, latest_sync_id)
            )
    if filters.planned_action:
        conditions.append(PokemonUserMetadata.planned_action == filters.planned_action)
    return conditions


def base_query() -> Select[Pokemon, PokemonUserMetadata, PokemonAnalysis]:
    return (
        select(Pokemon, PokemonUserMetadata, PokemonAnalysis)
        .outerjoin(PokemonUserMetadata, PokemonUserMetadata.pokemon_id == Pokemon.id)
        .outerjoin(PokemonAnalysis, PokemonAnalysis.pokemon_id == Pokemon.id)
    )


def order_by(sort: str) -> list[Any]:
    descending = sort.startswith("-")
    key = sort.lstrip("-")
    column = SORTS.get(key, Pokemon.cp)
    # Ranks: a lower number is better, so 'best first' is ascending. Nulls always last.
    expression = column.desc() if descending else column.asc()
    return [column.is_(None), expression, Pokemon.id]
