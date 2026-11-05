"""The newest OAK release next to the running version, for the owner only (issue #29)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.services.releases import ReleaseCheck, parse_version
from tests.conftest import PASSWORD, Api

RUNNING = parse_version(__version__)


def _release(version: str) -> dict[str, Any]:
    return {
        "tag_name": f"v{version}",
        "published_at": "2026-10-27T20:45:35Z",
        "html_url": f"https://github.com/arjancool/oak-pogo/releases/tag/v{version}",
    }


class Calls:
    """A stand-in for GitHub that counts the requests."""

    def __init__(self, answer: dict[str, Any] | Exception) -> None:
        self.answer = answer
        self.count = 0

    def __call__(self) -> dict[str, Any]:
        self.count += 1
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _use(container: Any, answer: dict[str, Any] | Exception, *, enabled: bool = True) -> Calls:
    calls = Calls(answer)
    container.settings.release_check = enabled
    container.releases = ReleaseCheck(container.settings, fetcher=calls)
    return calls


def _status(owner: Api) -> dict[str, Any]:
    response = owner.get("/api/v1/system/release")
    assert response.status_code == 200, response.text
    return response.json()


def test_a_newer_release_is_named_with_its_link(owner: Api, container: Any) -> None:
    assert RUNNING is not None
    newer = f"{RUNNING[0]}.{RUNNING[1] + 1}.0"
    _use(container, _release(newer))
    status = _status(owner)
    assert status["status"] == "newer" and status["current"] == __version__
    assert status["latest"] == {
        "version": newer,
        "published_at": "2026-10-27T20:45:35Z",
        "url": f"https://github.com/arjancool/oak-pogo/releases/tag/v{newer}",
    }


def test_the_same_version_is_the_newest(owner: Api, container: Any) -> None:
    _use(container, _release(__version__))
    assert _status(owner)["status"] == "same"


def test_a_build_newer_than_the_release_says_so(owner: Api, container: Any) -> None:
    _use(container, _release("0.9.0"))
    assert _status(owner)["status"] == "ahead"


def test_github_not_reachable_is_unknown_with_the_reason(owner: Api, container: Any) -> None:
    _use(container, httpx.ConnectError("offline"))
    status = _status(owner)
    assert status["status"] == "unknown" and status["latest"] is None
    assert status["reason"] == {
        "code": "RELEASE_UNREACHABLE",
        "text": "GitHub was niet bereikbaar: ConnectError",
        "data": {"error": "ConnectError"},
    }
    limited = httpx.HTTPStatusError(
        "rate limit", request=httpx.Request("GET", "https://api.github.com"), response=httpx.Response(403)
    )
    _use(container, limited)
    assert _status(owner)["reason"]["data"] == {"error": "HTTP 403"}
    missing = httpx.HTTPStatusError(
        "none", request=httpx.Request("GET", "https://api.github.com"), response=httpx.Response(404)
    )
    _use(container, missing)
    assert _status(owner)["reason"]["code"] == "RELEASE_NONE"


@pytest.mark.parametrize("answer", [{"tag_name": "nieuw"}, {}, ValueError("no JSON")])
def test_an_unreadable_answer_is_unknown(owner: Api, container: Any, answer: Any) -> None:
    _use(container, answer)
    status = _status(owner)
    assert status["status"] == "unknown" and status["reason"]["code"] == "RELEASE_INVALID"


def test_only_a_link_to_the_oak_releases_is_passed_on(owner: Api, container: Any) -> None:
    _use(container, {**_release("9.0.0"), "html_url": "https://elsewhere.example/v9.0.0"})
    assert _status(owner)["latest"]["url"] is None


def test_the_answer_is_kept_for_a_while(owner: Api, container: Any) -> None:
    calls = _use(container, _release(__version__))
    _status(owner)
    _status(owner)
    assert calls.count == 1, "a page view does not go outside every time"


def test_switched_off_asks_nothing(owner: Api, container: Any) -> None:
    calls = _use(container, _release("9.0.0"), enabled=False)
    assert _status(owner) == {"enabled": False, "current": __version__}
    assert calls.count == 0


def test_only_the_owner_sees_it(owner: Api, app: Any, container: Any) -> None:
    calls = _use(container, _release("9.0.0"))
    assert owner.post("/api/v1/users", {"username": "gebruiker", "password": PASSWORD}).status_code == 201
    with TestClient(app) as other_client:
        user = Api(other_client)
        assert user.login("gebruiker").status_code == 200
        assert user.get("/api/v1/system/release").status_code == 403
    assert calls.count == 0
