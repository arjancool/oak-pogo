"""The Box CSV follows the chosen language: a parameter from the interface, else the language the
user chose, else Dutch (issue #31)."""

from __future__ import annotations

from typing import Any

from app.api.v1.pokemon import BOX_CSV_COLUMNS
from tests.conftest import Api


def _header(owner: Api, account: int, **params: Any) -> list[str]:
    response = owner.get("/api/v1/pokemon/export/csv", account_id=account, **params)
    assert response.status_code == 200, response.text
    return response.text.lstrip("﻿").splitlines()[0].split(";")


def test_the_box_csv_follows_the_language(owner: Api, container: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    owner.upload(account, export)
    container.runner.drain()
    assert _header(owner, account) == BOX_CSV_COLUMNS["nl"], "Dutch without a choice"
    assert _header(owner, account, lang="en")[2:5] == ["species", "form", "nickname"]
    chosen = owner.put("/api/v1/auth/me/preferences", {"preferences": {"language": "en"}})
    assert chosen.status_code == 200, chosen.text
    assert _header(owner, account) == BOX_CSV_COLUMNS["en"], "the language the user chose"
    assert _header(owner, account, lang="nl") == BOX_CSV_COLUMNS["nl"], "the interface wins"
    assert owner.get("/api/v1/pokemon/export/csv", account_id=account, lang="fr").status_code == 422


def test_both_languages_have_the_same_columns() -> None:
    assert len(BOX_CSV_COLUMNS["nl"]) == len(BOX_CSV_COLUMNS["en"])
    shared = [n for n, e in zip(BOX_CSV_COLUMNS["nl"], BOX_CSV_COLUMNS["en"], strict=True) if n == e]
    assert "oak_id" in shared and "cleanup_status" in shared
