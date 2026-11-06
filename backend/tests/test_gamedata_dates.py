"""The date of the Game Data per source, and the newest Game Master at PokeMiners (issue #28)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.gamedata.fetch import UpstreamDate, upstream_time
from tests.conftest import FIXTURES, TEST_LIMITS, Api, downloads

# 28 August 2026, 12:00 UTC, as PokeMiners writes it: milliseconds since 1970.
AUGUST = "1787918400000"
AUGUST_ISO = "2026-08-28T12:00:00+00:00"
LEAGUES = {"1500": "great", "2500": "ultra", "10000": "master"}


def test_upstream_dates_are_read_carefully() -> None:
    now = datetime(2026, 11, 5, tzinfo=UTC)
    assert upstream_time(AUGUST, now) == datetime(2026, 8, 28, 12, tzinfo=UTC)
    assert upstream_time(int(AUGUST) // 1000, now) == datetime(2026, 8, 28, 12, tzinfo=UTC), "seconds too"
    assert upstream_time("2026-10-21 03:50:13", now) == datetime(2026, 10, 21, 3, 50, 13, tzinfo=UTC)
    for wrong in (None, "", "gisteren", True, "99999999999999999999", "1000", "2030-01-01T00:00:00", "<html>"):
        assert upstream_time(wrong, now) is None, wrong


def _network(monkeypatch: pytest.MonkeyPatch, timestamp: httpx.Response) -> None:
    """The sources outside, served from the fixtures."""
    base = FIXTURES / "gamedata"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/latest/timestamp.txt"):
            return timestamp
        if path.endswith("/latest/latest.json"):
            content = (base / "pokeminers-subset.json").read_bytes()
            return httpx.Response(200, content=content, headers={"etag": '"pokeminers"'})
        if path.endswith("/src/data/gamemaster.json"):
            return httpx.Response(200, content=(base / "pvpoke-subset.json").read_bytes(), headers={"etag": '"pvpoke"'})
        if "/rankings/" in path:
            cup, cap = path.split("/rankings/")[1].split("/")[0], path.rsplit("-", 1)[1].removesuffix(".json")
            name = f"pvpoke-rankings-{LEAGUES[cap]}" if cup == "all" else f"pvpoke-rankings-{cup}-{cap}"
            file = base / f"{name}-subset.json"
            if file.exists():
                return httpx.Response(200, content=file.read_bytes())
        return httpx.Response(404)

    def client(_settings: Any) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)

    monkeypatch.setattr("app.gamedata.fetch._client", client)


def _dates(owner: Api) -> dict[str, dict[str, Any]]:
    active = owner.get("/api/v1/gamedata/status").json()["active"]
    return {d["source"]: d for d in active["dates"]}


def test_a_download_keeps_the_date_of_each_source(owner: Api, container: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    container.gamedata.limits = TEST_LIMITS
    _network(monkeypatch, httpx.Response(200, text=AUGUST + "\n"))
    assert container.gamedata.update_from_network().status == "activated"
    dates = _dates(owner)
    assert dates["pokeminers"] == {"source": "pokeminers", "date": AUGUST_ISO, "reason": None}
    assert dates["pvpoke"]["date"] == "2026-10-21T03:50:13+00:00"
    # After an update the active version is the newest, so the page says so.
    check = owner.get("/api/v1/gamedata/status").json()["remote_check"]
    assert check["available"] is False and check["latest"] == {"date": AUGUST_ISO, "reason": None}


def test_an_unreachable_date_is_unknown_with_the_reason(
    owner: Api, container: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    container.gamedata.limits = TEST_LIMITS
    _network(monkeypatch, httpx.Response(404))
    assert container.gamedata.update_from_network().status == "activated", "the update goes on without it"
    reason = _dates(owner)["pokeminers"]["reason"]
    assert _dates(owner)["pokeminers"]["date"] is None
    assert reason["code"] == "DATE_UNREACHABLE" and reason["data"] == {"error": "HTTPStatusError"}


def test_a_file_that_is_no_timestamp_is_unknown(owner: Api, container: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    container.gamedata.limits = TEST_LIMITS
    _network(monkeypatch, httpx.Response(200, text="<html>niet gevonden</html>"))
    container.gamedata.update_from_network()
    assert _dates(owner)["pokeminers"]["reason"]["code"] == "DATE_INVALID"


def test_an_upload_has_no_date(owner: Api, gamedata: Any) -> None:
    dates = _dates(owner)
    assert dates["pokeminers"]["date"] is None and dates["pokeminers"]["reason"]["code"] == "DATE_UPLOAD"
    assert dates["pvpoke"]["date"] is not None, "PvPoke writes its date in the file itself"


def test_an_older_version_gets_the_date_of_the_same_content(
    owner: Api, container: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = container.gamedata
    store.limits = TEST_LIMITS
    assert store.update_from_downloads(downloads(), origin="download").status == "activated"
    assert _dates(owner)["pokeminers"]["reason"]["code"] == "DATE_NOT_RECORDED"
    _network(monkeypatch, httpx.Response(200, text=AUGUST))
    assert store.update_from_network().status == "unchanged"
    assert _dates(owner)["pokeminers"] == {"source": "pokeminers", "date": AUGUST_ISO, "reason": None}


def _active_etags(owner: Api) -> dict[str, str | None]:
    active = owner.get("/api/v1/gamedata/status").json()["active"]
    return {s["id"]: s["etag"] for s in active["sources"] if s["id"] in ("pokeminers", "pvpoke")}


@pytest.mark.parametrize(
    ("latest", "available"),
    [(UpstreamDate(AUGUST_ISO), False), (UpstreamDate("2026-10-27T12:00:00+00:00"), True)],
)
def test_the_check_compares_the_newest_date(
    owner: Api, container: Any, monkeypatch: pytest.MonkeyPatch, latest: UpstreamDate, available: bool
) -> None:
    container.gamedata.limits = TEST_LIMITS
    _network(monkeypatch, httpx.Response(200, text=AUGUST))
    container.gamedata.update_from_network()
    etags = _active_etags(owner)
    monkeypatch.setattr("app.gamedata.store.remote_etags", lambda _settings: etags)
    monkeypatch.setattr("app.gamedata.store.remote_timestamp", lambda _settings: latest)
    result = owner.post("/api/v1/gamedata/check").json()
    assert result["available"] is available
    assert result["changed_sources"] == (["pokeminers"] if available else [])
    kept = owner.get("/api/v1/gamedata/status").json()["remote_check"]
    assert kept["latest"]["date"] == latest.at and kept["available"] is available and kept["checked_at"]


def test_a_check_without_the_date_says_why(owner: Api, gamedata: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.gamedata.store.remote_etags", lambda _settings: {"pokeminers": "x", "pvpoke": "y"})
    result = owner.post("/api/v1/gamedata/check").json()
    assert result["latest"]["date"] is None
    assert result["latest"]["reason"] == {
        "code": "DATE_UNREACHABLE",
        "text": "De datum van de bron was niet bereikbaar: ConnectError",
        "data": {"error": "ConnectError"},
    }

    def offline(_settings: Any) -> Any:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("app.gamedata.store.remote_etags", offline)
    failed = owner.post("/api/v1/gamedata/check").json()
    assert failed["available"] is None and failed["error"]["code"] == "SOURCE_UNREACHABLE"
    assert owner.get("/api/v1/gamedata/status").json()["remote_check"]["error"]["code"] == "SOURCE_UNREACHABLE"
