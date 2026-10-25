"""Configurable cleanup and analysis rules (spec §11.2, §18.3, ADR-0019).

Three kinds of settings live here and are kept apart on purpose:

* hard protections (``protect_*``): a Pokémon that matches one is always PROTECT, whatever
  its scores are. Vintage Pokémon (2016–2019) are protected by a fixed rule in the engine and
  cannot be switched off here;
* the weights of the keep score (``keep_*``), a number from 0 to 100;
* thresholds for the battle analysis and for turning a keep score into advice.

Favorites are deliberately not a hard protection. They add ``keep_points_favorite`` to the
keep score and can never be proposed for transfer without a review and an explicit
confirmation (ADR-0019).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, fields
from typing import Any

from app.core.errors import ValidationFailedError

ENGINE_VERSION = "cleanup-2.1"
SCORE_MAX = 100
MAX_KEEP_MIN = 10
MAX_EVENT_HOLD_DAYS = 60
IV_RANK_MAX = 4096


@dataclass(frozen=True, slots=True)
class CleanupRules:
    # --- hard protections -------------------------------------------------------------------
    protect_shiny: bool = True
    protect_lucky: bool = True
    protect_hundo: bool = True
    protect_location_card: bool = True
    protect_costume: bool = True
    protect_mythical: bool = True
    protect_legendary: bool = True
    protect_ultra_beast: bool = True
    protect_shadow: bool = True
    protect_purified: bool = False
    protect_dynamax: bool = True
    protect_gigantamax: bool = True
    protect_event: bool = True
    protect_nicknamed: bool = True
    protect_mega_progress: bool = True

    # --- roles and minimums -----------------------------------------------------------------
    keep_min_per_species: int = 1
    keep_best_great: bool = True
    keep_best_ultra: bool = True
    keep_best_master: bool = True
    keep_best_raid: bool = True

    # --- battle analysis --------------------------------------------------------------------
    # Species within this PvPoke league rank count as meta-relevant for that league.
    meta_rank_threshold: int = 150
    # Species up to this PvPoke rank count fully in the battle score; below it the weight drops
    # linearly to zero at ``meta_rank_threshold``.
    species_rank_full: int = 25
    # A Pokémon that would rank in this top of all attackers of a type has raid value; #1 counts
    # fully, the value drops linearly to zero just past this rank.
    raid_top_n: int = 25
    # IV rank (out of 4096) from which a non-best copy still goes to review instead of transfer.
    good_iv_rank_threshold: int = 100
    # Only the best copy with an IV rank at or below this value is advised as a BUILD
    # investment. A weaker best copy is kept, but not worth Stardust.
    build_iv_rank_threshold: int = 500
    # A Pokémon at or above this fraction of the league cap counts as directly usable.
    ready_cp_fraction: float = 0.95
    max_level: float = 50.0
    include_best_buddy: bool = False
    elite_tm_available: bool = False
    consider_costs: bool = True
    allow_transfer_on_partial_import: bool = False

    # --- events (ADR-0021) ------------------------------------------------------------------
    # Hold transfer candidates for an upcoming Community Day of their family, or an event the
    # user added, and give a tip before double Transfer Candy.
    use_events: bool = True
    # How many days ahead an event counts.
    event_hold_days: int = 14

    # --- keep score (0–100) -----------------------------------------------------------------
    # Share of the battle score that counts towards the keep score, in percent.
    keep_weight_battle: int = 45
    # The best copy of its species, form and Shadow status (or the only one).
    keep_points_best_copy: int = 20
    keep_points_favorite: int = 25
    keep_points_shiny: int = 15
    keep_points_lucky: int = 10
    keep_points_rarity: int = 10  # Legendary, Mythical, Ultra Beast
    keep_points_costume: int = 10
    keep_points_location_card: int = 10
    keep_points_event: int = 10
    keep_points_max: int = 10  # Dynamax or Gigantamax
    keep_points_mega: int = 5
    # Special traits together never add more than this.
    keep_traits_cap: int = 30
    keep_points_nickname: int = 5
    # An OAK plan for this Pokémon (keep, evolve, power up, TM, ...), not 'transfer'.
    keep_points_planned: int = 10
    # A keep score at or above this value means KEEP; between the two thresholds REVIEW.
    keep_threshold: int = 70
    review_threshold: int = 40

    def validate(self) -> CleanupRules:
        if not 0 <= self.keep_min_per_species <= MAX_KEEP_MIN:
            raise ValidationFailedError("keep_min_per_species moet tussen 0 en 10 liggen.")
        if not 0.5 <= self.ready_cp_fraction <= 1.0:
            raise ValidationFailedError("ready_cp_fraction moet tussen 0,5 en 1 liggen.")
        if min(self.meta_rank_threshold, self.good_iv_rank_threshold, self.raid_top_n, self.species_rank_full) < 1:
            raise ValidationFailedError("Drempels moeten positief zijn.")
        if self.species_rank_full > self.meta_rank_threshold:
            raise ValidationFailedError("species_rank_full mag niet boven meta_rank_threshold liggen.")
        if not 1 <= self.good_iv_rank_threshold <= IV_RANK_MAX or not 1 <= self.build_iv_rank_threshold <= IV_RANK_MAX:
            raise ValidationFailedError("Een IV-rang ligt tussen 1 en 4096.")
        if not 1 <= self.max_level <= 60:
            raise ValidationFailedError("max_level is ongeldig.")
        if not 0 <= self.event_hold_days <= MAX_EVENT_HOLD_DAYS:
            raise ValidationFailedError(f"event_hold_days moet tussen 0 en {MAX_EVENT_HOLD_DAYS} liggen.")
        for item in fields(self):
            if item.name.startswith("keep_points_") or item.name in (
                "keep_weight_battle",
                "keep_traits_cap",
                "keep_threshold",
                "review_threshold",
            ):
                value = getattr(self, item.name)
                if not 0 <= value <= SCORE_MAX:
                    raise ValidationFailedError(f"{item.name} moet tussen 0 en 100 liggen.")
        if self.review_threshold > self.keep_threshold:
            raise ValidationFailedError("De reviewdrempel mag niet boven de bewaardrempel liggen.")
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CleanupRules:
        """Unknown keys are ignored. That is how settings of an older engine version, such as
        the removed ``protect_favorites`` and ``protect_before_year``, stop having effect."""
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in (data or {}).items() if k in known}
        try:
            return cls(**values).validate()
        except TypeError as exc:
            raise ValidationFailedError("Ongeldige regelinstellingen.") from exc
