"""Downloading the upstream sources. The only module in the game data layer that does I/O over
the network."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.core.config import Settings
from app.core.download import GAMEDATA_MAX_BYTES, client, fetch
from app.gamedata.cups import build_cups, ranking_downloads
from app.gamedata.transform import RANKING_FILES

log = logging.getLogger("oak.gamedata")

USER_AGENT = "OAK-PokemonGO-Manager/2.0 (+https://github.com/arjancool/oak-pogo)"
# timestamp.txt holds one number; anything larger is not that file.
TIMESTAMP_MAX_BYTES = 64
# One commit from the GitHub API is a few kilobytes.
COMMITS_MAX_BYTES = 256 * 1024
# Pokémon GO came out in July 2016; an upstream date before that, or far in the future, is wrong.
FIRST_UPSTREAM_DATE = datetime(2016, 7, 1, tzinfo=UTC)
MILLISECONDS_FROM = 10**11


def upstream_time(value: Any, now: datetime | None = None) -> datetime | None:
    """The time a source says its data is from: milliseconds or seconds since 1970, or an ISO
    date such as PvPoke's "2026-08-28 10:15:00" (UTC when no zone is given). None when the value
    is missing, unreadable or outside 2016 up to tomorrow."""
    moment: datetime | None = None
    if isinstance(value, bool):
        return None
    if isinstance(value, int) or (isinstance(value, str) and value.strip().isdigit()):
        number = int(value)
        try:
            moment = datetime.fromtimestamp(number / 1000 if number >= MILLISECONDS_FROM else number, UTC)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(value, str) and value.strip():
        try:
            moment = datetime.fromisoformat(value.strip())
        except ValueError:
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
    if moment is None:
        return None
    latest = (now or datetime.now(UTC)) + timedelta(days=1)
    return moment.astimezone(UTC) if FIRST_UPSTREAM_DATE <= moment <= latest else None


@dataclass(frozen=True, slots=True)
class UpstreamDate:
    """The date of the newest data at a source. ``problem`` says why it is unknown:
    "unreachable" (with the error name in ``detail``) or "invalid"."""

    at: str | None
    problem: str | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class Downloaded:
    id: str
    url: str
    content: bytes
    etag: str | None
    retrieved_at: str
    # The date the source gives for this data, when it publishes one next to the file.
    upstream: UpstreamDate | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    def json(self) -> Any:
        return json.loads(self.content)

    def source_record(self, upstream_timestamp: str | None = None) -> dict[str, Any]:
        record = {
            "id": self.id,
            "url": self.url,
            "sha256": self.sha256,
            "etag": self.etag,
            "bytes": len(self.content),
            "retrieved_at": self.retrieved_at,
            "upstream_timestamp": upstream_timestamp or (self.upstream.at if self.upstream else None),
        }
        if self.upstream and self.upstream.problem:
            record["upstream_problem"] = {"problem": self.upstream.problem, "detail": self.upstream.detail}
        return record


def source_urls(settings: Settings) -> dict[str, str]:
    base = settings.gamedata_pvpoke_base_url.rstrip("/")
    urls = {
        "pokeminers": settings.gamedata_pokeminers_url,
        "pvpoke": f"{base}/gamemaster.json",
    }
    for league, cap in RANKING_FILES.items():
        urls[f"pvpoke-rankings-{league}"] = f"{base}/rankings/all/overall/rankings-{cap}.json"
    return urls


def timestamp_url(settings: Settings) -> str:
    """PokeMiners publishes timestamp.txt next to latest.json (issue #28)."""
    return settings.gamedata_pokeminers_url.rsplit("/", 1)[0] + "/timestamp.txt"


def github_commits_url(url: str) -> str | None:
    """For a file on raw.githubusercontent.com, the GitHub API address of its last commit. The
    Game Master of alexelgt has no timestamp.txt, so the date of its last change is the date of
    the data (ADR-0028). None for a file elsewhere."""
    parsed = httpx.URL(url)
    if parsed.scheme != "https" or parsed.host != "raw.githubusercontent.com":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 6 and parts[2:4] == ["refs", "heads"]:  # owner/repo/refs/heads/ref/file
        owner, repo, ref, path = parts[0], parts[1], parts[4], parts[5:]
    elif len(parts) >= 4:  # owner/repo/ref/file
        owner, repo, ref, path = parts[0], parts[1], parts[2], parts[3:]
    else:
        return None
    query = httpx.QueryParams({"path": "/".join(path), "sha": ref, "per_page": "1"})
    return f"https://api.github.com/repos/{owner}/{repo}/commits?{query}"


def source_name(url: str) -> str:
    """Who publishes a source, for the page: the owner on GitHub, otherwise the host."""
    parsed = httpx.URL(url)
    if parsed.host == "raw.githubusercontent.com":
        owner = next((part for part in parsed.path.split("/") if part), "")
        return owner or parsed.host
    return parsed.host or url


def _client(settings: Settings) -> httpx.Client:
    return client(settings.gamedata_timeout_seconds, USER_AGENT)


def _download(http: httpx.Client, source_id: str, url: str) -> Downloaded:
    """At most GAMEDATA_MAX_BYTES, and the URL the content really came from (issue #49)."""
    response = fetch(http, url, max_bytes=GAMEDATA_MAX_BYTES)
    return Downloaded(
        id=source_id,
        url=response.url,
        content=response.content,
        etag=response.headers.get("etag"),
        retrieved_at=datetime.now(UTC).isoformat(),
    )


def _timestamp(http: httpx.Client, settings: Settings) -> UpstreamDate:
    """The date of the newest Game Master at its source. Never raises: an unknown date does not
    stop an update or a check.

    timestamp.txt next to the file comes first, as PokeMiners publishes it. Without it, for a file
    on GitHub, the date of the last commit that changed the file counts (ADR-0028)."""
    try:
        response = fetch(http, timestamp_url(settings), max_bytes=TIMESTAMP_MAX_BYTES)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != httpx.codes.NOT_FOUND:
            return UpstreamDate(None, "unreachable", type(exc).__name__)
        return _commit_date(http, settings.gamedata_pokeminers_url)
    except httpx.HTTPError as exc:
        return UpstreamDate(None, "unreachable", type(exc).__name__)
    moment = upstream_time(response.content.decode("ascii", "replace").strip())
    return UpstreamDate(moment.isoformat()) if moment else UpstreamDate(None, "invalid")


def _commit_date(http: httpx.Client, url: str) -> UpstreamDate:
    api = github_commits_url(url)
    if api is None:
        return UpstreamDate(None, "not_published")
    try:
        response = fetch(http, api, max_bytes=COMMITS_MAX_BYTES, headers={"Accept": "application/vnd.github+json"})
        commits = json.loads(response.content)
        stamp = commits[0]["commit"]["committer"]["date"]
    except httpx.HTTPError as exc:
        return UpstreamDate(None, "unreachable", type(exc).__name__)
    except (ValueError, LookupError, TypeError):
        return UpstreamDate(None, "invalid")
    moment = upstream_time(stamp)
    return UpstreamDate(moment.isoformat()) if moment else UpstreamDate(None, "invalid")


def download_all(settings: Settings) -> dict[str, Downloaded]:
    results: dict[str, Downloaded] = {}
    base = settings.gamedata_pvpoke_base_url.rstrip("/")
    with _client(settings) as http:
        for source_id, url in source_urls(settings).items():
            results[source_id] = _download(http, source_id, url)
        results["pokeminers"] = dataclasses.replace(results["pokeminers"], upstream=_timestamp(http, settings))
        # The cups PvPoke shows decide which cup rankings exist (ADR-0027). A missing cup ranking
        # leaves that cup without species ranks; it does not stop the update.
        cups, _notes = build_cups(results["pvpoke"].json())
        for source_id, (cup, cp) in ranking_downloads(cups).items():
            url = f"{base}/rankings/{cup}/overall/rankings-{cp}.json"
            try:
                results[source_id] = _download(http, source_id, url)
            except httpx.HTTPError as exc:
                log.warning("cup ranking unavailable", extra={"source": source_id, "error": str(exc)[:200]})
    return results


def remote_timestamp(settings: Settings) -> UpstreamDate:
    """The date of the newest Game Master at its source, for the check without download."""
    with _client(settings) as http:
        return _timestamp(http, settings)


def remote_etags(settings: Settings) -> dict[str, str | None]:
    """ETags of the two main sources, for the 'new version available' check without download."""
    urls = source_urls(settings)
    result: dict[str, str | None] = {}
    with _client(settings) as http:
        for source_id in ("pokeminers", "pvpoke"):
            response = fetch(http, urls[source_id], max_bytes=GAMEDATA_MAX_BYTES, method="HEAD")
            result[source_id] = response.headers.get("etag")
    return result
