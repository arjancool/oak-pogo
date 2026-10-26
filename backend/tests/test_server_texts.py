"""Every sentence the cleanup engine builds has a text in the interface catalog (ADR-0025).

The engine sends a code with data and a Dutch sentence. The interface builds the sentence in the
chosen language from frontend/src/i18n, and falls back to the Dutch sentence when a code is
missing there. This test makes sure no code is missing, so English users never get Dutch for it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "frontend" / "src" / "i18n" / "nl.json"
ENGINE = ROOT / "backend" / "app" / "recommendations"
GROUPS = ("reasons", "warnings", "protections", "parts", "differences", "traits", "species", "notes")
CODE_CALL = re.compile(r'(?:_reason|_part|_text)\(\s*"([A-Z][A-Z_]+)"|"code": "([A-Z][A-Z_]+)"|\("([A-Z][A-Z_]+)", "')
ROLE = re.compile(r'"role": "(best_\w+|minimum)"')


def engine_codes() -> set[str]:
    codes: set[str] = set()
    for path in ENGINE.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        codes |= {next(g for g in match.groups() if g) for match in CODE_CALL.finditer(source)}
        codes |= {role.upper() for role in ROLE.findall(source)}
    return codes


def catalog_codes() -> set[str]:
    server = json.loads(CATALOG.read_text(encoding="utf-8"))["server"]
    found: set[str] = set()
    for group in GROUPS:
        for key in server.get(group, {}):
            found.add(re.sub(r"_(one|other|[a-z]+(?:_[a-z]+)*)$", "", key))
    return found


def test_every_engine_code_has_an_interface_text() -> None:
    codes = engine_codes()
    assert len(codes) > 40, "the pattern still finds the engine's codes"
    missing = sorted(codes - catalog_codes())
    assert not missing, f"add these codes under 'server' in {CATALOG.relative_to(ROOT)}: {missing}"
