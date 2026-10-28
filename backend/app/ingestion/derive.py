"""Derived Pokémon columns (ADR-0015 projection).

Recomputed after every import and whenever another Game Data version becomes active, so a
newer dataset can interpret forms, moves and levels the previous one did not know.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

from app.domain.pokemon import iv_percent
from app.gamedata.model import GameData
from app.models import Pokemon

# Raised when stored derived columns may be wrong and must be recomputed once for every Pokémon.
# 2: a catch date corrected by a later import did not update the catch year (audit F01).
# 3: a form the Game Master marks as a costume counts as a costume (costume_form).
DERIVE_REVISION = 3


def apply_derived(row: Pokemon, gd: GameData | None, tz: ZoneInfo) -> None:
    row.iv_percent = iv_percent(row.iv_attack, row.iv_defense, row.iv_stamina)
    row.caught_year = row.caught_at.astimezone(tz).year if row.caught_at else None
    if gd is None:
        row.derived_version_id = None
        return
    resolution = gd.resolve_form(row.species_id, row.form_name)
    form = resolution.form
    record = gd.species_record(row.species_id)
    row.form_resolution = resolution.status
    row.costume_form = gd.is_costume_form(row.species_id, row.form_name)
    row.species_key = record["key"] if record else None
    row.species_name = (form or {}).get("name") or (record["name"] if record else None)
    row.form_key = form["key"] if form else None
    row.form_label = form.get("label") if form and resolution.status == "exact" else None
    types = form.get("types", []) if form else []
    row.type_1 = types[0] if types else None
    row.type_2 = types[1] if len(types) > 1 else None
    row.pokemon_class = form.get("class") if form else None
    row.family_id = form.get("family") if form else None
    total_cpm = None
    if row.cp_multiplier is not None:
        total_cpm = row.cp_multiplier + (row.additional_cp_multiplier or 0.0)
    row.level = gd.level_for_cpm(total_cpm)
    row.move_fast_key = _move_key(gd, row.move_fast)
    row.move_charged_1_key = _move_key(gd, row.move_charged_1)
    row.move_charged_2_key = _move_key(gd, row.move_charged_2)
    row.derived_version_id = gd.version_id


def _move_key(gd: GameData, move_id: int | None) -> str | None:
    move = gd.move_by_id(move_id)
    return str(move["key"]) if move else None
