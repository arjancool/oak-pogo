"""A valid webhook token works, also from an address that sent many invalid ones (issue #44)."""

from __future__ import annotations

from typing import Any

from tests.conftest import Api


def test_a_valid_token_gets_through_a_blocked_address(owner: Api, container: Any, export: dict[str, Any]) -> None:
    path = owner.webhook_path(owner.account())
    wrong = path[:-6] + ("A" * 6 if not path.endswith("AAAAAA") else "B" * 6)
    for _ in range(container.webhook_invalid_by_ip.limit):
        assert owner.client.post(wrong, json={}).status_code == 404
    assert owner.client.post(wrong, json={}).status_code == 429, "invalid tokens stay blocked"
    response = owner.client.post(path, json=export)
    assert response.status_code == 202, response.text
