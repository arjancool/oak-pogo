"""Max Battles: which attack a Dynamax or Gigantamax Pokémon uses (audit A15)."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from sqlalchemy import select

from app.domain.pokemon import BreadMode
from app.gamedata.model import GameData
from app.models import Pokemon
from app.services.battles import max_attack, max_battle_overview
from tests.conftest import Api, downloads


def _pokemon(mode: BreadMode, *, dex: int = 6, form: str = "6:", fast: str = "AIR_SLASH_FAST") -> Pokemon:
    return Pokemon(species_id=dex, form_key=form, move_fast_key=fast, bread_mode=mode)


def test_gigantamax_uses_its_g_max_move_not_the_fast_move(gamedata: GameData) -> None:
    fast = gamedata.move("AIR_SLASH_FAST")
    assert fast is not None and fast["type"] == "flying"
    for form in ("6:", "6:CHARIZARDNORMAL"):
        attack = max_attack(gamedata, _pokemon(BreadMode.GIGANTAMAX, form=form))
        assert attack == {"type": "fire", "name": "G-Max Wildfire", "source": "gmax_move", "unknown_reason": None}


def test_dynamax_uses_the_max_move_of_its_fast_move_type(gamedata: GameData) -> None:
    attack = max_attack(gamedata, _pokemon(BreadMode.DYNAMAX))
    assert attack == {"type": "flying", "name": "Max Airstream", "source": "fast_move", "unknown_reason": None}


def test_gigantamax_without_a_known_g_max_move_is_unknown(gamedata: GameData) -> None:
    attack = max_attack(gamedata, _pokemon(BreadMode.GIGANTAMAX, dex=150, form="150:", fast="PSYCHO_CUT_FAST"))
    assert attack["type"] is None and attack["source"] is None
    assert "geen G-Max-aanval" in attack["unknown_reason"]


def test_dataset_without_g_max_table_says_so(gamedata: GameData) -> None:
    dataset = copy.deepcopy(dict(gamedata.dataset))
    dataset["bread"].pop("gmax_moves")
    dataset["transform_revision"] = 1
    old = GameData(dataset, gamedata.version_id)
    assert old.outdated
    attack = max_attack(old, _pokemon(BreadMode.GIGANTAMAX))
    assert attack["type"] is None and "Werk de Game Data bij" in attack["unknown_reason"]


def test_dataset_from_an_older_transform_is_rebuilt_from_unchanged_sources(
    container: Any, gamedata: GameData, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = container.gamedata
    dataset = copy.deepcopy(dict(gamedata.dataset))
    dataset["transform_revision"] = 1
    monkeypatch.setattr(store, "_active", GameData(dataset, gamedata.version_id))  # what an upgrade finds
    monkeypatch.setattr("app.gamedata.store.remote_etags", lambda _settings: {})
    assert store.check_remote()["repair_needed"]
    result = store.update_from_downloads(downloads(), origin="download")
    assert result.status == "activated"
    assert not store.active().outdated


@pytest.mark.parametrize(("mode", "expected"), [(BreadMode.GIGANTAMAX, "fire"), (BreadMode.DYNAMAX, "flying")])
def test_overview_ranks_attackers_by_the_right_type(
    owner: Api, container: Any, gamedata: GameData, export: dict[str, Any], mode: BreadMode, expected: str
) -> None:
    account = owner.account()
    one = copy.deepcopy(next(p for p in export["pokemons"] if not p.get("isEgg")))
    export["pokemons"] = [one]
    assert owner.upload(account, export).status_code == 202
    container.runner.drain()
    with container.db.transaction() as session:
        pokemon = session.scalars(select(Pokemon).where(Pokemon.trainer_account_id == account)).one()
        pokemon.species_id, pokemon.species_name, pokemon.form_key = 6, "Charizard", "6:"
        pokemon.move_fast_key, pokemon.bread_mode = "AIR_SLASH_FAST", mode
    with container.db.read() as session:
        result = max_battle_overview(session, gamedata, account, ["steel"])
    item = result["pokemon"][0]
    assert item["max_attack_type"] == expected
    # Fire hits steel super effectively, flying does not.
    assert item["attack_effectiveness"] == pytest.approx(gamedata.effectiveness(expected, ["steel"]))
    assert result["advice"]["attackers"][0]["pokemon_id"] == item["pokemon_id"]
