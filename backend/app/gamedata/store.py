"""Game Data versions on disk and in the database, plus the in-memory active dataset."""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.config import Settings
from app.core.db import Database
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.gamedata.fetch import (
    Downloaded,
    UpstreamDate,
    download_all,
    remote_etags,
    remote_timestamp,
    source_name,
    upstream_time,
)
from app.gamedata.model import GameData
from app.gamedata.transform import SCHEMA_VERSION, build_dataset
from app.gamedata.validate import (
    DatasetInvalidError,
    ValidationLimits,
    dataset_not_a_list,
    summarize_dataset,
    validate_dataset,
)
from app.models import GameDataVersion
from app.repositories.settings import set_setting

log = logging.getLogger("oak.gamedata")
KEEP_VERSIONS = 3
LAST_CHECK_KEY = "gamedata.last_check"
# The result of the last check for a newer version, so the page can keep showing it (issue #28).
REMOTE_CHECK_KEY = "gamedata.remote_check"
# The sources whose date the page shows.
DATED_SOURCES = ("pokeminers", "pvpoke")


@dataclass(frozen=True, slots=True)
class UpdateResult:
    version_id: int | None
    status: str  # activated | unchanged | failed
    message: str
    warnings: list[dict[str, Any]]
    # The message for the interface: {code, text, data} with the Dutch text (ADR-0025). A
    # failure without a code, such as a file that is no JSON, has only the text.
    text: dict[str, Any] = field(default_factory=dict)
    # Why validation failed, one message per problem; empty for any other result.
    errors: list[dict[str, Any]] = field(default_factory=list)


def _unreachable(exc: Exception) -> dict[str, Any]:
    name = type(exc).__name__
    return {"code": "SOURCE_UNREACHABLE", "text": f"Bron niet bereikbaar: {name}", "data": {"error": name}}


GAMEDATA_FILE = re.compile(r"oak-gamedata-\d+\.json\.gz")


def _date_problem(problem: Mapping[str, Any] | None) -> dict[str, Any]:
    """Why a source date is unknown, as a server text (ADR-0025)."""
    kind = (problem or {}).get("problem")
    if kind == "unreachable":
        error = str((problem or {}).get("detail") or "")
        text = f"De datum van de bron was niet bereikbaar: {error}"
        return {"code": "DATE_UNREACHABLE", "text": text, "data": {"error": error}}
    if kind == "invalid":
        return {"code": "DATE_INVALID", "text": "De bron gaf geen datum die OAK kan lezen.", "data": {}}
    return {"code": "DATE_NOT_PUBLISHED", "text": "De bron vermeldt geen datum bij deze gegevens.", "data": {}}


def source_dates(sources: list[dict[str, Any]], origin: str) -> list[dict[str, Any]]:
    """The date of the data per source of a version, or why it is unknown (issue #28)."""
    dates = []
    for source in sources:
        source_id = source.get("id")
        if source_id not in DATED_SOURCES:
            continue
        moment = upstream_time(source.get("upstream_timestamp"))
        reason: dict[str, Any] | None = None
        if moment is None:
            if source.get("upstream_timestamp") is not None:
                reason = _date_problem({"problem": "invalid"})
            elif origin == "upload":
                text = "Een geüpload bestand heeft geen datum van de bron."
                reason = {"code": "DATE_UPLOAD", "text": text, "data": {}}
            elif source_id == "pokeminers" and "upstream_problem" not in source:
                text = "Deze versie is gedownload voordat OAK de datum van de Game Master bewaarde."
                reason = {"code": "DATE_NOT_RECORDED", "text": text, "data": {}}
            else:
                reason = _date_problem(source.get("upstream_problem"))
        dates.append({"source": source_id, "date": moment.isoformat() if moment else None, "reason": reason})
    return dates


def _latest(upstream: UpstreamDate, source: str) -> dict[str, Any]:
    reason = None if upstream.at else _date_problem({"problem": upstream.problem, "detail": upstream.detail})
    return {"date": upstream.at, "reason": reason, "source": source}


class GameDataStore:
    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db
        self._lock = threading.Lock()
        self._update_lock = threading.Lock()
        self._active: GameData | None = None
        self.limits = ValidationLimits()

    # --- active dataset ---------------------------------------------------------------------

    def active(self) -> GameData | None:
        return self._active

    def load_active(self) -> GameData | None:
        with self.db.read() as session:
            version = session.scalars(select(GameDataVersion).where(GameDataVersion.status == "active")).first()
            if version is None or version.file_name is None:
                self._active = None
                return None
            version_id, file_name = version.id, version.file_name
        try:
            dataset = self._read(file_name)
        except (OSError, ValueError) as exc:
            log.error("active game data file unreadable", extra={"version": version_id, "error": str(exc)})
            self._active = None
            return None
        with self._lock:
            self._active = GameData(dataset, version_id)
        log.info("game data loaded", extra={"version": version_id})
        return self._active

    def _path(self, file_name: str) -> Path:
        # Only names OAK gives itself, so a changed database row cannot point outside the
        # Game Data directory (issue #55).
        if not GAMEDATA_FILE.fullmatch(file_name):
            msg = f"Ongeldige bestandsnaam voor Game Data: {file_name!r}"
            raise ValueError(msg)
        return self.settings.gamedata_dir / file_name

    def _read(self, file_name: str) -> dict[str, Any]:
        with gzip.open(self._path(file_name), "rt", encoding="utf-8") as handle:
            dataset = json.load(handle)
        if dataset.get("schema_version") != SCHEMA_VERSION:
            msg = f"unsupported schema_version {dataset.get('schema_version')}"
            raise ValueError(msg)
        return dataset

    # --- building versions ------------------------------------------------------------------

    def update_from_downloads(self, downloads: Mapping[str, Downloaded], *, origin: str) -> UpdateResult:
        with self._update_lock:
            active_sources = self._active_sources()
            # Unchanged sources only mean "nothing to do" while the active dataset is loaded and
            # built by the current transform. A missing or unreadable file, for example after
            # restoring only the database, is rebuilt from the same sources (audit A11), and so is
            # a dataset that lacks data a newer transform adds.
            if (
                self._active is not None
                and not self._active.outdated
                and active_sources
                and all(active_sources.get(sid) == d.sha256 for sid, d in downloads.items())
                and set(active_sources) == set(downloads)
            ):
                self._record_check(None)
                self._add_missing_date(downloads)
                unchanged = "De bronnen zijn niet gewijzigd sinds de actieve versie."
                return UpdateResult(
                    self._active.version_id if self._active else None,
                    "unchanged",
                    unchanged,
                    [],
                    {"code": "SOURCES_UNCHANGED", "text": unchanged, "data": {}},
                )
            now = datetime.now(UTC)
            try:
                game_master = downloads["pokeminers"].json()
                pvpoke = downloads["pvpoke"].json() if "pvpoke" in downloads else None
                rankings = {
                    sid.removeprefix("pvpoke-rankings-"): d.json()
                    for sid, d in downloads.items()
                    if sid.startswith("pvpoke-rankings-")
                }
                if not isinstance(game_master, list):
                    raise dataset_not_a_list()
                sources = [
                    d.source_record(pvpoke.get("timestamp") if sid == "pvpoke" and isinstance(pvpoke, dict) else None)
                    for sid, d in downloads.items()
                ]
                dataset = build_dataset(
                    game_master,
                    pvpoke=pvpoke,
                    rankings=rankings or None,
                    sources=sources,
                    generated_at=now.isoformat(),
                )
                warnings = validate_dataset(dataset, self.limits)
            # Any unexpected structure is a failed version on the page, never an error 500 (issue #47).
            except Exception as exc:
                errors = exc.errors if isinstance(exc, DatasetInvalidError) else []
                message = "; ".join(e["text"] for e in errors) if errors else (str(exc) or type(exc).__name__)
                with self.db.transaction() as session:
                    session.add(
                        GameDataVersion(
                            status="failed",
                            origin=origin,
                            schema_version=SCHEMA_VERSION,
                            sources=[d.source_record() for d in downloads.values()],
                            error=message[:2000],
                            errors=errors or None,
                            created_at=now,
                        )
                    )
                self._record_check(message)
                log.warning("game data validation failed", extra={"error": message[:300]})
                return UpdateResult(None, "failed", message, [], {"text": message}, errors)

            content = json.dumps(dataset, separators=(",", ":")).encode("utf-8")
            digest = hashlib.sha256(content).hexdigest()
            with self.db.transaction() as session:
                version = GameDataVersion(
                    status="ready",
                    origin=origin,
                    schema_version=SCHEMA_VERSION,
                    content_sha256=digest,
                    sources=dataset["sources"],
                    summary={**summarize_dataset(dataset), "warnings": warnings},
                    created_at=now,
                )
                session.add(version)
                session.flush()
                version.file_name = f"oak-gamedata-{version.id}.json.gz"
                version_id = version.id
                file_name = str(version.file_name)
            tmp = self._path(file_name).with_name(file_name + ".tmp")
            with gzip.open(tmp, "wb") as handle:
                handle.write(content)
            tmp.replace(self._path(file_name))
            self.activate(version_id)
            self._record_check(None)
            activated = "Nieuwe Game Data-versie geactiveerd."
            return UpdateResult(
                version_id,
                "activated",
                activated,
                warnings,
                {"code": "VERSION_ACTIVATED", "text": activated, "data": {}},
            )

    def update_from_network(self) -> UpdateResult:
        try:
            downloads = download_all(self.settings)
        except Exception as exc:  # network errors of every kind keep the current version
            text = _unreachable(exc)
            self._record_check(text["text"])
            log.warning("game data download failed", extra={"error": str(exc)[:300]})
            return UpdateResult(self._active.version_id if self._active else None, "failed", text["text"], [], text)
        result = self.update_from_downloads(downloads, origin="download")
        upstream = downloads["pokeminers"].upstream
        if result.status in ("activated", "unchanged") and upstream is not None:
            # The active version is now the newest there is, so the page need not say otherwise.
            self._save_remote_check(
                {"available": False, "changed_sources": [], "repair_needed": False, "error": None},
                upstream,
            )
        return result

    def update_from_upload(self, files: Mapping[str, bytes]) -> UpdateResult:
        if "pokeminers" not in files:
            raise ValidationFailedError(
                "Een Game Master-bestand (GAME_MASTER.json of latest.json) is verplicht.",
                context="game_master_required",
            )
        now = datetime.now(UTC).isoformat()
        downloads = {
            sid: Downloaded(id=sid, url="upload", content=content, etag=None, retrieved_at=now)
            for sid, content in files.items()
        }
        return self.update_from_downloads(downloads, origin="upload")

    def activate(self, version_id: int) -> None:
        with self.db.immediate_transaction() as session:
            target = session.get(GameDataVersion, version_id)
            if target is None:
                raise NotFoundError("Game Data-versie niet gevonden.", context="game_data_version")
            if target.status not in ("ready", "archived", "active") or not target.file_name:
                raise ConflictError("Deze versie kan niet geactiveerd worden.", context="version_not_activatable")
            if not self._path(target.file_name).exists():
                raise ConflictError(
                    "Het bestand van deze versie is niet meer aanwezig.", context="version_file_missing"
                )
            for version in session.scalars(select(GameDataVersion).where(GameDataVersion.status == "active")):
                if version.id != version_id:
                    version.status = "archived"
            target.status = "active"
            target.activated_at = datetime.now(UTC)
        self.load_active()
        self._prune()

    def _prune(self) -> None:
        with self.db.transaction() as session:
            keep = session.scalars(
                select(GameDataVersion)
                .where(GameDataVersion.status.in_(("active", "archived", "ready")))
                .order_by(GameDataVersion.id.desc())
            ).all()
            for version in keep[KEEP_VERSIONS:]:
                if version.status == "active":
                    continue
                if version.file_name:
                    self._path(version.file_name).unlink(missing_ok=True)
                version.status = "pruned"
                version.file_name = None

    def _active_sources(self) -> dict[str, str]:
        with self.db.read() as session:
            version = session.scalars(select(GameDataVersion).where(GameDataVersion.status == "active")).first()
            if version is None:
                return {}
            return {s["id"]: s["sha256"] for s in version.sources if "id" in s and "sha256" in s}

    def _add_missing_date(self, downloads: Mapping[str, Downloaded]) -> None:
        """An active version from before OAK kept the date of the Game Master gets it from a download
        with the same content: the date belongs to that content."""
        upstream = downloads["pokeminers"].upstream if "pokeminers" in downloads else None
        if upstream is None or upstream.at is None:
            return
        with self.db.transaction() as session:
            version = session.scalars(select(GameDataVersion).where(GameDataVersion.status == "active")).first()
            if version is None:
                return
            sources = [dict(source) for source in version.sources]
            for source in sources:
                if (
                    source.get("id") == "pokeminers"
                    and not source.get("upstream_timestamp")
                    and source.get("sha256") == downloads["pokeminers"].sha256
                ):
                    source["upstream_timestamp"] = upstream.at
                    source.pop("upstream_problem", None)
                    version.sources = sources

    def _save_remote_check(self, result: Mapping[str, Any], upstream: UpstreamDate) -> dict[str, Any]:
        source = source_name(self.settings.gamedata_pokeminers_url)
        record = {**result, "checked_at": datetime.now(UTC).isoformat(), "latest": _latest(upstream, source)}
        with self.db.transaction() as session:
            set_setting(session, REMOTE_CHECK_KEY, record)
        return record

    def _record_check(self, error: str | None) -> None:
        with self.db.transaction() as session:
            set_setting(
                session,
                LAST_CHECK_KEY,
                {"at": datetime.now(UTC).isoformat(), "error": error},
            )

    def check_remote(self) -> dict[str, Any]:
        """Compare upstream ETags with the active version without downloading the files, and read
        the date of the newest Game Master. The requests run outside any transaction; only the
        result is written, so the page keeps showing it (issue #28)."""
        upstream = remote_timestamp(self.settings)
        try:
            etags = remote_etags(self.settings)
        except Exception as exc:  # report, do not raise: the page must still render
            # The error is a server text: {code, text, data} (ADR-0025).
            return self._save_remote_check({"available": None, "error": _unreachable(exc)}, upstream)
        with self.db.read() as session:
            version = session.scalars(select(GameDataVersion).where(GameDataVersion.status == "active")).first()
            sources = list(version.sources) if version else []
        known = {s["id"]: s.get("etag") for s in sources}
        changed = [sid for sid, tag in etags.items() if tag is None or known.get(sid) != tag]
        # A newer date at the source counts too, also when the ETags say nothing new.
        active_date = next(
            (upstream_time(s.get("upstream_timestamp")) for s in sources if s.get("id") == "pokeminers"), None
        )
        latest_date = upstream_time(upstream.at)
        if active_date and latest_date and latest_date > active_date and "pokeminers" not in changed:
            changed.append("pokeminers")
        repair = version is not None and (self._active is None or self._active.outdated)
        result = {
            "available": bool(changed) or version is None or repair,
            "changed_sources": changed,
            "repair_needed": repair,
            "error": None,
        }
        return self._save_remote_check(result, upstream)
