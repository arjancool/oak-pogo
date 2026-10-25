"""Trainer accounts and their webhook credentials (spec §20.2, §4.2)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth, get_container, get_session, owned_account
from app.api.v1.auth import audit
from app.auth.tokens import new_webhook_token, sha256_hex
from app.core.container import Container
from app.core.errors import ValidationFailedError
from app.models import ImportJob, Pokemon, TrainerAccount, WebhookCredential
from app.recommendations.rules import CleanupRules
from app.schemas.common import ApiModel, UtcDatetime
from app.services.analysis import RULES_KEY

router = APIRouter(prefix="/accounts", tags=["accounts"])
DIAGNOSTICS_HOURS = 24
WEBHOOK_PATH = "/api/v1/ingest/pgsharp/"


class AccountIn(ApiModel):
    nickname: str = Field(min_length=1, max_length=64)


class AccountPatch(ApiModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=64)
    completeness: dict[str, float] | None = None


class AccountDelete(ApiModel):
    confirm_nickname: str


class WebhookOut(ApiModel):
    active: bool
    token_identifier: str | None
    url_masked: str | None
    created_at: UtcDatetime | None
    last_used_at: UtcDatetime | None


class WebhookCreated(ApiModel):
    url: str
    token_identifier: str
    message: str


class AccountOut(ApiModel):
    id: int
    nickname: str
    source_nickname: str | None
    trainer_level: int | None
    experience: int | None
    stardust: int | None
    pokecoins: int | None
    team: int | None
    max_pokemon_storage: int | None
    max_item_storage: int | None
    last_successful_sync_at: UtcDatetime | None
    last_export_time: UtcDatetime | None
    last_import_attempt_at: UtcDatetime | None
    sync_status: str
    created_at: UtcDatetime
    pokemon_count: int = 0
    linked: bool = False
    webhook: WebhookOut | None = None
    diagnostics_until: UtcDatetime | None = None
    completeness: dict[str, Any] = Field(default_factory=dict)


def _webhook_out(cred: WebhookCredential | None, base_url: str) -> WebhookOut:
    if cred is None:
        return WebhookOut(active=False, token_identifier=None, url_masked=None, created_at=None, last_used_at=None)
    return WebhookOut(
        active=cred.status == "active",
        token_identifier=cred.token_identifier,
        url_masked=f"{base_url}{WEBHOOK_PATH}oakwh_{cred.token_identifier}_••••••••",
        created_at=cred.created_at,
        last_used_at=cred.last_used_at,
    )


def _account_out(session: Session, account: TrainerAccount, container: Container) -> AccountOut:
    out = AccountOut.model_validate(account)
    out.pokemon_count = int(
        session.scalar(
            select(func.count())
            .select_from(Pokemon)
            .where(Pokemon.trainer_account_id == account.id, Pokemon.inventory_status == "in_inventory")
        )
        or 0
    )
    out.linked = account.source_fingerprint is not None
    cred = session.scalars(
        select(WebhookCredential)
        .where(WebhookCredential.trainer_account_id == account.id, WebhookCredential.status == "active")
        .order_by(WebhookCredential.id.desc())
    ).first()
    out.webhook = _webhook_out(cred, container.settings.base_url)
    out.completeness = (account.settings or {}).get("completeness") or {}
    return out


@router.get("", response_model=list[AccountOut])
def list_accounts(
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> list[AccountOut]:
    accounts = session.scalars(
        select(TrainerAccount).where(TrainerAccount.user_id == auth.user.id).order_by(TrainerAccount.id)
    ).all()
    return [_account_out(session, a, container) for a in accounts]


@router.post("", response_model=AccountOut, status_code=201)
def create_account(
    body: AccountIn,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> AccountOut:
    account = TrainerAccount(
        user_id=auth.user.id,
        nickname=body.nickname.strip(),
        sync_status="waiting",
        settings={},
        created_at=container.clock.now(),
    )
    session.add(account)
    session.flush()
    audit(session, auth.user.id, "account_created", str(account.id), container)
    return _account_out(session, account, container)


@router.get("/{account_id}", response_model=AccountOut)
def get_account(
    account_id: int,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> AccountOut:
    return _account_out(session, owned_account(session, auth.user, account_id), container)


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(
    account_id: int,
    body: AccountPatch,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> AccountOut:
    account = owned_account(session, auth.user, account_id)
    if body.nickname is not None:
        account.nickname = body.nickname.strip()
    if body.completeness is not None:
        fraction = body.completeness.get("max_drop_fraction")
        absolute = body.completeness.get("max_drop_absolute")
        if fraction is not None and not 0 < fraction <= 1:
            raise ValidationFailedError("max_drop_fraction moet tussen 0 en 1 liggen.")
        if absolute is not None and absolute < 0:
            raise ValidationFailedError("max_drop_absolute moet positief zijn.")
        account.settings = {**(account.settings or {}), "completeness": body.completeness}
    return _account_out(session, account, container)


@router.delete("/{account_id}", status_code=204)
def delete_account(
    account_id: int,
    body: AccountDelete,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> Response:
    """Deleting an account removes all its OAK data and stored exports. The caller must repeat the nickname."""
    account = owned_account(session, auth.user, account_id)
    if body.confirm_nickname.strip() != account.nickname:
        raise ValidationFailedError(
            "Typ de naam van het traineraccount exact over om te bevestigen.",
            code="CONFIRMATION_MISMATCH",
        )
    payload_files = set(
        session.scalars(
            select(ImportJob.payload_file).where(
                ImportJob.trainer_account_id == account.id, ImportJob.payload_file.is_not(None)
            )
        )
    )
    audit(session, auth.user.id, "account_deleted", f"{account.id}:{account.nickname}", container)
    session.delete(account)
    session.flush()
    still_used = set(session.scalars(select(ImportJob.payload_file).where(ImportJob.payload_file.in_(payload_files))))
    session.commit()
    # The stored exports go only after the commit, so a failed delete never loses them.
    for file_name in payload_files - still_used:
        (container.settings.imports_dir / str(file_name)).unlink(missing_ok=True)
    return Response(status_code=204)


@router.post("/{account_id}/webhook", response_model=WebhookCreated, status_code=201)
def create_webhook(
    account_id: int,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> WebhookCreated:
    """Create or rotate the webhook token. The full URL is returned exactly once."""
    account = owned_account(session, auth.user, account_id)
    now = container.clock.now()
    for cred in session.scalars(
        select(WebhookCredential).where(
            WebhookCredential.trainer_account_id == account.id, WebhookCredential.status == "active"
        )
    ):
        cred.status = "revoked"
        cred.revoked_at = now
    token, identifier = new_webhook_token()
    session.add(
        WebhookCredential(
            trainer_account_id=account.id,
            token_identifier=identifier,
            token_hash=sha256_hex(token),
            created_at=now,
            status="active",
        )
    )
    audit(session, auth.user.id, "webhook_created", f"{account.id}:{identifier}", container)
    return WebhookCreated(
        url=f"{container.settings.base_url}{WEBHOOK_PATH}{token}",
        token_identifier=identifier,
        message="Kopieer deze URL nu. OAK bewaart alleen een hash en kan hem later niet opnieuw tonen.",
    )


@router.delete("/{account_id}/webhook", status_code=204)
def revoke_webhook(
    account_id: int,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> Response:
    account = owned_account(session, auth.user, account_id)
    now = container.clock.now()
    for cred in session.scalars(
        select(WebhookCredential).where(
            WebhookCredential.trainer_account_id == account.id, WebhookCredential.status == "active"
        )
    ):
        cred.status = "revoked"
        cred.revoked_at = now
        audit(
            session,
            auth.user.id,
            "webhook_revoked",
            f"{account.id}:{cred.token_identifier}",
            container,
        )
    return Response(status_code=204)


class DiagnosticsIn(ApiModel):
    enabled: bool


@router.put("/{account_id}/diagnostics", response_model=AccountOut)
def set_diagnostics(
    account_id: int,
    body: DiagnosticsIn,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> AccountOut:
    """Temporary diagnostics: for 24 hours the structure of every incoming request is kept in
    full detail (key paths and types, never values)."""
    account = owned_account(session, auth.user, account_id)
    account.diagnostics_until = container.clock.now() + timedelta(hours=DIAGNOSTICS_HOURS) if body.enabled else None
    return _account_out(session, account, container)


@router.post("/{account_id}/unlink", response_model=AccountOut)
def unlink_account(
    account_id: int,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> AccountOut:
    """Forget which Pokémon GO account this trainer account is linked to, so an export of a
    different account is accepted on the next import. Needed only after a deliberate switch."""
    account = owned_account(session, auth.user, account_id)
    account.source_fingerprint = None
    audit(session, auth.user.id, "account_unlinked", str(account.id), container)
    return _account_out(session, account, container)


@router.get("/{account_id}/rules", response_model=dict[str, Any])
def get_rules(
    account_id: int,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    account = owned_account(session, auth.user, account_id)
    return CleanupRules.from_dict((account.settings or {}).get(RULES_KEY)).to_dict()
