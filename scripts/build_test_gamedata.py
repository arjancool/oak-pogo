"""Extract a small, representative subset of the upstream Game Master sources for tests.

Usage:
    python scripts/build_test_gamedata.py <pokeminers latest.json> <pvpoke gamemaster.json> \
        <rankings-1500.json> <rankings-2500.json> <rankings-10000.json> <fantasy rankings-1500.json>

Writes fixtures/gamedata/*.json. The subset keeps every global template OAK reads, the
species below with all their forms, the moves they reference and their PvPoke entries, and the
cups in ``CUPS`` with their format and the Fantasy Cup ranking (ADR-0027).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DEX = sorted({
    1, 2, 3, 4, 5, 6, 7, 8, 9, 19, 20, 25, 26, 52, 53, 66, 67, 68, 129, 130, 133, 134, 135, 136, 147, 148, 149,
    150, 151, 183, 184, 194, 195, 196, 197, 298, 302, 307, 308, 351, 379, 382, 470, 471, 700, 793, 831, 832,
    863, 888, 980,
})
GLOBAL_TEMPLATES = (
    "PLAYER_LEVEL_SETTINGS", "POKEMON_UPGRADE_SETTINGS", "LUCKY_POKEMON_SETTINGS", "BATTLE_SETTINGS",
    "COMBAT_SETTINGS", "COMBAT_LEAGUE_DEFAULT_GREAT", "COMBAT_LEAGUE_DEFAULT_ULTRA", "COMBAT_LEAGUE_DEFAULT_MASTER",
    "BREAD_MOVE_MAPPING_SETTINGS", "SOURDOUGH_MOVE_MAPPING_SETTINGS",
)
OUT = Path(__file__).resolve().parents[1] / "fixtures" / "gamedata"
# One cup with a type filter and one with an evolution filter and a level cap.
CUPS = (("fantasy", 1500), ("little", 500))


def ranking_subset(data: list[dict], pv_ids: set[str]) -> list[dict]:
    """Keep the real rank positions: entries outside the subset are replaced by placeholders."""
    subset = [r if r["speciesId"] in pv_ids else {"speciesId": f"_other_{i}"} for i, r in enumerate(data)]
    last = max((i for i, r in enumerate(subset) if not r["speciesId"].startswith("_other_")), default=0)
    return [
        {k: r[k] for k in ("speciesId", "score", "moveset", "moves", "scores") if k in r}
        for r in subset[: last + 1]
    ]


def cup_subset(pvpoke: dict) -> dict:
    names = {name for name, _cp in CUPS}
    return {
        "cups": [c for c in pvpoke["cups"] if c["name"] in names],
        "formats": [f for f in pvpoke["formats"] if (f["cup"], f["cp"]) in CUPS and f.get("showFormat")],
        "greatLeagueIneligible": pvpoke["greatLeagueIneligible"],
    }


def main(argv: list[str]) -> None:
    pokeminers, pvpoke, *rankings, fantasy = (json.loads(Path(p).read_text()) for p in argv[1:7])
    keep_species: set[str] = set()
    selected = []
    move_refs: set[str] = set()
    for entry in pokeminers:
        tid = entry["templateId"]
        match = re.match(r"^V(\d{4})_POKEMON_", tid)
        if match and int(match.group(1)) in DEX and "pokemonSettings" in entry["data"]:
            settings = entry["data"]["pokemonSettings"]
            keep_species.add(settings["pokemonId"])
            for key in ("quickMoves", "cinematicMoves", "eliteQuickMove", "eliteCinematicMove"):
                move_refs.update(m for m in settings.get(key, []) or [] if isinstance(m, str))
            shadow = settings.get("shadow") or {}
            move_refs.update(v for v in (shadow.get("shadowChargeMove"), shadow.get("purifiedChargeMove")) if v)
            selected.append(entry)
    move_refs.update({"FRUSTRATION", "RETURN"})
    for entry in pokeminers:
        tid = entry["templateId"]
        data = entry["data"]
        if tid in GLOBAL_TEMPLATES or "typeEffective" in data or "breadMoveLevelSettings" in data or "itemSettings" in data:
            selected.append(entry)
        elif re.match(r"^VN_BM_\d+$", tid):  # Max and G-Max moves
            selected.append(entry)
        elif re.match(r"^(COMBAT_)?V\d{4}_MOVE_", tid):
            move = (data.get("moveSettings") or {}).get("movementId") or (data.get("combatMove") or {}).get("uniqueId")
            if move in move_refs:
                selected.append(entry)
        elif tid.startswith("FORMS_V") and int(tid[7:11]) in DEX:
            selected.append(entry)
    pv_pokemon = [p for p in pvpoke["pokemon"] if p["dex"] in DEX]
    pv_ids = {p["speciesId"] for p in pv_pokemon}
    pv_moves = {m for p in pv_pokemon for m in (*p.get("fastMoves", []), *p.get("chargedMoves", []))}
    pv_subset = {
        "timestamp": pvpoke["timestamp"], "id": pvpoke["id"], "title": pvpoke["title"],
        "pokemon": pv_pokemon, "moves": [m for m in pvpoke["moves"] if m["moveId"] in pv_moves],
        **cup_subset(pvpoke),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pokeminers-subset.json").write_text(json.dumps(selected, separators=(",", ":")))
    (OUT / "pvpoke-subset.json").write_text(json.dumps(pv_subset, separators=(",", ":")))
    for name, data in (*zip(("great", "ultra", "master"), rankings, strict=True), ("fantasy-1500", fantasy)):
        trimmed = ranking_subset(data, pv_ids)
        (OUT / f"pvpoke-rankings-{name}-subset.json").write_text(json.dumps(trimmed, separators=(",", ":")))
    print(f"templates={len(selected)} pvpoke={len(pv_pokemon)}")


if __name__ == "__main__":
    main(sys.argv)
