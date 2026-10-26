"""Every sentence the battle pages, the Pokémon analysis and the Pokédex get from the server has a
text in the interface catalog (ADR-0025).

Like the cleanup reasons (tests/test_server_texts.py), these sentences carry a code with data and
the Dutch text. The interface builds the sentence from frontend/src/i18n and falls back to the Dutch
text when a code is missing there. This test makes sure no code is missing, and that the catalog's
Dutch is the server's Dutch for every sentence without values in it.
"""

from __future__ import annotations

import itertools
import json
import re
from pathlib import Path
from typing import Any

from app.analysis.league import _readiness
from app.api.v1 import battles as battles_api
from app.api.v1 import pokedex, pokemon
from app.services import battles, gyms

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "frontend" / "src" / "i18n" / "nl.json"
APP = ROOT / "backend" / "app"
GROUPS = {
    "battles": ("services/battles.py", "services/gyms.py", "api/v1/battles.py"),
    "readiness": ("analysis/league.py",),
    "analysis": ("analysis/purify.py", "api/v1/pokemon.py"),
    "pokedex": ("api/v1/pokedex.py",),
}
CODE = re.compile(r'(?:_text|_reason)\(\s*"([A-Z][A-Z_]+)"|"code": "([A-Z][A-Z_]+)"')
SUFFIX = re.compile(r"_(one|other|[a-z]+(?:_[a-z]+)*)$")


def _server() -> dict[str, dict[str, str]]:
    return json.loads(CATALOG.read_text(encoding="utf-8"))["server"]


def _codes(group: str) -> set[str]:
    codes: set[str] = set()
    for name in GROUPS[group]:
        source = (APP / name).read_text(encoding="utf-8")
        codes |= {next(g for g in match.groups() if g) for match in CODE.finditer(source)}
    return codes


def test_every_code_has_an_interface_text() -> None:
    server = _server()
    total = 0
    for group in GROUPS:
        codes = _codes(group)
        total += len(codes)
        known = {SUFFIX.sub("", key) for key in server.get(group, {})}
        missing = sorted(codes - known)
        assert not missing, f"add these codes under 'server.{group}' in {CATALOG.relative_to(ROOT)}: {missing}"
    assert total > 45, "the pattern still finds the codes"


def _fixed_texts() -> list[tuple[str, dict[str, Any]]]:
    """Sentences without values, as the server sends them."""
    leagues = [
        battles_api.league_method({"kind": kind, "ranked_species": ranked})
        for kind, ranked in (("league", 10), ("cup", 10), ("cup", None))
    ]
    readiness = [
        _readiness(cap, 1400, 20.0, cp, level, evolution, 0.95)[1]
        for cap, cp, level, evolution in itertools.product(
            (1500, None), (None, 1000, 1390, 1600), (None, 15.0, 25.0), (False, True)
        )
    ]
    variants = [label for _mode, label in battles.TEAM_VARIANTS]
    return [
        *(("battles", text) for text in (*leagues, *variants, *battles.MAX_NOTES, *gyms.NOTES)),
        *(
            ("battles", text)
            for text in (
                battles.TEAM_METHOD,
                battles_api.RAID_METHOD,
                battles_api.ROCKET_METHOD,
                battles_api.ROCKET_LINEUP_NOTE,
                battles_api.MAX_METHOD,
                gyms.METHOD,
                gyms.OUTDATED,
                gyms.SOURCE,
            )
        ),
        *(("readiness", text) for text in readiness),
        *(("analysis", text) for text in pokemon.ANALYSIS_METHOD.values()),
        ("analysis", pokemon.CP_AFTER_UNKNOWN),
        ("analysis", pokemon.CANDY_ROUNDING),
        *(("pokedex", label) for _level, label in pokedex.CP_LEVELS if "data" not in label),
    ]


def test_fixed_sentences_match_the_catalog() -> None:
    server = _server()
    texts = _fixed_texts()
    assert {text["code"] for group, text in texts if group == "readiness"} == _codes("readiness")
    for group, text in texts:
        context = text.get("data", {}).get("context")
        key = f"{text['code']}_{context}" if context else text["code"]
        assert server[group].get(key) == text["text"], f"server.{group}.{key}"
