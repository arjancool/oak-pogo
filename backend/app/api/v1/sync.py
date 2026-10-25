"""Synchronisation status and history (spec §8.3, §17.4)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth, get_session, owned_account
from app.api.v1.imports import ImportOut, SyncRunOut, import_out
from app.models import ImportJob, PokemonChangeEvent, SyncRun, WebhookCredential
from app.schemas.common import ApiModel, UtcDatetime

router = APIRouter(prefix="/sync", tags=["sync"])


class SyncStatus(ApiModel):
    account_id: int
    state: str  # waiting | connected | processing | error | warning
    message: str
    last_successful_sync_at: UtcDatetime | None
    last_import_attempt_at: UtcDatetime | None
    webhook_active: bool
    webhook_last_used_at: UtcDatetime | None
    pending_imports: int
    last_import: ImportOut | None
    last_sync: SyncRunOut | None


@router.get("/status", response_model=SyncStatus)
def sync_status(
    account_id: int, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)
) -> SyncStatus:
    account = owned_account(session, auth.user, account_id)
    cred = session.scalars(
        select(WebhookCredential).where(
            WebhookCredential.trainer_account_id == account.id, WebhookCredential.status == "active"
        )
    ).first()
    pending = (
        session.scalar(
            select(func.count())
            .select_from(ImportJob)
            .where(
                ImportJob.trainer_account_id == account.id,
                ImportJob.status.in_(("queued", "processing")),
            )
        )
        or 0
    )
    last_job = session.scalars(
        select(ImportJob).where(ImportJob.trainer_account_id == account.id).order_by(ImportJob.id.desc()).limit(1)
    ).first()
    last_run = session.scalars(
        select(SyncRun).where(SyncRun.trainer_account_id == account.id).order_by(SyncRun.id.desc()).limit(1)
    ).first()
    if pending:
        state, message = "processing", "Er wordt een import verwerkt."
    elif last_job is not None and last_job.status in ("failed", "rejected"):
        state, message = "error", last_job.error_message or "De laatste import is mislukt."
    elif last_job is not None and last_job.status == "partial":
        state, message = (
            "warning",
            "De laatste import was gedeeltelijk. Ontbrekende Pokémon zijn niet als verdwenen gemarkeerd.",
        )
    elif last_run is not None:
        state, message = "connected", "Gesynchroniseerd."
    else:
        state, message = "waiting", "Nog geen export ontvangen."
    return SyncStatus(
        account_id=account.id,
        state=state,
        message=message,
        last_successful_sync_at=account.last_successful_sync_at,
        last_import_attempt_at=account.last_import_attempt_at,
        webhook_active=cred is not None,
        webhook_last_used_at=cred.last_used_at if cred else None,
        pending_imports=pending,
        last_import=import_out(session, last_job) if last_job else None,
        last_sync=SyncRunOut.model_validate(last_run) if last_run else None,
    )


@router.get("/history", response_model=dict[str, Any])
def sync_history(
    account_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    account = owned_account(session, auth.user, account_id)
    total = (
        session.scalar(select(func.count()).select_from(SyncRun).where(SyncRun.trainer_account_id == account.id)) or 0
    )
    runs = session.scalars(
        select(SyncRun)
        .where(SyncRun.trainer_account_id == account.id)
        .order_by(SyncRun.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [SyncRunOut.model_validate(r).model_dump(mode="json") for r in runs],
    }


@router.get("/runs/{run_id}/events", response_model=dict[str, Any])
def sync_run_events(
    run_id: int,
    account_id: int,
    event_type: str | None = None,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    account = owned_account(session, auth.user, account_id)
    stmt = (
        select(func.count(), PokemonChangeEvent.event_type)
        .where(
            PokemonChangeEvent.trainer_account_id == account.id,
            PokemonChangeEvent.sync_run_id == run_id,
        )
        .group_by(PokemonChangeEvent.event_type)
    )
    counts = {kind: count for count, kind in session.execute(stmt).all()}
    return {"run_id": run_id, "counts": counts, "event_type": event_type}
