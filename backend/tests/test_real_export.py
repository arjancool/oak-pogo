"""Optional check of the cleanup rules on a real export with real Game Data (ADR-0019).

Skipped unless ``OAK_TEST_REAL_EXPORT`` points to a PGSharp ``PGSStats.json``. The test
downloads the current Game Data, so it needs network access. A real export is personal data:
keep it outside the repository.

    OAK_TEST_REAL_EXPORT=/pad/naar/PGSStats.json pytest tests/test_real_export.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

EXPORT = os.environ.get("OAK_TEST_REAL_EXPORT")

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not EXPORT, reason="OAK_TEST_REAL_EXPORT is niet ingesteld"),
]


def _items(owner: Any, account: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        data = owner.get("/api/v1/cleanup/recommendations", account_id=account, page_size=500, page=page).json()
        items += data["items"]
        if len(items) >= data["total"]:
            return items
        page += 1


def test_real_export_rules(owner: Any, container: Any) -> None:
    result = container.gamedata.update_from_network()
    assert result.status == "activated", result.message
    account = owner.account()
    owner.upload(account, json.loads(Path(str(EXPORT)).read_text(encoding="utf-8-sig")))
    container.runner.drain()
    items = _items(owner, account)
    assert items

    for item in items:
        codes = [r["code"] for r in item["protection_reasons"]]
        assert "FAVORITE" not in codes
        if item["status"] == "PROTECT":
            assert codes, "PROTECT always has a hard reason"
        pokemon = item["pokemon"]
        if pokemon["favorite"]:
            assert item["status"] != "TRANSFER_CANDIDATE"
        if pokemon["vintage_year"] is not None:
            assert item["status"] == "PROTECT" and codes[0] == "VINTAGE"
            assert item["battle_score"] is not None and item["scores"]["battle"]["parts"]
        if not pokemon["catch_date_known"]:
            assert item["status"] != "TRANSFER_CANDIDATE"

    # Gym defenders on real data: only forms the Game Data allows, one per species, best first.
    gyms = owner.get("/api/v1/battles/gym-defenders", account_id=account).json()
    assert gyms["unknown_reason"] is None and gyms["defenders"]
    gd = container.gamedata.active()
    species = [d["species_id"] for d in gyms["defenders"]]
    assert len(species) == len(set(species))
    assert all(gd.species_record(dex) is not None for dex in species)
    bulks = [d["bulk"] for d in gyms["defenders"]]
    assert bulks == sorted(bulks, reverse=True)
