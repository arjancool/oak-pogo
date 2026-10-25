"""Gym defenders: Game Data eligibility, bulk and the overview per account."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from sqlalchemy import select

from app.analysis.gym import defender_bulk, defender_value
from app.analysis.stats import BaseStats, IVs
from app.domain.pokemon import Alignment
from app.gamedata.model import GameData
from app.models import Pokemon
from app.services.gyms import OUTDATED, gym_defenders
from tests.conftest import Api


@pytest.fixture
def account(owner: Api, container: Any, gamedata: GameData, export: dict[str, Any]) -> int:
    account_id = owner.account()
    owner.upload(account_id, export)
    container.runner.drain()
    return account_id


def test_bulk_is_defense_times_hp() -> None:
    base = BaseStats(attack=100, defense=200, stamina=300)
    ivs = IVs(0, 10, 15)
    # Defense (200 + 10) · 0.5 = 105, HP floor((300 + 15) · 0.5) = 157.
    assert defender_bulk(base, ivs, 0.5) == pytest.approx(105 * 157)
    assert defender_bulk(base, ivs, 0.5, 0.8) == pytest.approx(105 * 0.8 * 157)
    assert defender_value(50, 100) == 50
    assert defender_value(150, 100) == 100
    assert defender_value(10, 0) is None


def test_game_data_says_who_may_defend(gamedata: GameData) -> None:
    assert gamedata.forms["149:"]["deployable"] is True  # Dragonite
    assert gamedata.forms["150:"]["deployable"] is False  # Mewtwo, Legendary
    assert gamedata.forms["151:"]["deployable"] is False  # Mew, Mythical
    assert gamedata.forms["793:"]["deployable"] is False  # Nihilego, Ultra Beast


def test_overview_lists_only_allowed_pokemon_once_per_species(owner: Api, account: int, gamedata: GameData) -> None:
    response = owner.get("/api/v1/battles/gym-defenders", account_id=account)
    assert response.status_code == 200, response.text
    data = response.json()
    defenders = data["defenders"]
    assert defenders and data["unknown_reason"] is None
    assert data["game_data_version"] == gamedata.version_id
    assert data["excluded"]["not_deployable"] >= 1  # the sample has a Mewtwo
    species = [d["species_id"] for d in defenders]
    assert len(species) == len(set(species))
    assert 150 not in species
    bulks = [d["bulk"] for d in defenders]
    assert bulks == sorted(bulks, reverse=True)
    for item in defenders:
        assert 0 <= item["value"] <= 100
        assert item["reasons"] and item["confidence"] in ("high", "medium", "low")
        assert item["same_species"] >= 0


def test_shadow_lowers_bulk_by_the_game_data_multiplier(container: Any, account: int, gamedata: GameData) -> None:
    with container.db.read() as session:
        before = {d["pokemon_id"]: d for d in gym_defenders(session, gamedata, account, limit=100)["defenders"]}
    # The only one of its species, so it stays in the list as the strongest of that species.
    target = next(d for d in before.values() if d["same_species"] == 0 and not d["shadow"])
    with container.db.transaction() as session:
        pokemon = session.get(Pokemon, target["pokemon_id"])
        assert pokemon is not None
        pokemon.alignment = Alignment.SHADOW
    with container.db.read() as session:
        after = gym_defenders(session, gamedata, account, limit=100)["defenders"]
    shadow = next((d for d in after if d["pokemon_id"] == target["pokemon_id"]), None)
    multiplier = float(gamedata.mechanics["pve"]["shadow_defense"])
    assert multiplier < 1
    assert shadow is not None and shadow["shadow"] is True
    assert shadow["bulk"] == pytest.approx(target["bulk"] * multiplier, rel=1e-3)
    assert shadow["value"] <= target["value"]
    assert any("Shadow" in reason for reason in shadow["reasons"])


def test_dataset_without_eligibility_says_so(container: Any, account: int, gamedata: GameData) -> None:
    dataset = copy.deepcopy(dict(gamedata.dataset))
    for form in dataset["forms"].values():
        form.pop("deployable")
    old = GameData(dataset, gamedata.version_id)
    with container.db.read() as session:
        result = gym_defenders(session, old, account)
    assert result["defenders"] == [] and result["unknown_reason"] == OUTDATED


def test_only_own_accounts(owner: Api, account: int, container: Any) -> None:
    with container.db.read() as session:
        assert session.scalars(select(Pokemon).where(Pokemon.trainer_account_id == account)).first() is not None
    assert owner.get("/api/v1/battles/gym-defenders", account_id=account + 999).status_code == 404
