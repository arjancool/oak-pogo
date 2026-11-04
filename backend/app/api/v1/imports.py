"""Manual upload and import job status (spec §4.4, §20.3)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, defer

from app.api.deps import AuthContext, get_auth, get_container, get_session, owned_account
from app.api.uploads import bounded_form, form_file, form_text
from app.core.container import Container
from app.core.errors import (
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    RateLimitedError,
    ValidationFailedError,
)
from app.domain.classification import CONFIRMABLE_CODES
from app.ingestion.receive import (
    IncomingPayload,
    PreparedImport,
    create_import_job,
    decode_payload,
    prepare_import,
)
from app.models import BackgroundJob, ImportIssue, ImportJob, SyncRun, TrainerAccount, User
from app.schemas.common import ApiModel, UtcDatetime

router = APIRouter(prefix="/imports", tags=["imports"])
MAX_PAGE_SIZE = 200


class SyncRunOut(ApiModel):
    id: int
    classification: str
    source: str
    export_time: UtcDatetime | None
    applied_at: UtcDatetime
    total_pokemon: int
    eggs: int
    new_count: int
    changed_count: int
    unchanged_count: int
    missing_count: int
    missing_unconfirmed_count: int
    reappeared_count: int
    items_changed: bool
    warnings: list[dict[str, Any]]


class ImportOut(ApiModel):
    id: int
    trainer_account_id: int
    source: str
    status: str
    stage: str | None
    progress: int
    classification: str | None
    filename: str | None
    payload_size: int
    payload_available: bool = False
    export_time: UtcDatetime | None
    received_at: UtcDatetime
    started_at: UtcDatetime | None
    finished_at: UtcDatetime | None
    error_code: str | None
    error_message: str | None
    # The values in error_message (ADR-0025); None for errors stored before OAK kept them.
    error_data: dict[str, Any] | None = None
    duplicate_of_id: int | None
    retry_of_id: int | None
    confirm_full: bool
    request_meta: dict[str, Any] | None
    schema_summary: dict[str, Any] | None = None
    sync_run: SyncRunOut | None = None
    issue_counts: dict[str, int] = Field(default_factory=dict)
    confirmable: bool = False


class IssueOut(ApiModel):
    id: int
    severity: str
    code: str
    message: str
    # The values in message (ADR-0025); None for messages stored before OAK kept them.
    data: dict[str, Any] | None = None
    path: str | None
    source_pokemon_id: str | None


def import_out(session: Session, job: ImportJob, *, detail: bool = False) -> ImportOut:
    # The structure summary is only for the detail view; a list never loads it (issue #46).
    fields = {name: getattr(job, name) for name in ImportOut.model_fields if name in IMPORT_COLUMNS}
    if detail:
        fields["schema_summary"] = job.schema_summary
    out = ImportOut.model_validate(fields)
    out.payload_available = job.payload_file is not None and job.payload_purged_at is None
    if job.sync_run_id:
        run = session.get(SyncRun, job.sync_run_id)
        if run is not None:
            out.sync_run = SyncRunOut.model_validate(run)
    counts = session.execute(
        select(ImportIssue.severity, func.count())
        .where(ImportIssue.import_job_id == job.id)
        .group_by(ImportIssue.severity)
    ).all()
    out.issue_counts = dict(counts)  # type: ignore[arg-type]
    if job.status == "partial" and out.payload_available:
        codes = set(session.scalars(select(ImportIssue.code).where(ImportIssue.import_job_id == job.id)))
        warnings = {w["code"] for w in (out.sync_run.warnings if out.sync_run else [])}
        out.confirmable = bool(warnings) and warnings <= CONFIRMABLE_CODES and "UNIDENTIFIABLE_RECORDS" not in codes
    return out


IMPORT_COLUMNS = frozenset(ImportJob.__table__.columns.keys()) - {"schema_summary"}


def _owned_job(session: Session, auth: AuthContext, import_id: int) -> ImportJob:
    job = session.scalars(
        select(ImportJob)
        .join(TrainerAccount, TrainerAccount.id == ImportJob.trainer_account_id)
        .where(ImportJob.id == import_id, TrainerAccount.user_id == auth.user.id)
    ).first()
    if job is None:
        raise NotFoundError("Import niet gevonden.", context="import")
    return job


@router.post("/upload", response_model=ImportOut, status_code=202)
async def upload(
    request: Request,
    auth: AuthContext = Depends(get_auth),
    container: Container = Depends(get_container),
) -> ImportOut:
    """Upload PGSStats.json. The fields are ``file`` and an optional ``account_id``. The body
    is only read after the login check, and never beyond the configured limit (audit A04)."""
    _count_import(container, auth)
    limit = container.settings.max_import_bytes
    form = await bounded_form(request, limit, max_files=1)
    try:
        file = form_file(form, "file")
        if file is None:
            raise ValidationFailedError("Kies een bestand om te uploaden.", code="FILE_REQUIRED", context="import")
        raw_account = form_text(form, "account_id")
        try:
            account_id = int(raw_account) if raw_account else None
        except ValueError as exc:
            raise ValidationFailedError("Ongeldig traineraccount.", context="account_id") from exc
        body = await file.read(limit + 1)
        if len(body) > limit:
            raise PayloadTooLargeError("Het bestand is groter dan de ingestelde limiet.", context="file")
        incoming = IncomingPayload(
            body=body,
            source="upload",
            content_type=file.content_type or "application/json",
            filename=file.filename,
        )
    finally:
        await form.close()
    result = await run_in_threadpool(_accept_upload, container, auth.user.id, account_id, incoming)
    container.runner.notify()
    return result


def _accept_upload(container: Container, user_id: int, account_id: int | None, incoming: IncomingPayload) -> ImportOut:
    if incoming.content_type and incoming.content_type.startswith("multipart/"):
        incoming.content_type = "application/json"
    with container.import_slots:
        decoded = decode_payload(incoming, container.settings.max_import_bytes)
        # The export is read, filtered and stored before the write transaction (app/ingestion/receive.py).
        with (
            prepare_import(decoded, secret=container.secret, imports_dir=container.settings.imports_dir) as prepared,
            container.db.transaction() as session,
        ):
            user = session.get(User, user_id)
            assert user is not None
            account = _upload_account(session, user, account_id, prepared)
            require_nothing_queued(session, account.id)
            job = create_import_job(
                session,
                account=account,
                user_id=user_id,
                incoming=incoming,
                decoded=decoded,
                prepared=prepared,
                now=container.clock.now(),
            )
            return import_out(session, job, detail=True)


def _upload_account(session: Session, user: User, account_id: int | None, prepared: PreparedImport) -> TrainerAccount:
    """The chosen trainer account, or the one the export belongs to when none was chosen."""
    fingerprint = prepared.fingerprint
    if account_id is None:
        matches = (
            session.scalars(
                select(TrainerAccount).where(
                    TrainerAccount.user_id == user.id,
                    TrainerAccount.source_fingerprint == fingerprint,
                )
            ).all()
            if fingerprint
            else []
        )
        if len(matches) != 1:
            raise ValidationFailedError(
                "OAK kan het traineraccount niet automatisch herkennen. Kies het account waar deze export bij hoort.",
                code="ACCOUNT_REQUIRED",
            )
        return matches[0]
    account = owned_account(session, user, account_id)
    if fingerprint and account.source_fingerprint and account.source_fingerprint != fingerprint:
        other = session.scalars(
            select(TrainerAccount).where(
                TrainerAccount.user_id == user.id,
                TrainerAccount.source_fingerprint == fingerprint,
            )
        ).first()
        if other is not None:
            raise ConflictError(
                "Deze export hoort bij een ander Pokémon GO-account dan het gekozen traineraccount. "
                f"Deze export hoort bij '{other.nickname}'.",
                code="ACCOUNT_MISMATCH",
                context="known_account",
                data={"nickname": other.nickname},
                details={"matching_account_id": other.id},
            )
        raise ConflictError(
            "Deze export hoort bij een ander Pokémon GO-account dan het gekozen traineraccount.",
            code="ACCOUNT_MISMATCH",
            context="other_account",
            details={"matching_account_id": None},
        )
    return account


@router.get("", response_model=dict[str, Any])
def list_imports(
    account_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=MAX_PAGE_SIZE),
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    account = owned_account(session, auth.user, account_id)
    total = (
        session.scalar(select(func.count()).select_from(ImportJob).where(ImportJob.trainer_account_id == account.id))
        or 0
    )
    jobs = session.scalars(
        select(ImportJob)
        .options(defer(ImportJob.schema_summary))
        .where(ImportJob.trainer_account_id == account.id)
        .order_by(ImportJob.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [import_out(session, j).model_dump(mode="json") for j in jobs],
    }


@router.get("/{import_id}", response_model=ImportOut)
def get_import(
    import_id: int, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)
) -> ImportOut:
    return import_out(session, _owned_job(session, auth, import_id), detail=True)


@router.get("/{import_id}/errors", response_model=list[IssueOut])
def get_import_errors(
    import_id: int,
    severity: str | None = None,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
) -> list[IssueOut]:
    job = _owned_job(session, auth, import_id)
    stmt = select(ImportIssue).where(ImportIssue.import_job_id == job.id)
    if severity:
        stmt = stmt.where(ImportIssue.severity == severity)
    return [IssueOut.model_validate(i) for i in session.scalars(stmt.order_by(ImportIssue.id).limit(1000))]


def _count_import(container: Container, auth: AuthContext) -> None:
    """Uploads, retries and confirmations per user, so one user cannot keep the single worker
    busy for everyone (issue #45)."""
    retry = container.imports_by_user.hit(f"user:{auth.user.id}")
    if retry:
        raise RateLimitedError(
            "Te veel imports in korte tijd. Probeer het later opnieuw.", retry_after=retry, context="imports"
        )


def require_nothing_queued(session: Session, account_id: int) -> None:
    """At most one manual import per trainer account waits in the queue (issue #45)."""
    waiting = session.scalar(
        select(ImportJob.id).where(ImportJob.trainer_account_id == account_id, ImportJob.status == "queued").limit(1)
    )
    if waiting is not None:
        raise ConflictError(
            "Er wacht al een import voor dit traineraccount. Probeer het opnieuw als die klaar is.",
            code="IMPORT_QUEUED",
        )


def _requeue(session: Session, container: Container, job: ImportJob, *, confirm_full: bool) -> ImportJob:
    require_nothing_queued(session, job.trainer_account_id)
    if job.payload_file is None or job.payload_purged_at is not None:
        raise ConflictError(
            "De opgeslagen export is niet meer beschikbaar. Upload hem opnieuw.",
            code="PAYLOAD_GONE",
        )
    now = container.clock.now()
    retry = ImportJob(
        trainer_account_id=job.trainer_account_id,
        user_id=job.user_id,
        source="retry",
        status="queued",
        stage="queued",
        payload_sha256=job.payload_sha256,
        payload_size=job.payload_size,
        payload_file=job.payload_file,
        filename=job.filename,
        request_meta=job.request_meta,
        # Not copied: the summary belongs to the import that received the export (issue #46).
        fingerprint=job.fingerprint,
        confirm_full=confirm_full,
        retry_of_id=job.id,
        received_at=now,
    )
    session.add(retry)
    session.flush()
    session.add(
        BackgroundJob(
            kind="import",
            status="queued",
            trainer_account_id=job.trainer_account_id,
            ref_id=retry.id,
            created_at=now,
        )
    )
    return retry


@router.post("/{import_id}/retry", response_model=ImportOut, status_code=202)
def retry_import(
    import_id: int,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> ImportOut:
    job = _owned_job(session, auth, import_id)
    _count_import(container, auth)
    if job.status not in ("failed", "rejected", "partial"):
        raise ConflictError(
            "Alleen mislukte, geweigerde of gedeeltelijke imports kunnen opnieuw.", context="retry_not_allowed"
        )
    retry = _requeue(session, container, job, confirm_full=False)
    session.commit()
    container.runner.notify()
    return import_out(session, retry)


@router.post("/{import_id}/confirm-full", response_model=ImportOut, status_code=202)
def confirm_full_import(
    import_id: int,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> ImportOut:
    """The user confirms that a partial import really was a complete export. Only then are the
    missing Pokémon marked as no longer in inventory (spec §4.7)."""
    job = _owned_job(session, auth, import_id)
    _count_import(container, auth)
    out = import_out(session, job)
    if not out.confirmable:
        raise ConflictError("Deze import kan niet als volledig bevestigd worden.", code="NOT_CONFIRMABLE")
    latest = session.scalar(
        select(func.max(ImportJob.id)).where(
            ImportJob.trainer_account_id == job.trainer_account_id,
            ImportJob.status.in_(("succeeded", "partial")),
        )
    )
    if latest != job.id:
        raise ConflictError("Er is al een nieuwere import verwerkt.", code="NOT_LATEST")
    retry = _requeue(session, container, job, confirm_full=True)
    session.commit()
    container.runner.notify()
    return import_out(session, retry)
