"""A newer Game Master names some forms only by number, such as 3362. OAK builds the dataset all
the same, instead of failing the whole update."""

from __future__ import annotations

import json
from typing import Any

from app.gamedata.transform import norm_key
from tests.conftest import TEST_LIMITS, downloads, gamedata_files


def test_a_numeric_form_is_a_key_like_any_other() -> None:
    assert norm_key(3362) == "3362"
    assert norm_key("SmolivNormal") == norm_key("SMOLIV_NORMAL")
    assert norm_key(None) == ""


def test_an_update_with_numeric_forms_is_activated(container: Any) -> None:
    files = gamedata_files()
    game_master = json.loads(files["pokeminers"])
    pikachu = next(t for t in game_master if t["templateId"] == "FORMS_V0025_POKEMON_PIKACHU")
    pikachu["data"]["formSettings"]["forms"].append({"form": 3362, "isCostume": True})
    files["pokeminers"] = json.dumps(game_master).encode()
    store = container.gamedata
    store.limits = TEST_LIMITS
    result = store.update_from_downloads(downloads(files), origin="upload")
    assert result.status == "activated", result.message
    active = store.active()
    assert active is not None
    assert active.is_costume_form(25, "3362")
