"""The structure summary of an import is bounded and holds no data as keys (issue #46)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import update

from app.models import ImportJob
from app.normalizers.schema import MAX_LIST_ITEMS, summarize_structure
from tests.conftest import Api


def test_keys_that_are_not_names_become_a_star(export: dict[str, Any]) -> None:
    export["Sportpark De Gym (Utrecht)"] = 1
    export["pokemons"][0]["gym name with spaces"] = 2
    export["player"]["badges"] = {"Sporthal Noord": 3, "12": 4}
    summary = summarize_structure(export)
    text = json.dumps(summary)
    for data in ("Sportpark", "gym name with spaces", "Sporthal"):
        assert data not in text, data
    assert "*" in summary["root_keys"] and "*" in summary["pokemon_keys_new"]
    assert "player.badges.*" in summary["paths"] and "player.badges.#" in summary["paths"]


def test_every_list_is_bounded(export: dict[str, Any]) -> None:
    for number in range(MAX_LIST_ITEMS + 50):
        export[f"extra_{number}"] = number
        export["pokemons"][0][f"field_{number}"] = number
    summary = summarize_structure(export)
    for name in ("root_keys", "root_keys_new", "pokemon_keys_new"):
        assert len(summary[name]) == MAX_LIST_ITEMS, name
        assert summary["list_counts"][name] > MAX_LIST_ITEMS, name
    assert summary["truncated"] is True


def test_a_retry_does_not_copy_the_summary_and_a_list_leaves_it_out(
    owner: Api, container: Any, export: dict[str, Any]
) -> None:
    account = owner.account()
    job_id = owner.upload(account, export).json()["id"]
    container.runner.drain()
    with container.db.transaction() as session:
        session.execute(update(ImportJob).where(ImportJob.id == job_id).values(status="failed"))
    retry_id = owner.post(f"/api/v1/imports/{job_id}/retry").json()["id"]
    assert owner.get(f"/api/v1/imports/{job_id}").json()["schema_summary"], "the original keeps it"
    assert owner.get(f"/api/v1/imports/{retry_id}").json()["schema_summary"] is None
    listed = owner.get("/api/v1/imports", account_id=account).json()["items"]
    assert all(item["schema_summary"] is None for item in listed)
