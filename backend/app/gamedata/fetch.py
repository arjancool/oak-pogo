"""Downloading the upstream sources. The only module in the game data layer that does I/O over
the network."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import Settings
from app.gamedata.cups import build_cups, ranking_downloads
from app.gamedata.transform import RANKING_FILES

log = logging.getLogger("oak.gamedata")

USER_AGENT = "OAK-PokemonGO-Manager/2.0 (+https://github.com/arjancool/oak-pogo)"


@dataclass(frozen=True, slots=True)
class Downloaded:
    id: str
    url: str
    content: bytes
    etag: str | None
    retrieved_at: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    def json(self) -> Any:
        return json.loads(self.content)

    def source_record(self, upstream_timestamp: str | None = None) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "sha256": self.sha256,
            "etag": self.etag,
            "bytes": len(self.content),
            "retrieved_at": self.retrieved_at,
            "upstream_timestamp": upstream_timestamp,
        }


def source_urls(settings: Settings) -> dict[str, str]:
    base = settings.gamedata_pvpoke_base_url.rstrip("/")
    urls = {
        "pokeminers": settings.gamedata_pokeminers_url,
        "pvpoke": f"{base}/gamemaster.json",
    }
    for league, cap in RANKING_FILES.items():
        urls[f"pvpoke-rankings-{league}"] = f"{base}/rankings/all/overall/rankings-{cap}.json"
    return urls


def _client(settings: Settings) -> httpx.Client:
    return httpx.Client(
        timeout=settings.gamedata_timeout_seconds,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )


def _download(client: httpx.Client, source_id: str, url: str) -> Downloaded:
    response = client.get(url)
    response.raise_for_status()
    return Downloaded(
        id=source_id,
        url=url,
        content=response.content,
        etag=response.headers.get("etag"),
        retrieved_at=datetime.now(UTC).isoformat(),
    )


def download_all(settings: Settings) -> dict[str, Downloaded]:
    results: dict[str, Downloaded] = {}
    base = settings.gamedata_pvpoke_base_url.rstrip("/")
    with _client(settings) as client:
        for source_id, url in source_urls(settings).items():
            results[source_id] = _download(client, source_id, url)
        # The cups PvPoke shows decide which cup rankings exist (ADR-0027). A missing cup ranking
        # leaves that cup without species ranks; it does not stop the update.
        cups, _notes = build_cups(results["pvpoke"].json())
        for source_id, (cup, cp) in ranking_downloads(cups).items():
            url = f"{base}/rankings/{cup}/overall/rankings-{cp}.json"
            try:
                results[source_id] = _download(client, source_id, url)
            except httpx.HTTPError as exc:
                log.warning("cup ranking unavailable", extra={"source": source_id, "error": str(exc)[:200]})
    return results


def remote_etags(settings: Settings) -> dict[str, str | None]:
    """ETags of the two main sources, for the 'new version available' check without download."""
    urls = source_urls(settings)
    result: dict[str, str | None] = {}
    with _client(settings) as client:
        for source_id in ("pokeminers", "pvpoke"):
            response = client.head(urls[source_id])
            response.raise_for_status()
            result[source_id] = response.headers.get("etag")
    return result
