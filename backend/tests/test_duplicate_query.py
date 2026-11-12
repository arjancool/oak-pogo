"""The duplicate filter counts groups once instead of row by row (issue #38)."""

from __future__ import annotations

import time
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import make_transient

from app.domain.query import Term, parse_query
from app.models import Pokemon
from tests.conftest import Api


def test_the_same_term_twice_counts_once() -> None:
    assert parse_query("!dup !dup dubbel&!duplicate") == [
        Term("flag", "duplicate", negate=True),
        Term("flag", "duplicate"),
    ]


def _key(pokemon: Pokemon) -> tuple[Any, int]:
    # The form key, or else the species number, and the alignment: the same as the SQL.
    form = pokemon.form_key if pokemon.form_key is not None else ("species", pokemon.species_id)
    return form, pokemon.alignment or 0


def _ids(owner: Api, account: int, **params: Any) -> set[int]:
    response = owner.get("/api/v1/pokemon", account_id=account, page_size=200, **params)
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["items"]}


def test_duplicates_are_the_same_as_counted_by_hand(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = owner.account()
    owner.upload(account, export)
    container.runner.drain()
    with container.db.transaction() as session:
        rows = session.scalars(select(Pokemon).where(Pokemon.trainer_account_id == account)).all()
        groups = Counter(_key(p) for p in rows)
        pair = next(p for p in rows if groups[_key(p)] == 2)
        single = next(p for p in rows if groups[_key(p)] == 1)
        # One of a pair and a single one are gone: the other of the pair is no longer a
        # duplicate, and the one that is gone still is, because its partner is still there.
        pair.inventory_status = "not_in_inventory"
        single.inventory_status = "not_in_inventory"
        session.flush()
        rows = session.scalars(select(Pokemon).where(Pokemon.trainer_account_id == account)).all()
        present = Counter(_key(p) for p in rows if p.inventory_status == "in_inventory")
        expected = {p.id for p in rows if present[_key(p)] - (1 if p.inventory_status == "in_inventory" else 0) >= 1}
        everyone = {p.id for p in rows}
    assert expected, "the sample export has duplicates"
    assert _ids(owner, account, q="dup", status="all") == expected
    assert _ids(owner, account, q="!dup", status="all") == everyone - expected
    assert _ids(owner, account, duplicate="true", status="all") == expected


def test_duplicate_filter_stays_fast_for_a_large_collection(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = owner.account()
    owner.upload(account, export)
    container.runner.drain()
    with container.db.transaction() as session:
        template = session.scalars(select(Pokemon).where(Pokemon.trainer_account_id == account)).first()
        assert template is not None
        session.expunge(template)
        for number in range(4000):
            make_transient(template)
            template.id = None  # type: ignore[assignment]
            template.source_pokemon_id = str(10**15 + number)
            template.species_id = 2000 + number % 2500
            template.form_key = f"TEST_{number % 2500}"
            session.add(template)
            session.flush()
            session.expunge(template)
    started = time.perf_counter()
    response = owner.get("/api/v1/pokemon", account_id=account, q="!dup cp>0", duplicate="false", page_size=1)
    took = time.perf_counter() - started
    assert response.status_code == 200, response.text
    assert response.json()["total"] >= 1000
    assert took < 3, f"duplicate filter took {took:.1f} s for about 4,000 Pokémon"
