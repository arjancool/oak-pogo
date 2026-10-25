"""Background task handlers and periodic maintenance."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.ingestion.derive import apply_derived
from app.ingestion.receive import load_payload, write_payload
from app.models import AnalysisRun, BackgroundJob, ImportJob, Pokemon, TrainerAccount
from app.normalizers.sanitize import SANITIZER_REVISION, sanitize_export
from app.recommendations.rules import ENGINE_VERSION
from app.repositories.settings import get_setting, set_setting
from app.services.analysis import AnalysisService, rules_for
from app.services.events import FEED_KEY, update_events

if TYPE_CHECKING:
    from app.core.container import Container

log = logging.getLogger("oak.jobs")
REDERIVE_BATCH = 500


def register_tasks(container: Container) -> None:
    runner = container.runner
    analysis = AnalysisService(container.settings, container.db, container.gamedata, container.clock)

    def import_task(job: BackgroundJob) -> None:
        if job.ref_id is not None:
            container.processor.process(job.ref_id)

    def analysis_task(job: BackgroundJob) -> None:
        if job.trainer_account_id is not None:
            analysis.run(job.trainer_account_id)

    def gamedata_task(_: BackgroundJob) -> None:
        result = container.gamedata.update_from_network()
        if result.status == "activated":
            enqueue_rederive(container)

    def rederive_task(_: BackgroundJob) -> None:
        rederive_all(container)

    def events_task(_: BackgroundJob) -> None:
        update_events(container.settings, container.db, container.clock.now())
        schedule_event_analyses(container, analysis)

    runner.register("import", import_task)
    runner.register("analysis", analysis_task)
    runner.register("gamedata_update", gamedata_task)
    runner.register("rederive", rederive_task)
    runner.register("events_update", events_task)
    runner.maintenance.append(lambda: resanitize_payloads(container))
    runner.maintenance.append(lambda: purge_payloads(container))
    runner.maintenance.append(lambda: schedule_gamedata_check(container))
    runner.maintenance.append(lambda: schedule_events_check(container))
    # Holds start when an event comes within reach and end with the event (ADR-0021).
    runner.maintenance.append(lambda: schedule_event_analyses(container, analysis))


def enqueue(container: Container, kind: str, account_id: int | None = None) -> None:
    with container.db.transaction() as session:
        pending = session.scalar(
            select(BackgroundJob.id)
            .where(
                BackgroundJob.kind == kind,
                BackgroundJob.status == "queued",
                BackgroundJob.trainer_account_id.is_(None)
                if account_id is None
                else BackgroundJob.trainer_account_id == account_id,
            )
            .limit(1)
        )
        if pending is None:
            session.add(
                BackgroundJob(
                    kind=kind,
                    status="queued",
                    trainer_account_id=account_id,
                    created_at=container.clock.now(),
                )
            )
    container.runner.notify()


def enqueue_rederive(container: Container) -> None:
    enqueue(container, "rederive")


def rederive_all(container: Container) -> None:
    """Recompute derived columns for every Pokémon after a Game Data switch, then re-run the
    analyses, so recommendations always state the dataset version they were built on."""
    gd = container.gamedata.active()
    with container.db.transaction() as session:
        account_ids = list(session.scalars(select(TrainerAccount.id)))
    for account_id in account_ids:
        last_id = 0
        while True:
            with container.db.immediate_transaction() as session:
                rows = session.scalars(
                    select(Pokemon)
                    .where(Pokemon.trainer_account_id == account_id, Pokemon.id > last_id)
                    .order_by(Pokemon.id)
                    .limit(REDERIVE_BATCH)
                ).all()
                for row in rows:
                    apply_derived(row, gd, container.settings.tz)
                if not rows:
                    break
                last_id = rows[-1].id
        enqueue(container, "analysis", account_id)
    log.info("derived columns recomputed", extra={"accounts": len(account_ids)})


def schedule_events_check(container: Container) -> None:
    settings = container.settings
    if not settings.events_auto_update:
        return
    with container.db.read() as session:
        state = get_setting(session, FEED_KEY) or {}
    if state.get("checked_at"):
        last = datetime.fromisoformat(state["checked_at"])
        if container.clock.now() - last < timedelta(hours=settings.events_update_interval_hours):
            return
    enqueue(container, "events_update")


def schedule_event_analyses(container: Container, analysis: AnalysisService) -> None:
    """Queue an analysis for every account whose advice was computed before the events within
    reach changed. Accounts without an analysis get one with their first import."""
    with container.db.read() as session:
        latest = (
            select(AnalysisRun.trainer_account_id, func.max(AnalysisRun.id).label("run_id"))
            .where(AnalysisRun.status == "done")
            .group_by(AnalysisRun.trainer_account_id)
            .subquery()
        )
        runs = session.execute(
            select(AnalysisRun.trainer_account_id, AnalysisRun.input_fingerprint).join(
                latest, AnalysisRun.id == latest.c.run_id
            )
        ).all()
        stale = []
        for account_id, fingerprint in runs:
            account = session.get(TrainerAccount, account_id)
            if account is not None and analysis.input_fingerprint(session, account, rules_for(account)) != fingerprint:
                stale.append(account_id)
    for account_id in stale:
        enqueue(container, "analysis", account_id)
    if stale:
        log.info("analyses queued after an event change", extra={"accounts": len(stale)})


SANITIZER_KEY = "imports.sanitizer_revision"


def resanitize_payloads(container: Container) -> None:
    """Filter stored exports again after the filter was tightened, once per revision.

    Stored exports stay for OAK_RAW_IMPORT_RETENTION_DAYS. Waiting for that would keep fields the
    current filter drops on disk for up to that long (audit A05, re-check of 24 October).
    """
    with container.db.read() as session:
        if (get_setting(session, SANITIZER_KEY) or 0) >= SANITIZER_REVISION:
            return
        files = set(
            session.scalars(
                select(ImportJob.payload_file).where(
                    ImportJob.payload_file.is_not(None), ImportJob.payload_purged_at.is_(None)
                )
            )
        )
    imports_dir = container.settings.imports_dir
    rewritten = 0
    for file_name in sorted(str(f) for f in files):
        if not (imports_dir / file_name).exists():
            continue
        try:
            data = load_payload(imports_dir, file_name)
        except (OSError, ValueError) as exc:
            # Unreadable files cannot be processed either. Keep them for diagnosis; they expire.
            log.warning("stored export unreadable", extra={"file": file_name, "error": type(exc).__name__})
            continue
        write_payload(imports_dir, file_name, sanitize_export(data))
        rewritten += 1
    with container.db.transaction() as session:
        set_setting(session, SANITIZER_KEY, SANITIZER_REVISION)
    log.info("stored exports filtered again", extra={"count": rewritten, "revision": SANITIZER_REVISION})


def purge_payloads(container: Container) -> None:
    """Delete stored (sanitized) exports older than OAK_RAW_IMPORT_RETENTION_DAYS."""
    days = container.settings.raw_import_retention_days
    cutoff = container.clock.now() - timedelta(days=days)
    with container.db.transaction() as session:
        jobs = session.scalars(
            select(ImportJob).where(
                ImportJob.payload_file.is_not(None),
                ImportJob.payload_purged_at.is_(None),
                ImportJob.received_at < cutoff,
                ImportJob.status.not_in(("queued", "processing")),
            )
        ).all()
        files = {j.payload_file for j in jobs}
        still_needed = set(
            session.scalars(
                select(ImportJob.payload_file).where(
                    ImportJob.payload_file.in_(files),
                    ImportJob.status.in_(("queued", "processing")),
                )
            )
        )
        for job in jobs:
            if job.payload_file in still_needed:
                continue
            (container.settings.imports_dir / str(job.payload_file)).unlink(missing_ok=True)
            job.payload_purged_at = container.clock.now()
    if jobs:
        log.info("purged stored exports", extra={"count": len(jobs), "retention_days": days})


def schedule_gamedata_check(container: Container) -> None:
    settings = container.settings
    if not settings.gamedata_auto_update:
        return
    active = container.gamedata.active()
    if active is None or active.outdated:
        # No usable or a dataset from an older transform: rebuild now instead of waiting for
        # the interval (audit A11).
        enqueue(container, "gamedata_update")
        return
    with container.db.transaction() as session:
        last = get_setting(session, "gamedata.last_check")
    if last and last.get("at"):
        last_at = datetime.fromisoformat(last["at"])
        if container.clock.now() - last_at < timedelta(hours=settings.gamedata_update_interval_hours):
            return
    enqueue(container, "gamedata_update")


def schedule_outdated_analyses(container: Container) -> int:
    """Queue a new analysis for every account whose latest analysis was made by another engine
    version. Runs at startup, so an upgrade recomputes all recommendations by itself."""
    with container.db.read() as session:
        latest = (
            select(AnalysisRun.trainer_account_id, func.max(AnalysisRun.id).label("run_id"))
            .where(AnalysisRun.status == "done")
            .group_by(AnalysisRun.trainer_account_id)
            .subquery()
        )
        outdated = list(
            session.scalars(
                select(latest.c.trainer_account_id)
                .join(AnalysisRun, AnalysisRun.id == latest.c.run_id)
                .where(AnalysisRun.engine_version != ENGINE_VERSION)
            )
        )
    for account_id in outdated:
        enqueue(container, "analysis", account_id)
    if outdated:
        log.info(
            "analyses queued for a new engine version",
            extra={"accounts": len(outdated), "engine": ENGINE_VERSION},
        )
    return len(outdated)
