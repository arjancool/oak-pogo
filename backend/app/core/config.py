"""Runtime configuration, read from ``OAK_*`` environment variables.

Every setting has a documented default in ``docs/DEPLOYMENT.md``. Nothing here falls back
silently: an invalid value fails at startup with a message naming the variable.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import secrets
from functools import cached_property
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SECRET_KEY_LENGTH = 32
SECRET_KEY_FILENAME = ".secret_key"
# Only OAK itself reads the data directory and the key (issue #43).
PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
# POSIX file modes; on Windows they mean something else and OAK leaves them alone.
POSIX = os.name == "posix"
log = logging.getLogger("oak.config")


class SecretKeyFileError(RuntimeError):
    """The stored key is unusable. OAK refuses to start rather than make a new one silently."""


BYTES_PER_MEGABYTE = 1024 * 1024


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OAK_", extra="ignore")

    env: Literal["production", "development", "test"] = "production"
    base_url: str = "http://localhost:8080"
    data_dir: Path = Path("/data")
    port: int = Field(default=8080, ge=1, le=65535)
    timezone: str = "Europe/Amsterdam"
    secret_key: str | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    allow_registration: bool = False
    trusted_proxy_cidrs: str = ""
    raw_import_retention_days: int = Field(default=14, ge=0, le=3650)
    # How long the audit log keeps an entry (issue #55).
    audit_retention_days: int = Field(default=365, ge=1, le=3650)
    max_import_mb: int = Field(default=64, ge=1, le=1024)
    session_idle_hours: int = Field(default=168, ge=1)
    session_max_days: int = Field(default=30, ge=1)
    login_max_attempts: int = Field(default=10, ge=1)
    login_window_minutes: int = Field(default=15, ge=1)
    webhook_rate_limit_per_hour: int = Field(default=60, ge=1)
    gamedata_auto_update: bool = True
    gamedata_update_interval_hours: int = Field(default=24, ge=1)
    # The Game Master. The name is older than the source: alexelgt is the default (ADR-0028), and
    # PokeMiners' latest/latest.json works too.
    gamedata_pokeminers_url: str = "https://raw.githubusercontent.com/alexelgt/game_masters/master/GAME_MASTER.json"
    gamedata_pvpoke_base_url: str = "https://raw.githubusercontent.com/pvpoke/pvpoke/master/src/data"
    gamedata_timeout_seconds: int = Field(default=120, ge=5)
    # Event calendar of LeekDuck.com, published as JSON by ScrapedDuck (ADR-0021).
    events_auto_update: bool = True
    events_update_interval_hours: int = Field(default=12, ge=1)
    events_url: str = "https://raw.githubusercontent.com/bigfoott/ScrapedDuck/data/events.json"
    sprite_url_template: str = ""
    # The newest OAK release on GitHub, for the owner on the settings page (issue #29).
    release_check: bool = True
    release_check_hours: int = Field(default=12, ge=1)
    start_worker: bool = True
    frontend_dir: Path | None = None

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            msg = f"OAK_TIMEZONE '{value}' is geen geldige IANA-tijdzone"
            raise ValueError(msg) from exc
        return value

    @field_validator("base_url")
    @classmethod
    def _valid_base_url(cls, value: str) -> str:
        value = value.rstrip("/")
        if not value.startswith(("http://", "https://")):
            msg = "OAK_BASE_URL moet met http:// of https:// beginnen"
            raise ValueError(msg)
        return value

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def _valid_cidrs(cls, value: str) -> str:
        for part in _split_csv(value):
            try:
                ipaddress.ip_network(part, strict=False)
            except ValueError as exc:
                msg = f"OAK_TRUSTED_PROXY_CIDRS bevat een ongeldig netwerk: '{part}'"
                raise ValueError(msg) from exc
        return value

    @field_validator("gamedata_pokeminers_url", "gamedata_pvpoke_base_url", "events_url")
    @classmethod
    def _https_source(cls, value: str) -> str:
        # Downloads from outside go over https only (issue #49).
        if not value.startswith("https://"):
            msg = f"Een bron voor Game Data of events moet met https:// beginnen: '{value}'"
            raise ValueError(msg)
        return value

    @field_validator("secret_key")
    @classmethod
    def _valid_secret(cls, value: str | None) -> str | None:
        if value is not None and value.strip() == "":
            return None
        if value is not None and len(value) < MIN_SECRET_KEY_LENGTH:
            msg = f"OAK_SECRET_KEY moet minimaal {MIN_SECRET_KEY_LENGTH} tekens lang zijn"
            raise ValueError(msg)
        return value

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def secure_cookies(self) -> bool:
        return self.base_url.startswith("https://")

    @property
    def database_path(self) -> Path:
        return self.data_dir / "oak.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"

    @property
    def imports_dir(self) -> Path:
        return self.data_dir / "imports"

    @property
    def gamedata_dir(self) -> Path:
        return self.data_dir / "gamedata"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def max_import_bytes(self) -> int:
        return self.max_import_mb * BYTES_PER_MEGABYTE

    @property
    def trusted_proxies(self) -> list[str]:
        return _split_csv(self.trusted_proxy_cidrs)

    @cached_property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def ensure_directories(self) -> None:
        for directory in (self.data_dir, self.imports_dir, self.gamedata_dir, self.backups_dir):
            directory.mkdir(parents=True, exist_ok=True, mode=PRIVATE_DIR_MODE)
        # The database, back-ups, imports and the key are for OAK alone. A data directory that
        # others can read is closed, which also covers the files made before this was in place.
        _restrict(self.data_dir, PRIVATE_DIR_MODE)

    def resolve_secret_key(self) -> tuple[str, bool]:
        """Return the secret key and whether it was generated and stored in the data directory.

        A configured ``OAK_SECRET_KEY`` always wins. Without one, OAK creates a random key once
        and keeps it in ``<data_dir>/.secret_key`` (mode 0600), so sessions and fingerprints stay
        valid across restarts. The status page reports which of the two is in use.
        """
        if self.secret_key:
            return self.secret_key, False
        path = self.data_dir / SECRET_KEY_FILENAME
        if path.exists():
            return _read_secret_file(path), True
        generated = secrets.token_urlsafe(48)
        _write_secret_file(path, generated)
        return generated, True


def _read_secret_file(path: Path) -> str:
    """A stored key that is empty or too short is never replaced: a new key would end every
    session and change which trainer account an export belongs to, without anyone noticing."""
    stored = path.read_text(encoding="utf-8").strip()
    if len(stored) < MIN_SECRET_KEY_LENGTH:
        msg = (
            f"Het bestand {path} bevat geen geldige geheime sleutel: hij is leeg of korter dan "
            f"{MIN_SECRET_KEY_LENGTH} tekens. OAK start niet, want een nieuwe sleutel laat alle "
            "sessies vervallen en verandert de koppeling tussen exports en traineraccounts. Zet de "
            "juiste sleutel terug uit een back-up, of verwijder het bestand om bewust een nieuwe "
            "sleutel te laten maken."
        )
        raise SecretKeyFileError(msg)
    _restrict(path, PRIVATE_FILE_MODE)
    return stored


def _write_secret_file(path: Path, value: str) -> None:
    """Write through a temporary file that has mode 0600 from the moment it exists, then put it
    in place in one step. The key is never on disk with wider rights, and never half written."""
    tmp = path.with_name(f"{path.name}.{secrets.token_hex(4)}.tmp")
    descriptor = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, PRIVATE_FILE_MODE)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _restrict(path: Path, mode: int) -> None:
    """Take away the rights of group and others. Logs, but does not stop OAK, when that fails,
    for example on a directory that belongs to another user."""
    if not POSIX:
        return
    current = path.stat().st_mode & 0o777
    if current & ~mode == 0:
        return
    try:
        path.chmod(mode)
    except OSError as exc:
        details = {"path": str(path), "mode": oct(current), "error": type(exc).__name__}
        log.warning("could not restrict permissions", extra=details)
        return
    log.warning("permissions restricted", extra={"path": str(path), "was": oct(current), "now": oct(mode)})


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]
