"""Search syntax (spec §9.4) and Box filters."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from app.domain.query import (
    FLAG_ALIASES,
    FLAG_TERMS,
    NUMERIC_FIELDS,
    TEXT_FIELDS,
    UNSUPPORTED_TERMS,
    QuerySyntaxError,
    Term,
    parse_query,
)

QUERY_DOCS = Path(__file__).resolve().parents[2] / "docs" / "QUERY_SYNTAX.md"


def test_parse_examples() -> None:
    assert parse_query("Gyarados") == [Term("free", "name", "contains", "gyarados")]
    assert parse_query("cp>2500") == [Term("numeric", "cp", ">", 2500.0)]
    assert parse_query("ivs:15/15/15") == [Term("ivs", "ivs", "=", (15, 15, 15))]
    assert parse_query("2018") == [Term("numeric", "caught_year", "=", 2018.0)]
    assert parse_query("shiny cp<1500") == [
        Term("flag", "shiny"),
        Term("numeric", "cp", "<", 1500.0),
    ]
    assert parse_query("!favorite&lucky") == [
        Term("flag", "favorite", negate=True),
        Term("flag", "lucky"),
    ]
    assert parse_query("cp:1000-2000") == [Term("numeric", "cp", "range", (1000.0, 2000.0))]
    assert parse_query("#130") == [Term("numeric", "species_id", "=", 130.0)]
    assert parse_query("move:hydro_pump") == [Term("text", "move", "contains", "hydro pump")]
    assert parse_query("4*") == [Term("flag", "hundo")]


@pytest.mark.parametrize(
    "bad", ["!", "cp>abc", "ivs:16/1/1", "onbekend:3", "evolvable", "!evolueerbaar", " ".join(["x"] * 21)]
)
def test_parse_errors(bad: str) -> None:
    with pytest.raises(QuerySyntaxError):
        parse_query(bad)


def test_every_search_term_is_documented() -> None:
    text = QUERY_DOCS.read_text(encoding="utf-8")
    for term in [*FLAG_TERMS, *FLAG_ALIASES, *NUMERIC_FIELDS, *TEXT_FIELDS, *UNSUPPORTED_TERMS]:
        assert f"`{term}" in text, term


def test_documented_examples_parse() -> None:
    section = QUERY_DOCS.read_text(encoding="utf-8").split("## Voorbeelden", 1)[1].split("\n## ", 1)[0]
    examples = re.findall(r"^\| `([^`]+)` \|", section, flags=re.MULTILINE)
    assert len(examples) >= 5
    for example in examples:
        parse_query(example)


def test_box_search_filters_and_sort(owner: Any, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    owner.upload(account, export)
    container.runner.drain()

    def total(**params: Any) -> int:
        response = owner.get("/api/v1/pokemon", account_id=account, page_size=1, **params)
        assert response.status_code == 200, response.text
        return int(response.json()["total"])

    assert total() == 67
    assert total(q="magikarp") == 6
    assert total(q="#129") == 6
    assert total(q="hundo") >= 1
    assert total(q="ivs:15/15/15") == total(q="hundo")
    assert total(q="shiny") == total(shiny="true")
    assert total(q="!shiny") == 67 - total(q="shiny")
    assert total(q="cp>1000 cp<=5000") == total(cp_min=1001, cp_max=5000)
    assert total(q="shadow") >= 1 and total(q="purified") >= 1 and total(q="lucky") >= 1
    assert total(q="background") >= 1 and total(q="dynamax") >= 1 and total(q="costume") >= 1
    assert total(q="duplicate") >= 6
    assert total(q="year:2016") >= 1
    assert total(species="129,130") == total(q="#129") + total(q="#130")
    assert total(q="move:splash") >= 1
    assert total(q="type:water") >= 6
    assert total(q="untagged") + total(q="!untagged") == 67
    bad = owner.get("/api/v1/pokemon", account_id=account, q="cp>abc")
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "QUERY_SYNTAX"
    items = owner.get("/api/v1/pokemon", account_id=account, sort="-cp", page_size=67).json()["items"]
    cps = [i["cp"] for i in items]
    assert cps == sorted(cps, reverse=True)
    names = [
        i["species_name"]
        for i in owner.get("/api/v1/pokemon", account_id=account, sort="name", page_size=67).json()["items"]
    ]
    assert names == sorted(names)
    page2 = owner.get("/api/v1/pokemon", account_id=account, sort="-cp", page=2, page_size=10).json()["items"]
    assert [p["id"] for p in page2] == [p["id"] for p in items[10:20]]
    csv = owner.get("/api/v1/pokemon/export/csv", account_id=account, q="magikarp")
    assert csv.status_code == 200 and len(csv.text.strip().splitlines()) == 7


def test_bulk_actions_only_touch_metadata(owner: Any, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    owner.upload(account, export)
    container.runner.drain()
    items = owner.get("/api/v1/pokemon", account_id=account, page_size=3).json()["items"]
    ids = [i["id"] for i in items]
    before = {i["id"]: (i["cp"], i["favorite"]) for i in items}
    for action, value in (
        ("protect", "bulk"),
        ("add_tag", "raid"),
        ("review", None),
        ("add_to_list", "plan"),
    ):
        response = owner.post(
            "/api/v1/pokemon/bulk",
            {"account_id": account, "ids": ids, "action": action, "value": value},
        )
        assert response.status_code == 200, response.text
    for pokemon_id in ids:
        detail = owner.get(f"/api/v1/pokemon/{pokemon_id}").json()
        assert detail["metadata"]["protected"] is True and "raid" in detail["metadata"]["tags"]
        assert detail["metadata"]["review_status"] == "to_review"
        assert (detail["cp"], detail["favorite"]) == before[pokemon_id]
    compare = owner.post("/api/v1/pokemon/compare", {"ids": ids[:2]})
    assert compare.status_code == 200 and len(compare.json()) == 2
