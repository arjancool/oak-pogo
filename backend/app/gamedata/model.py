"""Read-only view on an active dataset. Pure code, safe to share between threads."""

from __future__ import annotations

import bisect
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.gamedata.transform import TRANSFORM_REVISION, form_key, norm_key

# PGSharp's cpMultiplier is a float32. A level matches when the stored value is within this
# distance of the table value.
CPM_TOLERANCE = 1e-4


@dataclass(frozen=True, slots=True)
class FormResolution:
    form: Mapping[str, Any] | None
    status: str  # exact | base | fallback_default_form | unknown_species


class GameData:
    def __init__(self, dataset: Mapping[str, Any], version_id: int) -> None:
        self.dataset = dataset
        self.version_id = version_id
        self.forms: Mapping[str, Mapping[str, Any]] = dataset["forms"]
        self.species: Mapping[str, Mapping[str, Any]] = dataset["species"]
        self.moves: Mapping[str, Mapping[str, Any]] = dataset["moves"]
        self._move_ids: Mapping[str, str] = dataset["move_ids"]
        mechanics = dataset["mechanics"]
        self.mechanics: Mapping[str, Any] = mechanics
        self._cpm_levels = [float(row[0]) for row in mechanics["cpm"]]
        self._cpm_values = [float(row[1]) for row in mechanics["cpm"]]
        self._cpm_by_level = dict(zip(self._cpm_levels, self._cpm_values, strict=True))
        self.type_chart: Mapping[str, Mapping[str, float]] = dataset["type_chart"]
        self.leagues: dict[str, Mapping[str, Any]] = {lg["id"]: lg for lg in dataset["leagues"]}
        self.cups: dict[str, Mapping[str, Any]] = {cup["id"]: cup for cup in dataset.get("cups", [])}
        self._cup_species = {cup_id: frozenset(cup["eligible"]) for cup_id, cup in self.cups.items()}
        self.rankings: Mapping[str, Any] = dataset.get("rankings", {})
        self.items: Mapping[str, Mapping[str, Any]] = dataset.get("items", {})
        self._name_to_dex = {record["key"]: int(dex) for dex, record in self.species.items()}
        # Per species the forms the Game Master marks as a costume (isCostume), as comparison keys.
        self._costume_forms = {
            int(dex): frozenset(
                norm_key(name)
                for key in record.get("forms", [])
                for name in self.forms.get(key, {}).get("costume_forms", [])
            )
            for dex, record in self.species.items()
        }
        self.gmax_moves: Mapping[str, list[Mapping[str, Any]]] | None = dataset.get("bread", {}).get("gmax_moves")

    @property
    def outdated(self) -> bool:
        """Built by an older transform: valid, but without data a newer revision adds."""
        return int(self.dataset.get("transform_revision", 1)) < TRANSFORM_REVISION

    # --- levels ---------------------------------------------------------------------------------

    @property
    def max_level(self) -> float:
        return float(self.mechanics["max_normal_level"])

    @property
    def best_buddy_bonus(self) -> float:
        return float(self.mechanics.get("best_buddy_bonus_levels") or 0)

    def cpm(self, level: float) -> float | None:
        return self._cpm_by_level.get(float(level))

    def levels(self, minimum: float, maximum: float) -> list[float]:
        return [lv for lv in self._cpm_levels if minimum <= lv <= maximum]

    def level_for_cpm(self, total_cpm: float | None) -> float | None:
        if total_cpm is None or total_cpm <= 0:
            return None
        index = bisect.bisect_left(self._cpm_values, total_cpm - CPM_TOLERANCE)
        for candidate in (index - 1, index, index + 1):
            if 0 <= candidate < len(self._cpm_values) and abs(self._cpm_values[candidate] - total_cpm) <= CPM_TOLERANCE:
                return self._cpm_levels[candidate]
        return None

    # --- species, forms, moves ------------------------------------------------------------------

    def dex_for_name(self, species_key: str) -> int | None:
        return self._name_to_dex.get(species_key)

    def species_record(self, dex: int) -> Mapping[str, Any] | None:
        return self.species.get(str(dex))

    def resolve_form(self, dex: int, form_name: str | None) -> FormResolution:
        """Map PGSharp's ``(pokemonId, formName)`` to a dataset form.

        ``formName`` ``Unset``/``None`` maps to the base template. A form the dataset does not
        know (for example a costume released after the dataset was built) falls back to the
        species' default form, and says so in ``status`` so the UI and the cleanup engine can
        treat the result as less certain.
        """
        record = self.species_record(dex)
        if record is None:
            return FormResolution(None, "unknown_species")
        if not form_name:
            base = self.forms.get(form_key(dex, None))
            if base is not None:
                return FormResolution(base, "base")
            return FormResolution(self._default_form(dex, record), "base")
        exact = self.forms.get(f"{dex}:{norm_key(form_name)}")
        if exact is not None:
            return FormResolution(exact, "exact")
        return FormResolution(self._default_form(dex, record), "fallback_default_form")

    def is_costume_form(self, dex: int, form_name: str | None) -> bool:
        """True when the Game Master marks this form as a costume.

        PGSharp does not always fill the costume field for such a Pokémon, for example a Pikachu
        with a hat from an event. The form name says it as well.
        """
        return bool(form_name) and norm_key(form_name) in self._costume_forms.get(dex, frozenset())

    def _default_form(self, dex: int, record: Mapping[str, Any]) -> Mapping[str, Any] | None:
        normal = self.forms.get(f"{dex}:{norm_key(record['key'])}NORMAL")
        if normal is not None:
            return normal
        base = self.forms.get(form_key(dex, None))
        if base is not None:
            return base
        keys = record.get("forms", [])
        return self.forms.get(keys[0]) if keys else None

    def move_by_id(self, move_id: int | None) -> Mapping[str, Any] | None:
        if move_id is None:
            return None
        key = self._move_ids.get(str(move_id))
        return self.moves.get(key) if key else None

    def move(self, key: str | None) -> Mapping[str, Any] | None:
        return self.moves.get(key) if key else None

    def gmax_move(self, dex: int | None, key: str | None) -> Mapping[str, Any] | None:
        """The fixed G-Max move of a Gigantamax Pokémon, by dataset form key (``6:``).

        A mapping without a form holds for every form of the species. The base form and the
        ``<SPECIES>NORMAL`` form are the same Pokémon.
        """
        if dex is None or not self.gmax_moves:
            return None
        form = (key or "").partition(":")[2]
        record = self.species_record(dex)
        normal = f"{norm_key(record['key'])}NORMAL" if record else None
        wanted = {form, normal} if form in ("", normal) else {form}
        entries = self.gmax_moves.get(str(dex), [])
        for entry in entries:
            if entry.get("form") in wanted:
                return entry
        return next((entry for entry in entries if entry.get("form") is None), None)

    def effectiveness(self, attack_type: str, defender_types: list[str]) -> float:
        row = self.type_chart.get(attack_type, {})
        result = 1.0
        for defender in defender_types:
            result *= row.get(defender, 1.0)
        return result

    def cup_allows(self, cup_id: str, form: Mapping[str, Any], *, shadow: bool) -> bool | None:
        """Whether this form may enter the cup. ``None`` when PvPoke does not know the form, so
        the rules cannot be applied to it (ADR-0027)."""
        species = self._cup_species.get(cup_id)
        pvpoke_id = form.get("pvpoke_id")
        if species is None or not pvpoke_id:
            return None
        return f"{pvpoke_id}_shadow" in species if shadow else pvpoke_id in species

    def ranking(self, league: str, pvpoke_id: str | None, *, shadow: bool = False) -> Mapping[str, Any] | None:
        if not pvpoke_id:
            return None
        table = self.rankings.get(league, {}).get("entries", {})
        if shadow:
            entry = table.get(f"{pvpoke_id}_shadow")
            if entry is not None:
                return entry
        return table.get(pvpoke_id)

    def item(self, pgsharp_name: str | None) -> Mapping[str, Any] | None:
        if not pgsharp_name:
            return None
        return self.items.get(norm_key(pgsharp_name))
