"""Runtime configuration, read from ``OAK_*`` environment variables.

Every setting has a documented default in ``docs/DEPLOYMENT.md``. Nothing here falls back
silently: an invalid value fails at startup with a message naming the variable.
"""

from __future__ import annotations

import ipaddress
import secrets
from functools import cached_property
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SECRET_KEY_LENGTH = 32
SECRET_KEY_FILENAME = ".secret_key"
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
    max_import_mb: int = Field(default=64, ge=1, le=1024)
    session_idle_hours: int = Field(default=168, ge=1)
    session_max_days: int = Field(default=30, ge=1)
    login_max_attempts: int = Field(default=10, ge=1)
    login_window_minutes: int = Field(default=15, ge=1)
    webhook_rate_limit_per_hour: int = Field(default=60, ge=1)
    gamedata_auto_update: bool = True
    gamedata_update_interval_hours: int = Field(default=24, ge=1)
    gamedata_pokeminers_url: str = "https://raw.githubusercontent.com/PokeMiners/game_masters/master/latest/latest.json"
    gamedata_pvpoke_base_url: str = "https://raw.githubusercontent.com/pvpoke/pvpoke/master/src/data"
    gamedata_timeout_seconds: int = Field(default=120, ge=5)
    # Event calendar of LeekDuck.com, published as JSON by ScrapedDuck (ADR-0021).
    events_auto_update: bool = True
    events_update_interval_hours: int = Field(default=12, ge=1)
    events_url: str = "https://raw.githubusercontent.com/bigfoott/ScrapedDuck/data/events.json"
    sprite_url_template: str = ""
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
            directory.mkdir(parents=True, exist_ok=True)

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
            stored = path.read_text(encoding="utf-8").strip()
            if len(stored) >= MIN_SECRET_KEY_LENGTH:
                return stored, True
        generated = secrets.token_urlsafe(48)
        path.write_text(generated, encoding="utf-8")
        path.chmod(0o600)
        return generated, True


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]
