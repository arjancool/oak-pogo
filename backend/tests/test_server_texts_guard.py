"""Sentences about the transfer list have a text in the interface catalog (ADR-0025)."""

from __future__ import annotations

import json
import re

from tests.test_server_texts import CATALOG, ROOT

SOURCES = {
    "guard": ROOT / "backend" / "app" / "services" / "transfer_guard.py",
}
CODES = re.compile(r'_text\(\s*"([A-Z][A-Z_]+)"')


def test_every_guard_code_has_an_interface_text() -> None:
    server = json.loads(CATALOG.read_text(encoding="utf-8"))["server"]
    for group, path in SOURCES.items():
        codes = set(CODES.findall(path.read_text(encoding="utf-8")))
        assert codes, path
        missing = sorted(code for code in codes if code not in server[group] and code not in server["protections"])
        assert not missing, f"{group}: {missing}"
    cleanup_api = (ROOT / "backend" / "app" / "api" / "v1" / "cleanup.py").read_text(encoding="utf-8")
    assert "UNCONFIRMED" in server["guard"] and "UNCONFIRMED" in cleanup_api
    assert "SEARCH_NOTE" in server["actionList"] and "SEARCH_NOTE" in cleanup_api
    fixed = set(re.findall(r'"code": "([A-Z_]+)",\n\s+"text": f?"', cleanup_api))
    assert fixed and fixed <= set(server["rules"]), fixed - set(server["rules"])
