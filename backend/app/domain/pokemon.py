"""Normalized, source-independent representation of a PGSharp export.

Pure domain code: no I/O, no framework imports. ``None`` always means *the export did not
carry this value*; it never stands in for ``False`` or ``0``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any

IV_MAX = 15
IV_COMBINED_MAX = IV_MAX * 3
# Pokémon GO launched in July 2016. A catch date before that is a data error, not a fact.
FIRST_GAME_YEAR = 2016
# Pokémon caught in these years are 'vintage': hard protected, never a regular transfer
# candidate (ADR-0019). This is a fixed policy, not a game mechanic.
VINTAGE_FIRST_YEAR = FIRST_GAME_YEAR
VINTAGE_LAST_YEAR = 2019


class Alignment(IntEnum):
    NONE = 0
    SHADOW = 1
    PURIFIED = 2


class Gender(IntEnum):
    UNSET = 0
    MALE = 1
    FEMALE = 2
    GENDERLESS = 3


class BreadMode(IntEnum):
    """PGSharp ``pokemonDisplay.breadModeEnum``. 'Bread' is the game's code name for Max Battles.

    Verified in a real export: 0 for regular Pokémon, 1 for Dynamax Pokémon. Value 2 for
    Gigantamax follows the community protocol definitions and is not yet verified.
    """

    NONE = 0
    DYNAMAX = 1
    GIGANTAMAX = 2


class PokemonSize(IntEnum):
    """PGSharp ``size``: the size class the game shows, from XXS to XXL.

    Verified in a real export: a Pokémon with 1 is the one the game called XXS, and most
    Pokémon have 3. The order of the other values follows the community protocol definitions.
    0 means the export did not say.
    """

    UNSET = 0
    XXS = 1
    XS = 2
    M = 3
    XL = 4
    XXL = 5


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class Issue:
    severity: Severity
    code: str
    message: str
    path: str | None = None
    source_pokemon_id: str | None = None
    # The values in the message, so the interface can show it in another language (ADR-0025).
    # "context" names the variant when one code has more than one message.
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MaxMove:
    move_type: int
    level: int


@dataclass(slots=True)
class NormalizedPokemon:
    source_pokemon_id: str
    species_id: int
    form_id: int | None = None
    form_name: str | None = None
    costume_id: int | None = None
    gender: int | None = None
    shiny: bool | None = None
    alignment: int | None = None
    lucky: bool | None = None
    favorite: bool | None = None
    cp: int | None = None
    hp: int | None = None
    max_hp: int | None = None
    iv_attack: int | None = None
    iv_defense: int | None = None
    iv_stamina: int | None = None
    cp_multiplier: float | None = None
    additional_cp_multiplier: float | None = None
    move_fast: int | None = None
    move_charged_1: int | None = None
    move_charged_2: int | None = None
    num_upgrades: int | None = None
    height_m: float | None = None
    weight_kg: float | None = None
    size_class: int | None = None
    pokeball: int | None = None
    caught_at: datetime | None = None
    traded_at: datetime | None = None
    hatched_from_egg: bool | None = None
    # Whether it defends a gym right now. Only this fact is kept, never which gym or where.
    in_gym: bool | None = None
    from_fort: bool | None = None
    origin_case: int | None = None
    origin_events: list[str] = field(default_factory=list)
    location_card: int | None = None
    bread_mode: int | None = None
    bread_moves: list[dict[str, int]] = field(default_factory=list)
    has_mega_evolved: bool | None = None
    mega_evolved_forms: list[int] = field(default_factory=list)
    temp_evolution: int | None = None
    nickname: str | None = None
    buddy_km_walked: float | None = None
    buddy_candy_awarded: int | None = None
    battles_attacked: int | None = None
    battles_defended: int | None = None
    purified_exclusive_move: bool | None = None
    limited_identifier: str | None = None
    tag_ids: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def iv_percent(self) -> float | None:
        return iv_percent(self.iv_attack, self.iv_defense, self.iv_stamina)

    @property
    def total_cp_multiplier(self) -> float | None:
        if self.cp_multiplier is None:
            return None
        return self.cp_multiplier + (self.additional_cp_multiplier or 0.0)


@dataclass(slots=True)
class TrainerSnapshot:
    nickname: str | None = None
    level: int | None = None
    experience: int | None = None
    stardust: int | None = None
    pokecoins: int | None = None
    team: int | None = None
    max_pokemon_storage: int | None = None
    max_item_storage: int | None = None
    stats: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ItemCount:
    item_id: int
    name: str | None
    count: int


@dataclass(slots=True)
class NormalizedExport:
    export_time: datetime | None
    export_time_raw: str | None
    trainer: TrainerSnapshot
    pokemon: list[NormalizedPokemon]
    items: list[ItemCount]
    eggs: int
    has_pokemon_list: bool
    has_items_list: bool
    has_account: bool
    has_player: bool
    pokemon_records: int
    # Records present in the export whose ID could not be read. Their absence from the result
    # makes the export unusable as proof that a missing Pokémon is gone.
    unidentifiable_records: int
    # Records with a readable ID but unreadable content. They prove presence, not state.
    unreadable_records: list[str]
    issues: list[Issue]


def iv_percent(attack: int | None, defense: int | None, stamina: int | None) -> float | None:
    if attack is None or defense is None or stamina is None:
        return None
    return round((attack + defense + stamina) / IV_COMBINED_MAX * 100, 1)


def is_hundo(attack: int | None, defense: int | None, stamina: int | None) -> bool:
    return attack == IV_MAX and defense == IV_MAX and stamina == IV_MAX


def catch_date_known(caught_year: int | None) -> bool:
    """False when the export has no usable catch date. OAK then never assumes the Pokémon is new."""
    return caught_year is not None and caught_year >= FIRST_GAME_YEAR


def has_costume(costume_id: int | None, costume_form: bool | None) -> bool | None:
    """A costume from the export's costume field, or a form the Game Master marks as a costume.

    None when neither says anything, so OAK never reads an unknown value as 'no costume'.
    """
    if (costume_id is not None and costume_id != 0) or costume_form:
        return True
    if costume_id is None and costume_form is None:
        return None
    return False


def extreme_size(size_class: int | None) -> str | None:
    """'xxs' or 'xxl' for the two rare sizes, otherwise None, also when the size is unknown."""
    if size_class == PokemonSize.XXS:
        return "xxs"
    if size_class == PokemonSize.XXL:
        return "xxl"
    return None


def vintage_year(caught_year: int | None) -> int | None:
    """The catch year when the Pokémon is vintage (2016–2019), otherwise None."""
    if caught_year is not None and VINTAGE_FIRST_YEAR <= caught_year <= VINTAGE_LAST_YEAR:
        return caught_year
    return None
