"""What the cleanup engine knows about one Pokémon. Built by the analysis service."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.analysis.gym import GymPotential
from app.analysis.league import LeagueTarget
from app.analysis.raid import RaidPotential
from app.domain.pokemon import IV_MAX, catch_date_known, vintage_year


@dataclass(slots=True)
class PokemonView:
    id: int
    name: str
    group_key: str | None
    cp: int | None
    level: float | None
    iv_attack: int | None
    iv_defense: int | None
    iv_stamina: int | None
    iv_percent: float | None
    caught_year: int | None
    species_class: str | None = None
    # Evolution family from the Game Data, such as FAMILY_PAWNIARD. Used for event rules.
    family: str | None = None
    favorite: bool = False
    shiny: bool = False
    lucky: bool = False
    shadow: bool = False
    purified: bool = False
    costume: bool = False
    location_card: bool = False
    dynamax: bool = False
    gigantamax: bool = False
    event: bool = False
    nicknamed: bool = False
    mega_progress: bool = False
    traded: bool = False
    form_resolution: str | None = None
    manual_protected: bool = False
    manual_reason: str | None = None
    override_status: str | None = None
    review_requested: bool = False
    planned_action: str | None = None
    protecting_tags: list[str] = field(default_factory=list)
    # Current move keys (fast first). Needed to recognise legacy moves the Pokémon already has.
    moves: list[str] = field(default_factory=list)
    leagues: dict[str, list[LeagueTarget]] = field(default_factory=dict)
    primary: dict[str, LeagueTarget | None] = field(default_factory=dict)
    raid: RaidPotential | None = None
    gym: GymPotential | None = None
    # Defends a gym right now, so it cannot be transferred until it returns.
    in_gym: bool = False

    @property
    def has_ivs(self) -> bool:
        return None not in (self.iv_attack, self.iv_defense, self.iv_stamina)

    @property
    def hundo(self) -> bool:
        return self.iv_attack == IV_MAX and self.iv_defense == IV_MAX and self.iv_stamina == IV_MAX

    @property
    def vintage_year(self) -> int | None:
        return vintage_year(self.caught_year)

    @property
    def catch_date_known(self) -> bool:
        return catch_date_known(self.caught_year)
