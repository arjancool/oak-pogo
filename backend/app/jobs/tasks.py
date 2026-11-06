"""Background task handlers and periodic maintenance."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.exc import OperationalError

from app.ingestion.derive import DERIVE_REVISION, apply_derived
from app.ingestion.receive import load_payload, write_payload
from app.models import AnalysisRun, AuditLog, BackgroundJob, ImportJob, Pokemon, TrainerAccount, UserSession
from app.normalizers.sanitize import SANITIZER_REVISION, sanitize_export
from app.recommendations.rules import ENGINE_VERSION
from app.repositories.settings import get_setting, set_setting
from app.services.analysis import AnalysisService, rules_for
from app.services.events import FEED_KEY, update_events

if TYPE_CHECKING:
    from app.core.container import Container

log = logging.getLogger("oak.jobs")
REDERIVE_BATCH = 500
# A busy database is worth one more try before the job counts as failed (audit F06).
ANALYSIS_ATTEMPTS = 2


def register_tasks(container: Container) -> None:
    runner = container.runner
    analysis = AnalysisService(container.settings, container.db, container.gamedata, container.clock)

    def import_task(job: BackgroundJob) -> None:
        if job.ref_id is not None:
            container.processor.process(job.ref_id)

    def analysis_task(job: BackgroundJob) -> None:
        if job.trainer_account_id is None:
            return
        for attempt in range(1, ANALYSIS_ATTEMPTS + 1):
            try:
                analysis.run(job.trainer_account_id)
                return
            except OperationalError as exc:
                if attempt == ANALYSIS_ATTEMPTS or "locked" not in str(exc):
                    raise
                log.warning("analysis retried after a database conflict", extra={"account_id": job.trainer_account_id})

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
    runner.maintenance.append(lambda: refresh_derived(container))
    runner.maintenance.append(lambda: purge_payloads(container))
    runner.maintenance.append(lambda: purge_audit_and_sessions(container))
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


def refresh_derived(container: Container) -> None:
    """Recompute every derived column once after a fix in how they are derived."""
    with container.db.read() as session:
        if (get_setting(session, DERIVE_KEY) or 0) >= DERIVE_REVISION:
            return
    enqueue_rederive(container)
    with container.db.transaction() as session:
        set_setting(session, DERIVE_KEY, DERIVE_REVISION)


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
DERIVE_KEY = "pokemon.derive_revision"


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
    """Delete stored (sanitized) exports older than OAK_RAW_IMPORT_RETENTION_DAYS.

    A retry uses the file of the import it retries. So the retention period of a file counts
    from the newest import that uses it, and a file goes only when no import that uses it is
    waiting or running. All imports that used it are then marked as purged (issue #35)."""
    days = container.settings.raw_import_retention_days
    now = container.clock.now()
    cutoff = now - timedelta(days=days)
    active = case((ImportJob.status.in_(("queued", "processing")), 1), else_=0)
    with container.db.transaction() as session:
        usage = session.execute(
            select(ImportJob.payload_file, func.max(ImportJob.received_at), func.max(active))
            .where(ImportJob.payload_file.is_not(None), ImportJob.payload_purged_at.is_(None))
            .group_by(ImportJob.payload_file)
        ).all()
        expired = [str(name) for name, newest, in_use in usage if newest < cutoff and not in_use]
        for name in expired:
            (container.settings.imports_dir / name).unlink(missing_ok=True)
        if expired:
            session.execute(
                update(ImportJob)
                .where(ImportJob.payload_file.in_(expired), ImportJob.payload_purged_at.is_(None))
                .values(payload_purged_at=now)
            )
    if expired:
        log.info("purged stored exports", extra={"count": len(expired), "retention_days": days})


# An ended session stays this long before it is deleted, so a recent logout can still be traced.
ENDED_SESSION_DAYS = 30


def _deleted(result: object) -> int:
    """How many rows a DELETE removed."""
    return int(getattr(result, "rowcount", 0) or 0)


def purge_audit_and_sessions(container: Container) -> None:
    """Delete audit entries older than OAK_AUDIT_RETENTION_DAYS, and sessions that ended more than
    ENDED_SESSION_DAYS ago: revoked, past their absolute end, or idle for longer than allowed
    (issue #55)."""
    settings = container.settings
    now = container.clock.now()
    audit_cutoff = now - timedelta(days=settings.audit_retention_days)
    ended = now - timedelta(days=ENDED_SESSION_DAYS)
    idle_ended = ended - timedelta(hours=settings.session_idle_hours)
    with container.db.transaction() as session:
        audits = _deleted(session.execute(delete(AuditLog).where(AuditLog.created_at < audit_cutoff)))
        sessions = _deleted(
            session.execute(
                delete(UserSession).where(
                    or_(
                        UserSession.revoked_at < ended,
                        UserSession.expires_at < ended,
                        UserSession.last_seen_at < idle_ended,
                    )
                )
            )
        )
    if audits or sessions:
        log.info("purged audit entries and sessions", extra={"audit": audits, "sessions": sessions})


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
