"""The user's best gym defenders, one per species, ranked by bulk (docs/ANALYSIS_ENGINE.md).

Whether a Pokémon may defend a gym comes from the Game Data (``isDeployable``), never from a list
in the code. A dataset built before that field was read says so instead of guessing.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.gym import defender_bulk, defender_value, effective_defense
from app.analysis.stats import IVs, base_stats_of, hit_points
from app.domain.pokemon import IV_MAX, Alignment
from app.gamedata.model import GameData
from app.models import Pokemon
from app.recommendations.cleanup import Confidence

MAX_DEFENDERS = 20
METHOD = (
    "Verdedigingswaarde = effectieve Defense × HP, vergeleken met de sterkst mogelijke verdediger uit de Game "
    "Data. Hoe hoger, hoe meer aanvallen een aanvaller nodig heeft. De eigen aanvallen van de verdediger en het "
    "verlies van motivatie tellen niet mee."
)
NOTES = [
    "Of een Pokémon in een gym mag, komt uit de Game Data (isDeployable). Legendary, Mythical en Ultra Beasts mogen "
    "meestal niet, maar de Game Data maakt uitzonderingen, zoals Meltan en Melmetal.",
    "Iedere soort mag maar één keer in dezelfde gym. Daarom staat per soort alleen je sterkste exemplaar in de lijst.",
    "Hoe snel een verdediger motivatie verliest, staat niet in de Game Data. Volgens metingen uit de community gaat "
    "dat sneller bij een hogere CP. OAK rekent daar niet mee.",
    "Staat een Pokémon al in een gym, dan zie je dat bij de laatste import. Zo'n Pokémon kun je niet nog een keer "
    "plaatsen. OAK leest dat uit de export. Of PGSharp het altijd meestuurt, is nog niet vastgesteld.",
    "Kies bij voorkeur een type dat de andere verdedigers in de gym nog niet hebben.",
]
OUTDATED = "De actieve Game Data zegt nog niet welke Pokémon in een gym mogen. Werk de Game Data bij."


def _label(form: Mapping[str, Any]) -> str:
    return f"{form['name']} ({form['label']})" if form.get("label") else str(form["name"])


def _confidence(pokemon: Pokemon) -> Confidence:
    if pokemon.form_resolution in ("exact", "base"):
        return Confidence.HIGH
    if pokemon.form_resolution == "fallback_default_form":
        return Confidence.LOW
    return Confidence.MEDIUM


def _move_name(gd: GameData, key: str | None) -> str | None:
    return str((gd.move(key) or {}).get("name", key)) if key else None


def _reference(gd: GameData) -> tuple[float, str | None] | None:
    """The bulk of the strongest form allowed in a gym, at the highest normal level with perfect IVs."""
    if any(form.get("deployable") is None for form in gd.forms.values()):
        return None
    cpm = gd.cpm(gd.max_level)
    best, name = 0.0, None
    if cpm is None:
        return best, name
    full = IVs(IV_MAX, IV_MAX, IV_MAX)
    for form in gd.forms.values():
        base = base_stats_of(dict(form)) if form.get("deployable") else None
        if base is None:
            continue
        bulk = defender_bulk(base, full, cpm)
        if bulk > best:
            best, name = bulk, _label(form)
    return best, name


def gym_defenders(session: Session, gd: GameData, account_id: int, limit: int = MAX_DEFENDERS) -> dict[str, Any]:
    result: dict[str, Any] = {
        "defenders": [],
        "excluded": {},
        "reference": None,
        "unknown_reason": None,
        "method": METHOD,
        "notes": NOTES,
        "source": "PGSharp-export en Game Data",
        "game_data_version": gd.version_id,
    }
    reference = _reference(gd)
    if reference is None:
        result["unknown_reason"] = OUTDATED
        return result
    reference_bulk, reference_name = reference
    result["reference"] = {"name": reference_name, "level": gd.max_level}
    shadow_defense = float(gd.mechanics.get("pve", {}).get("shadow_defense") or 1.0)

    excluded: Counter[str] = Counter()
    best: dict[int, dict[str, Any]] = {}
    count: Counter[int] = Counter()
    rows = session.scalars(
        select(Pokemon).where(Pokemon.trainer_account_id == account_id, Pokemon.inventory_status == "in_inventory")
    ).all()
    for pokemon in rows:
        form = gd.forms.get(pokemon.form_key or "")
        if form is None:
            excluded["unknown_form"] += 1
            continue
        if not form.get("deployable"):
            excluded["not_deployable"] += 1
            continue
        base = base_stats_of(dict(form))
        cpm = gd.cpm(pokemon.level) if pokemon.level is not None else None
        if base is None or cpm is None or pokemon.iv_defense is None or pokemon.iv_stamina is None:
            excluded["unknown_stats"] += 1
            continue
        shadow = pokemon.alignment == Alignment.SHADOW
        multiplier = shadow_defense if shadow else 1.0
        ivs = IVs(pokemon.iv_attack or 0, pokemon.iv_defense, pokemon.iv_stamina)
        bulk = defender_bulk(base, ivs, cpm, multiplier)
        value = defender_value(bulk, reference_bulk)
        hp = hit_points(base, ivs, cpm)
        defense = effective_defense(base, ivs, cpm, multiplier)
        reasons = [
            "Mag in een gym volgens de Game Data.",
            f"{hp} HP en een effectieve Defense van {defense:.0f}.",
            f"Verdedigingswaarde {value} van 100. Op 100 staat {reference_name} op level {gd.max_level:g} met "
            "perfecte IV's.",
        ]
        if shadow:
            reasons.append(
                f"Shadow: Defense × {shadow_defense:.2f} volgens de Game Data, dus minder stevig dan zonder Shadow."
            )
        dex = form["dex"]
        count[dex] += 1
        item = {
            "pokemon_id": pokemon.id,
            "name": pokemon.species_name,
            "form_label": pokemon.form_label,
            "species_id": dex,
            "shadow": shadow,
            "cp": pokemon.cp,
            "level": pokemon.level,
            "types": list(form.get("types", [])),
            "hp": hp,
            "defense": round(defense, 1),
            "bulk": round(bulk),
            "value": value,
            "fast_move": _move_name(gd, pokemon.move_fast_key),
            "charged_moves": [
                name
                for name in (_move_name(gd, pokemon.move_charged_1_key), _move_name(gd, pokemon.move_charged_2_key))
                if name
            ],
            "reasons": reasons,
            "in_gym": pokemon.in_gym,
            "confidence": _confidence(pokemon).value,
        }
        if dex not in best or bulk > best[dex]["bulk"]:
            best[dex] = item
    ranked = sorted(best.values(), key=lambda i: (-i["bulk"], -(i["cp"] or 0)))[:limit]
    for item in ranked:
        item["same_species"] = count[item["species_id"]] - 1
    result["defenders"] = ranked
    result["excluded"] = dict(excluded)
    return result
