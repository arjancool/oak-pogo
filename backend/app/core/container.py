"""Process-wide services, created once by the application lifespan."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.core.clock import Clock
from app.core.config import Settings
from app.core.db import Database
from app.core.ratelimit import SlidingWindowLimiter
from app.gamedata.store import GameDataStore
from app.ingestion.processor import ImportProcessor
from app.jobs.runner import JobRunner

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
INVALID_TOKEN_LIMIT = 20
INVALID_TOKEN_WINDOW_SECONDS = 600


@dataclass
class Container:
    settings: Settings
    db: Database
    clock: Clock
    secret: str
    secret_generated: bool
    gamedata: GameDataStore
    runner: JobRunner
    processor: ImportProcessor
    started_at: datetime
    sprite_template: str = ""
    login_by_user: SlidingWindowLimiter = field(init=False)
    login_by_ip: SlidingWindowLimiter = field(init=False)
    webhook_by_token: SlidingWindowLimiter = field(init=False)
    webhook_invalid_by_ip: SlidingWindowLimiter = field(init=False)

    def __post_init__(self) -> None:
        window = self.settings.login_window_minutes * SECONDS_PER_MINUTE
        self.login_by_user = SlidingWindowLimiter(self.settings.login_max_attempts, window)
        self.login_by_ip = SlidingWindowLimiter(self.settings.login_max_attempts * 3, window)
        self.webhook_by_token = SlidingWindowLimiter(self.settings.webhook_rate_limit_per_hour, SECONDS_PER_HOUR)
        self.webhook_invalid_by_ip = SlidingWindowLimiter(INVALID_TOKEN_LIMIT, INVALID_TOKEN_WINDOW_SECONDS)
