"""Item names in Dutch and in the official English of the game texts (issue #31)."""

from __future__ import annotations

from typing import Any

from app.api.v1.account_data import ITEM_GROUP_LABELS
from app.services.item_names import ITEMS, item_name
from tests.conftest import Api


def test_names_from_the_game_texts() -> None:
    assert item_name("LegendaryRaidTicket", 1403).en == "EX Raid Pass"
    assert item_name("OtherEvolutionStoneA", 1150).en == "Gimmighoul Coins"
    assert item_name("Breakfast", 651).en == "Zygarde Cube"
    assert item_name("ShadowGem", 1505).en == "Purified Gem"
    incubator = item_name("IncubatorBasicUnlimited", 901)
    assert (incubator.nl, incubator.en) == ("Onbeperkte broedmachine", "Incubator ∞")


def test_an_item_without_an_official_name_keeps_its_name() -> None:
    unknown = item_name("SomethingNewFromNiantic", 9999)
    assert unknown.nl == unknown.en == "Something New From Niantic", "split, never made up"
    assert item_name(None, 42).en == "Item #42"
    assert item_name("EventPassPointGoFest02", 2022).group == "event"


def test_every_item_has_both_names_and_a_known_group() -> None:
    for source, names in ITEMS.items():
        assert names.nl and names.en, source
        assert names.group in ITEM_GROUP_LABELS, source


def test_the_items_page_gets_both_names(owner: Api, container: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    owner.upload(account, export)
    container.runner.drain()
    items = owner.get("/api/v1/inventory/items", account_id=account).json()["items"]
    by_source = {i["source_name"]: i for i in items}
    assert by_source["XlRareCandy"]["names"] == {"nl": "Rare Candy XL", "en": "Rare Candy XL"}
    assert by_source["Mp"]["names"]["en"] == "Max Particle"
    assert all(i["name"] == i["names"]["nl"] for i in items)
