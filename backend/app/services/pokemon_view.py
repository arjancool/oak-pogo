"""Turning stored Pokémon rows into API output. Every big identifier leaves as a string."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.domain.pokemon import Alignment, BreadMode, catch_date_known, vintage_year
from app.gamedata.model import GameData
from app.models import Pokemon, PokemonAnalysis, PokemonUserMetadata
from app.schemas.common import UtcDatetime

IV_MAX = 15
MAX_MOVE_TYPE_NAMES = {1: "max_attack", 2: "max_guard", 3: "max_spirit"}


class MoveOut(BaseModel):
    id: int | None
    key: str | None
    name: str
    type: str | None
    kind: str | None


class MetadataOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    protected: bool
    protection_reason: str | None
    notes: str | None
    tags: list[str]
    planned_action: str | None
    planned_league: str | None
    priority: int | None
    review_status: str
    override_status: str | None
    last_reviewed_at: UtcDatetime | None
    updated_at: UtcDatetime


class CleanupOut(BaseModel):
    status: str
    priority: int
    confidence: str
    protection: list[str]
    summary: str | None
    battle_score: int | None = None
    keep_score: int | None = None


class LeagueSummary(BaseModel):
    rank: int | None = None
    percent: float | None = None


class PokemonSummary(BaseModel):
    id: int
    source_pokemon_id: str
    species_id: int
    species_name: str | None
    form_label: str | None
    form_name: str | None
    form_key: str | None
    form_resolution: str | None
    costume_id: int | None
    gender: int | None
    nickname: str | None
    cp: int | None
    hp: int | None
    max_hp: int | None
    level: float | None
    iv_attack: int | None
    iv_defense: int | None
    iv_stamina: int | None
    iv_percent: float | None
    types: list[str]
    pokemon_class: str | None
    family_id: str | None
    shiny: bool | None
    lucky: bool | None
    favorite: bool | None
    shadow: bool | None
    purified: bool | None
    dynamax: bool | None
    gigantamax: bool | None
    costume: bool | None
    location_card: int | None
    traded: bool
    hatched_from_egg: bool | None
    hundo: bool
    shundo: bool
    caught_at: UtcDatetime | None
    caught_year: int | None
    # The catch year when it is 2016–2019 (ADR-0019), otherwise None.
    vintage_year: int | None
    # False when the export has no usable catch date; OAK then never assumes it is new.
    catch_date_known: bool
    inventory_status: str
    first_seen_at: UtcDatetime
    last_changed_at: UtcDatetime
    disappeared_at: UtcDatetime | None
    fast_move: MoveOut | None
    charged_moves: list[MoveOut]
    second_move_unlocked: bool | None
    max_moves: list[dict[str, Any]]
    tag_ids: list[str]
    tag_labels: list[str]
    metadata: MetadataOut | None
    cleanup: CleanupOut | None
    pvp: dict[str, LeagueSummary]
    is_new: bool = False


def move_out(gd: GameData | None, move_id: int | None, key: str | None) -> MoveOut | None:
    if move_id is None and key is None:
        return None
    move: Mapping[str, Any] | None = gd.move(key) if gd and key else (gd.move_by_id(move_id) if gd else None)
    if move is None:
        return MoveOut(
            id=move_id,
            key=key,
            name=f"Aanval #{move_id}" if move_id else (key or "?"),
            type=None,
            kind=None,
        )
    return MoveOut(
        id=int(move["id"]),
        key=str(move["key"]),
        name=str(move["name"]),
        type=move.get("type"),
        kind=move.get("kind"),
    )


def _optional(value: int | None, wanted: int) -> bool | None:
    return None if value is None else value == wanted


def summarize(
    pokemon: Pokemon,
    metadata: PokemonUserMetadata | None,
    analysis: PokemonAnalysis | None,
    gd: GameData | None,
    *,
    tag_labels: Mapping[str, str] | None = None,
    latest_sync_id: int | None = None,
    first_sync_id: int | None = None,
) -> PokemonSummary:
    hundo = pokemon.iv_attack == IV_MAX and pokemon.iv_defense == IV_MAX and pokemon.iv_stamina == IV_MAX
    charged = [
        m
        for m in (
            move_out(gd, pokemon.move_charged_1, pokemon.move_charged_1_key),
            move_out(gd, pokemon.move_charged_2, pokemon.move_charged_2_key),
        )
        if m is not None
    ]
    labels = tag_labels or {}
    cleanup = None
    if analysis is not None:
        summary = analysis.reasons[0]["text"] if analysis.reasons else None
        cleanup = CleanupOut(
            status=analysis.status,
            priority=analysis.priority,
            confidence=analysis.confidence,
            protection=[r["text"] for r in analysis.protection_reasons],
            summary=summary,
            battle_score=analysis.battle_score,
            keep_score=analysis.keep_score,
        )
    return PokemonSummary(
        id=pokemon.id,
        source_pokemon_id=pokemon.source_pokemon_id,
        species_id=pokemon.species_id,
        species_name=pokemon.species_name,
        form_label=pokemon.form_label,
        form_name=pokemon.form_name,
        form_key=pokemon.form_key,
        form_resolution=pokemon.form_resolution,
        costume_id=pokemon.costume_id,
        gender=pokemon.gender,
        nickname=pokemon.nickname,
        cp=pokemon.cp,
        hp=pokemon.hp,
        max_hp=pokemon.max_hp,
        level=pokemon.level,
        iv_attack=pokemon.iv_attack,
        iv_defense=pokemon.iv_defense,
        iv_stamina=pokemon.iv_stamina,
        iv_percent=pokemon.iv_percent,
        types=[t for t in (pokemon.type_1, pokemon.type_2) if t],
        pokemon_class=pokemon.pokemon_class,
        family_id=pokemon.family_id,
        shiny=pokemon.shiny,
        lucky=pokemon.lucky,
        favorite=pokemon.favorite,
        shadow=_optional(pokemon.alignment, Alignment.SHADOW),
        purified=_optional(pokemon.alignment, Alignment.PURIFIED),
        dynamax=None if pokemon.bread_mode is None else pokemon.bread_mode in (BreadMode.DYNAMAX, BreadMode.GIGANTAMAX),
        gigantamax=_optional(pokemon.bread_mode, BreadMode.GIGANTAMAX),
        costume=None if pokemon.costume_id is None else pokemon.costume_id != 0,
        location_card=pokemon.location_card,
        traded=pokemon.traded_at is not None,
        hatched_from_egg=pokemon.hatched_from_egg,
        hundo=hundo,
        shundo=hundo and bool(pokemon.shiny),
        caught_at=pokemon.caught_at,
        caught_year=pokemon.caught_year,
        vintage_year=vintage_year(pokemon.caught_year),
        catch_date_known=catch_date_known(pokemon.caught_year),
        inventory_status=pokemon.inventory_status,
        first_seen_at=pokemon.first_seen_at,
        last_changed_at=pokemon.last_changed_at,
        disappeared_at=pokemon.disappeared_at,
        fast_move=move_out(gd, pokemon.move_fast, pokemon.move_fast_key),
        charged_moves=charged,
        second_move_unlocked=None if pokemon.move_charged_1 is None else pokemon.move_charged_2 is not None,
        max_moves=[
            {"type": MAX_MOVE_TYPE_NAMES.get(m["type"], f"type_{m['type']}"), "level": m["level"]}
            for m in pokemon.bread_moves
        ],
        tag_ids=list(pokemon.tag_ids),
        tag_labels=[labels[t] for t in pokemon.tag_ids if t in labels],
        metadata=MetadataOut.model_validate(metadata) if metadata else None,
        cleanup=cleanup,
        pvp={
            "great": LeagueSummary(rank=analysis.great_rank, percent=analysis.great_percent)
            if analysis
            else LeagueSummary(),
            "ultra": LeagueSummary(rank=analysis.ultra_rank, percent=analysis.ultra_percent)
            if analysis
            else LeagueSummary(),
            "master": LeagueSummary(percent=analysis.master_percent) if analysis else LeagueSummary(),
        },
        is_new=latest_sync_id is not None
        and pokemon.first_seen_sync_id == latest_sync_id
        and latest_sync_id != first_sync_id,
    )


def detail_extras(pokemon: Pokemon) -> dict[str, Any]:
    return {
        "height_m": pokemon.height_m,
        "weight_kg": pokemon.weight_kg,
        "size_class": pokemon.size_class,
        "pokeball": pokemon.pokeball,
        "origin_case": pokemon.origin_case,
        "origin_events": pokemon.origin_events,
        "limited_identifier": pokemon.limited_identifier,
        "traded_at": _iso(pokemon.traded_at),
        "from_fort": pokemon.from_fort,
        "buddy_km_walked": pokemon.buddy_km_walked,
        "buddy_candy_awarded": pokemon.buddy_candy_awarded,
        "battles_attacked": pokemon.battles_attacked,
        "battles_defended": pokemon.battles_defended,
        "num_upgrades": pokemon.num_upgrades,
        "has_mega_evolved": pokemon.has_mega_evolved,
        "mega_evolved_forms": pokemon.mega_evolved_forms,
        "temp_evolution": pokemon.temp_evolution,
        "purified_exclusive_move": pokemon.purified_exclusive_move,
        "cp_multiplier": pokemon.cp_multiplier,
        "additional_cp_multiplier": pokemon.additional_cp_multiplier,
        "form_id": pokemon.form_id,
        "bread_mode": pokemon.bread_mode,
        "extra": pokemon.extra,
        "last_seen_at": _iso(pokemon.last_seen_at),
        "derived_version_id": pokemon.derived_version_id,
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
