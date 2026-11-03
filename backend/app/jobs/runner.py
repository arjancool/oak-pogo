"""In-process background worker with a durable queue (ADR-0014).

One worker thread takes jobs from ``background_jobs`` in order. Because there is a single
worker, imports for one account never run concurrently. Jobs left ``running`` by a crash or
restart are put back in the queue at startup; their work ran in a transaction that was never
committed, so running them again is safe. A job that was interrupted ``MAX_ATTEMPTS`` times
fails instead, so a job that keeps stopping OAK does not start again at every restart.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.db import Database
from app.models import BackgroundJob, ImportJob, TrainerAccount

log = logging.getLogger("oak.jobs")
Handler = Callable[[BackgroundJob], None]
IDLE_WAIT_SECONDS = 30.0
MAINTENANCE_INTERVAL = timedelta(hours=1)
MAX_ATTEMPTS = 3


class JobRunner:
    def __init__(self, db: Database, clock: Clock) -> None:
        self.db = db
        self.clock = clock
        self.handlers: dict[str, Handler] = {}
        self.maintenance: list[Callable[[], None]] = []
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_maintenance = None

    def register(self, kind: str, handler: Handler) -> None:
        self.handlers[kind] = handler

    def recover(self) -> int:
        """Re-queue work interrupted by a restart, or stop it after ``MAX_ATTEMPTS`` attempts."""
        now = self.clock.now()
        with self.db.transaction() as session:
            stopped = session.scalars(
                select(BackgroundJob).where(BackgroundJob.status == "running", BackgroundJob.attempts >= MAX_ATTEMPTS)
            ).all()
            for stuck in stopped:
                _give_up(session, stuck, now)
            session.flush()
            jobs = session.execute(
                update(BackgroundJob).where(BackgroundJob.status == "running").values(status="queued")
            )
            session.execute(
                update(ImportJob).where(ImportJob.status == "processing").values(status="queued", stage="queued")
            )
            count = jobs.rowcount or 0  # type: ignore[attr-defined]
        if stopped:
            log.warning("stopped jobs interrupted too often", extra={"count": len(stopped)})
        if count:
            log.info("re-queued interrupted jobs", extra={"count": count})
        return count

    def notify(self) -> None:
        self._wake.set()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="oak-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = self.run_once()
                self._maybe_maintenance()
            except Exception:
                log.exception("worker loop error")
                worked = False
            if not worked:
                self._wake.wait(IDLE_WAIT_SECONDS)
                self._wake.clear()

    def _maybe_maintenance(self) -> None:
        now = self.clock.now()
        if self._last_maintenance is not None and now - self._last_maintenance < MAINTENANCE_INTERVAL:
            return
        self._last_maintenance = now
        for task in self.maintenance:
            try:
                task()
            except Exception:
                log.exception("maintenance task failed")

    def run_once(self) -> bool:
        """Claim and run the oldest queued job. Returns whether a job ran."""
        with self.db.immediate_transaction() as session:
            job = session.scalars(
                select(BackgroundJob).where(BackgroundJob.status == "queued").order_by(BackgroundJob.id).limit(1)
            ).first()
            if job is None:
                return False
            job.status = "running"
            job.started_at = self.clock.now()
            job.attempts += 1
            session.flush()
            session.expunge(job)
        handler = self.handlers.get(job.kind)
        error: str | None = None
        if handler is None:
            error = f"geen verwerker voor taaktype '{job.kind}'"
        else:
            try:
                handler(job)
            except Exception as exc:
                log.exception("job failed", extra={"job_id": job.id, "kind": job.kind})
                error = f"{type(exc).__name__}"
        with self.db.transaction() as session:
            stored = session.get(BackgroundJob, job.id)
            if stored is not None:
                stored.status = "failed" if error else "done"
                stored.error = error
                stored.progress = 100
                stored.finished_at = self.clock.now()
        return True

    def drain(self, limit: int = 100) -> int:
        """Run queued jobs synchronously. Used by tests and the CLI."""
        count = 0
        while count < limit and self.run_once():
            count += 1
        return count


def interrupted_message(attempts: int) -> dict[str, Any]:
    return {
        "code": "PROCESSING_INTERRUPTED",
        "message": (
            f"De verwerking is {attempts} keer onderbroken, bijvoorbeeld door een herstart of te weinig "
            "geheugen. OAK probeert het niet opnieuw. Er is niets gewijzigd."
        ),
        "data": {"attempts": attempts},
    }


def _give_up(session: Session, job: BackgroundJob, now: datetime) -> None:
    """Fail a job that was interrupted too often, and the import it was processing."""
    text = interrupted_message(job.attempts)
    job.status = "failed"
    job.error = text["message"]
    job.progress = 100
    job.finished_at = now
    if job.kind != "import" or job.ref_id is None:
        return
    imported = session.get(ImportJob, job.ref_id)
    if imported is None or imported.status not in ("queued", "processing"):
        return
    imported.status = "failed"
    imported.stage = "done"
    imported.error_code = text["code"]
    imported.error_message = text["message"]
    imported.error_data = text["data"]
    imported.finished_at = now
    account = session.get(TrainerAccount, imported.trainer_account_id)
    if account is not None:
        account.sync_status = "error"
