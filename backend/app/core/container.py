"""Process-wide services, created once by the application lifespan."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime

from app.core.clock import Clock
from app.core.config import Settings
from app.core.db import Database
from app.core.ratelimit import SlidingWindowLimiter
from app.gamedata.store import GameDataStore
from app.ingestion.processor import ImportProcessor
from app.jobs.runner import JobRunner
from app.services.releases import ReleaseCheck

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
INVALID_TOKEN_LIMIT = 20
INVALID_TOKEN_WINDOW_SECONDS = 600
# Failed logins for one username, from any address, before OAK slows down attempts on it, as a
# multiple of OAK_LOGIN_MAX_ATTEMPTS. Slowed down means one attempt per SLOW_LOGIN_SECONDS: it never
# locks the user out, so someone else cannot block an account by guessing at it.
USERNAME_LIMIT_FACTOR = 5
SLOW_LOGIN_SECONDS = 5
# Manual uploads, retries and confirmations per user per hour (issue #45). The webhook has its own
# limit per token (OAK_WEBHOOK_RATE_LIMIT_PER_HOUR).
USER_IMPORTS_PER_HOUR = 30
# Exports read and stored at the same time. More wait their turn, so a burst of large exports
# cannot together use more memory than two do.
IMPORT_SLOTS = 2


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
    login_by_pair: SlidingWindowLimiter = field(init=False)
    login_by_ip: SlidingWindowLimiter = field(init=False)
    login_by_user: SlidingWindowLimiter = field(init=False)
    login_slow_by_user: SlidingWindowLimiter = field(init=False)
    password_checks_by_user: SlidingWindowLimiter = field(init=False)
    imports_by_user: SlidingWindowLimiter = field(init=False)
    webhook_by_token: SlidingWindowLimiter = field(init=False)
    webhook_invalid_by_ip: SlidingWindowLimiter = field(init=False)
    import_slots: threading.BoundedSemaphore = field(init=False)
    releases: ReleaseCheck = field(init=False)

    def __post_init__(self) -> None:
        window = self.settings.login_window_minutes * SECONDS_PER_MINUTE
        attempts = self.settings.login_max_attempts
        # Blocks a username from one address, and an address for every username.
        self.login_by_pair = SlidingWindowLimiter(attempts, window)
        self.login_by_ip = SlidingWindowLimiter(attempts * 3, window)
        # Only slows down a username that fails from many addresses.
        self.login_by_user = SlidingWindowLimiter(attempts * USERNAME_LIMIT_FACTOR, window)
        self.login_slow_by_user = SlidingWindowLimiter(1, SLOW_LOGIN_SECONDS)
        # Wrong current passwords when changing the password, per user (issue #41).
        self.password_checks_by_user = SlidingWindowLimiter(attempts, window)
        self.imports_by_user = SlidingWindowLimiter(USER_IMPORTS_PER_HOUR, SECONDS_PER_HOUR)
        self.webhook_by_token = SlidingWindowLimiter(self.settings.webhook_rate_limit_per_hour, SECONDS_PER_HOUR)
        self.webhook_invalid_by_ip = SlidingWindowLimiter(INVALID_TOKEN_LIMIT, INVALID_TOKEN_WINDOW_SECONDS)
        self.import_slots = threading.BoundedSemaphore(IMPORT_SLOTS)
        self.releases = ReleaseCheck(self.settings)
