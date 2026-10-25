"""Downloading the upstream sources. The only module in the game data layer that does I/O over
the network."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import Settings
from app.gamedata.transform import RANKING_FILES

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


def download_all(settings: Settings) -> dict[str, Downloaded]:
    results: dict[str, Downloaded] = {}
    with _client(settings) as client:
        for source_id, url in source_urls(settings).items():
            response = client.get(url)
            response.raise_for_status()
            results[source_id] = Downloaded(
                id=source_id,
                url=url,
                content=response.content,
                etag=response.headers.get("etag"),
                retrieved_at=datetime.now(UTC).isoformat(),
            )
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
