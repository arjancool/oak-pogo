"""Processing a queued import job (spec §4.6, steps 9–16)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.core.clock import Clock
from app.core.config import Settings
from app.core.db import Database
from app.domain.classification import AccountContext, CompletenessPolicy, ImportKind, classify
from app.domain.pokemon import Issue, Severity
from app.gamedata.store import GameDataStore
from app.ingestion.receive import APPLIED_STATUSES, load_payload
from app.ingestion.sync import apply_export, in_inventory_count
from app.models import BackgroundJob, ImportIssue, ImportJob, SyncRun, TrainerAccount
from app.normalizers.pgsharp import normalize_export

log = logging.getLogger("oak.ingest")
MAX_STORED_ISSUES = 500
POLICY_KEY = "completeness"


class ImportProcessor:
    def __init__(self, settings: Settings, db: Database, gamedata: GameDataStore, clock: Clock) -> None:
        self.settings = settings
        self.db = db
        self.gamedata = gamedata
        self.clock = clock

    def process(self, import_job_id: int) -> str:
        now = self.clock.now()
        with self.db.transaction() as session:
            job = session.get(ImportJob, import_job_id)
            if job is None or job.status not in ("queued", "processing"):
                return "skipped"
            job.status = "processing"
            job.stage = "normalizing"
            job.progress = 10
            job.started_at = now
            job.attempts += 1
            payload_file = job.payload_file
        if not payload_file:
            return self._fail(import_job_id, "PAYLOAD_MISSING", "De opgeslagen export ontbreekt.")
        try:
            raw = load_payload(self.settings.imports_dir, payload_file)
        except (OSError, ValueError):
            return self._fail(
                import_job_id,
                "PAYLOAD_UNREADABLE",
                "De opgeslagen export kan niet gelezen worden. Upload hem opnieuw.",
            )

        gd = self.gamedata.active()
        try:
            export = normalize_export(
                raw,
                species_resolver=gd.dex_for_name if gd else None,
                move_resolver=(lambda key: (gd.move(key) or {}).get("id")) if gd else None,
            )
        except Exception:
            # Every failure after the job started ends in a final state the user can act on,
            # never in "processing" (audit A06).
            log.exception("import normalization failed", extra={"import_id": import_job_id})
            return self._fail(
                import_job_id,
                "NORMALIZATION_FAILED",
                "De export kon niet gelezen worden door een interne fout. Er is niets gewijzigd.",
            )
        with self.db.transaction() as session:
            job = session.get(ImportJob, import_job_id)
            if job is not None:
                job.stage = "applying"
                job.progress = 40
                job.export_time = export.export_time

        try:
            with self.db.immediate_transaction() as session:
                job = session.get(ImportJob, import_job_id)
                if job is None:
                    return "skipped"
                account = session.get(TrainerAccount, job.trainer_account_id)
                if account is None:
                    return "skipped"
                duplicate_of = session.scalar(
                    select(ImportJob.id)
                    .where(
                        ImportJob.trainer_account_id == account.id,
                        ImportJob.payload_sha256 == job.payload_sha256,
                        ImportJob.status.in_(APPLIED_STATUSES),
                        ImportJob.id != job.id,
                    )
                    .limit(1)
                )
                if duplicate_of is not None and not job.confirm_full:
                    job.status = "duplicate"
                    job.classification = ImportKind.DUPLICATE.value
                    job.duplicate_of_id = duplicate_of
                    job.stage = "done"
                    job.progress = 100
                    job.finished_at = self.clock.now()
                    return "duplicate"

                has_previous = (
                    session.scalar(select(SyncRun.id).where(SyncRun.trainer_account_id == account.id).limit(1))
                    is not None
                )
                context = AccountContext(
                    known_fingerprint=account.source_fingerprint,
                    known_nickname=account.source_nickname,
                    in_inventory_count=in_inventory_count(session, account.id),
                    last_export_time=account.last_export_time,
                    has_previous_sync=has_previous,
                )
                classification = classify(
                    export,
                    context,
                    job.fingerprint,
                    policy=_policy(account.settings),
                    confirm_full=job.confirm_full,
                )
                _store_issues(session, job.id, export.issues)
                job.classification = classification.kind.value
                finished = self.clock.now()

                if classification.kind in (ImportKind.INVALID, ImportKind.STALE):
                    for reason in classification.reasons:
                        session.add(
                            ImportIssue(
                                import_job_id=job.id,
                                severity="error",
                                code=reason.code,
                                message=reason.message,
                            )
                        )
                    job.status = "rejected"
                    job.error_code = classification.reasons[0].code
                    job.error_message = classification.reasons[0].message
                    job.stage = "done"
                    job.progress = 100
                    job.finished_at = finished
                    account.sync_status = "error"
                    log.info("import rejected", extra={"import_id": job.id, "code": job.error_code})
                    return "rejected"

                run = apply_export(
                    session,
                    account=account,
                    export=export,
                    classification=classification,
                    job=job,
                    gd=gd,
                    tz=self.settings.tz,
                    now=finished,
                )
                for reason in classification.reasons:
                    session.add(
                        ImportIssue(
                            import_job_id=job.id,
                            severity="warning",
                            code=reason.code,
                            message=reason.message,
                        )
                    )
                # Link the account only on a full import: an unverified export never decides
                # which Pokémon GO account this trainer account belongs to.
                if job.fingerprint and not account.source_fingerprint and classification.kind is ImportKind.FULL:
                    account.source_fingerprint = job.fingerprint
                job.sync_run_id = run.id
                job.status = "succeeded" if classification.kind is ImportKind.FULL else "partial"
                job.stage = "done"
                job.progress = 100
                job.finished_at = finished
                account.sync_status = "ok" if classification.kind is ImportKind.FULL else "warning"
                _enqueue_analysis(session, account.id, finished)
                log.info(
                    "import applied",
                    extra={
                        "import_id": job.id,
                        "account_id": account.id,
                        "classification": classification.kind.value,
                        "new": run.new_count,
                        "changed": run.changed_count,
                        "missing": run.missing_count,
                    },
                )
                return job.status
        except Exception:
            log.exception("import processing failed", extra={"import_id": import_job_id})
            return self._fail(
                import_job_id,
                "PROCESSING_FAILED",
                "Verwerking mislukt door een interne fout. Er is niets gewijzigd.",
            )

    def _fail(self, import_job_id: int, code: str, message: str) -> str:
        with self.db.transaction() as session:
            job = session.get(ImportJob, import_job_id)
            if job is not None:
                job.status = "failed"
                job.error_code = code
                job.error_message = message
                job.stage = "done"
                job.finished_at = self.clock.now()
                account = session.get(TrainerAccount, job.trainer_account_id)
                if account is not None:
                    account.sync_status = "error"
        return "failed"


def _policy(account_settings: dict[str, Any] | None) -> CompletenessPolicy:
    raw = (account_settings or {}).get(POLICY_KEY) or {}
    defaults = CompletenessPolicy()
    return CompletenessPolicy(
        max_drop_fraction=float(raw.get("max_drop_fraction", defaults.max_drop_fraction)),
        max_drop_absolute=int(raw.get("max_drop_absolute", defaults.max_drop_absolute)),
    )


def _store_issues(session: Any, job_id: int, issues: list[Issue]) -> None:
    ordered = sorted(issues, key=lambda i: {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}[i.severity])
    for issue in ordered[:MAX_STORED_ISSUES]:
        session.add(
            ImportIssue(
                import_job_id=job_id,
                severity=issue.severity.value,
                code=issue.code,
                message=issue.message,
                path=issue.path,
                source_pokemon_id=issue.source_pokemon_id,
            )
        )
    if len(ordered) > MAX_STORED_ISSUES:
        session.add(
            ImportIssue(
                import_job_id=job_id,
                severity="info",
                code="ISSUES_TRUNCATED",
                message=f"{len(ordered) - MAX_STORED_ISSUES} meldingen niet opgeslagen.",
            )
        )


def _enqueue_analysis(session: Any, account_id: int, now: datetime) -> None:
    pending = session.scalar(
        select(BackgroundJob.id)
        .where(
            BackgroundJob.kind == "analysis",
            BackgroundJob.trainer_account_id == account_id,
            BackgroundJob.status == "queued",
        )
        .limit(1)
    )
    if pending is None:
        session.add(BackgroundJob(kind="analysis", status="queued", trainer_account_id=account_id, created_at=now))
