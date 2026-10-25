"""Purify scenario: level and IVs after purification, from the dataset (ADR-0022)."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from sqlalchemy import select

from app.analysis.league import Subject
from app.analysis.purify import Purified, purify
from app.analysis.stats import IVs
from app.domain.pokemon import Alignment
from app.gamedata.model import GameData
from app.models import Pokemon, TrainerAccount
from tests.conftest import Api

# A Shadow Machop 4/13/5 at level 8. Purified and evolved in the game it became a Machoke of
# 1355 CP and then a Machamp of 2066 CP.
MACHOP = "66:"


def _dex(form_key: str) -> int:
    return int(form_key.split(":", maxsplit=1)[0])


def _subject(**changes: Any) -> Subject:
    values: dict[str, Any] = {
        "form_key": MACHOP,
        "ivs": IVs(4, 13, 5),
        "level": 8.0,
        "cp": 257,
        "shadow": True,
        "purified": False,
        "lucky": False,
        "trainer_level": 40,
    }
    return Subject(**{**values, **changes})


def test_purify_raises_level_and_ivs(gamedata: GameData) -> None:
    result = purify(_subject(), gamedata.forms[MACHOP], gamedata.mechanics["purification"])
    assert isinstance(result, Purified)
    assert result.level == 25
    assert result.ivs == IVs(6, 15, 7)
    assert result.subject.shadow is False and result.subject.purified is True
    assert result.stardust == gamedata.forms[MACHOP]["shadow"]["purify_stardust"]
    assert result.candy == gamedata.forms[MACHOP]["shadow"]["purify_candy"]
    assert result.assumption is None and result.source


def test_purify_caps_ivs_and_keeps_a_higher_level(gamedata: GameData) -> None:
    result = purify(
        _subject(ivs=IVs(14, 15, 0), level=30.0), gamedata.forms[MACHOP], gamedata.mechanics["purification"]
    )
    assert isinstance(result, Purified)
    assert result.ivs == IVs(15, 15, 2)
    assert result.level == 30


def test_purify_follows_the_trainer_level(gamedata: GameData) -> None:
    rules = gamedata.mechanics["purification"]
    low = purify(_subject(trainer_level=20), gamedata.forms[MACHOP], rules)
    assert isinstance(low, Purified) and low.level == 20
    unknown = purify(_subject(trainer_level=None), gamedata.forms[MACHOP], rules)
    assert isinstance(unknown, Purified) and unknown.level == 25
    assert unknown.assumption is not None and "onbekend" in unknown.assumption


def test_purify_says_why_it_cannot(gamedata: GameData) -> None:
    form = gamedata.forms[MACHOP]
    assert isinstance(purify(_subject(shadow=False), form, gamedata.mechanics["purification"]), str)
    assert isinstance(purify(_subject(ivs=None), form, gamedata.mechanics["purification"]), str)
    assert isinstance(purify(_subject(), form, None), str)


@pytest.fixture
def machop(owner: Api, container: Any, gamedata: GameData, export: dict[str, Any]) -> int:
    account_id = owner.account()
    owner.upload(account_id, export)
    container.runner.drain()
    with container.db.transaction() as session:
        account = session.get(TrainerAccount, account_id)
        assert account is not None
        account.trainer_level = 40
        pokemon = session.scalars(select(Pokemon).where(Pokemon.trainer_account_id == account_id)).first()
        assert pokemon is not None
        pokemon.species_id, pokemon.form_key = 66, MACHOP
        pokemon.iv_attack, pokemon.iv_defense, pokemon.iv_stamina = 4, 13, 5
        pokemon.level, pokemon.cp, pokemon.alignment = 8.0, 257, Alignment.SHADOW
        pokemon.move_charged_1_key = gamedata.forms[MACHOP]["shadow"]["shadow_move"]
        pokemon.move_charged_2_key = None
        return pokemon.id


def test_evolutions_after_purify_match_the_game(owner: Api, machop: int) -> None:
    shadow = owner.get(f"/api/v1/pokemon/{machop}/evolutions").json()
    assert shadow["scenario"] is None
    assert {_dex(p["target_key"]): p["cp_after"] for p in shadow["paths"]} == {67: 418, 68: 639}

    purified = owner.get(f"/api/v1/pokemon/{machop}/evolutions", scenario="purified").json()
    assert purified["scenario"]["level"] == 25
    assert purified["scenario"]["ivs"] == {"attack": 6, "defense": 15, "stamina": 7}
    paths = {_dex(p["target_key"]): p for p in purified["paths"]}
    assert paths[67]["cp_after"] == 1355
    assert paths[68]["cp_after"] == 2066
    # Purification cannot be undone, and a level cannot be lowered: too strong for Great League.
    assert paths[68]["leagues"]["great"]["over_cap"] is True


def test_analysis_after_purify(owner: Api, machop: int, gamedata: GameData) -> None:
    data = owner.get(f"/api/v1/pokemon/{machop}/analysis", scenario="purified").json()
    assert data["scenario"]["cp"] == 840
    great = {_dex(t["target_key"]): t for t in data["leagues"]["great"]["targets"]}
    assert great[68]["cp_now"] == 2066
    assert great[68]["readiness"] == "not_suitable"
    purified_move = gamedata.forms[MACHOP]["shadow"]["purified_move"]
    assert [m["key"] for m in data["current_moves"]][-1] == purified_move


def test_power_ups_after_purify_start_at_the_new_level(owner: Api, machop: int) -> None:
    data = owner.get(f"/api/v1/pokemon/{machop}/powerups", scenario="purified").json()
    assert data["current"] == {"level": 25, "cp": 840}
    assert data["modifiers"]["purified"] is True and data["modifiers"]["shadow"] is False
    assert data["steps"][0]["level"] == 25.5


def test_only_a_shadow_can_be_purified(owner: Api, machop: int, container: Any) -> None:
    with container.db.transaction() as session:
        pokemon = session.get(Pokemon, machop)
        assert pokemon is not None
        pokemon.alignment = Alignment.NONE
    response = owner.get(f"/api/v1/pokemon/{machop}/analysis", scenario="purified")
    assert response.status_code == 422, response.text


def test_dataset_without_purification_rules_says_so(gamedata: GameData) -> None:
    dataset = copy.deepcopy(dict(gamedata.dataset))
    dataset["mechanics"].pop("purification")
    old = GameData(dataset, gamedata.version_id)
    result = purify(_subject(), old.forms[MACHOP], old.mechanics.get("purification"))
    assert isinstance(result, str) and "ontbreken" in result
