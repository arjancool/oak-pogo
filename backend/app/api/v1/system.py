"""System status, version, application settings, users and backups (spec §20.8, §26)."""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import __version__
from app.api.deps import AuthContext, get_auth, get_container, get_session, require_owner
from app.api.v1.auth import UserOut, audit, validate_username
from app.auth.passwords import hash_password
from app.auth.sessions import revoke_all_for_user
from app.core.container import Container
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.migrations import backup_database
from app.models import AuditLog, BackgroundJob, GameDataVersion, ImportJob, TrainerAccount, User
from app.repositories.settings import set_setting
from app.services.settings import POKEAPI_SPRITE_TEMPLATE, SPRITE_KEY

router = APIRouter(tags=["system"])
BUILD_INFO_KEYS = ("OAK_BUILD_SHA", "OAK_BUILD_DATE", "OAK_BUILD_REF")


def _build_info() -> dict[str, str | None]:
    return {key.removeprefix("OAK_BUILD_").lower(): os.environ.get(key) for key in BUILD_INFO_KEYS}


@router.get("/system/version", response_model=dict[str, Any])
def version() -> dict[str, Any]:
    return {"version": __version__, "build": _build_info()}


@router.get("/system/status", response_model=dict[str, Any])
def system_status(
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    settings = container.settings
    usage = shutil.disk_usage(settings.data_dir)
    db_size = settings.database_path.stat().st_size if settings.database_path.exists() else 0
    jobs = dict(session.execute(select(BackgroundJob.status, func.count()).group_by(BackgroundJob.status)).all())
    failed_imports = (
        session.scalar(
            select(func.count())
            .select_from(ImportJob)
            .join(TrainerAccount, TrainerAccount.id == ImportJob.trainer_account_id)
            .where(TrainerAccount.user_id == auth.user.id, ImportJob.status == "failed")
        )
        or 0
    )
    last_sync = session.scalar(
        select(func.max(TrainerAccount.last_successful_sync_at)).where(TrainerAccount.user_id == auth.user.id)
    )
    active = session.scalars(select(GameDataVersion).where(GameDataVersion.status == "active")).first()
    return {
        "version": __version__,
        "build": _build_info(),
        "started_at": container.started_at.isoformat(),
        "environment": settings.env,
        "timezone": settings.timezone,
        "base_url": settings.base_url,
        "database": {"status": "ok", "size_bytes": db_size, "path": str(settings.database_path)},
        "storage": {
            "total_bytes": usage.total,
            "free_bytes": usage.free,
            "data_dir": str(settings.data_dir),
        },
        "jobs": {
            "pending": jobs.get("queued", 0) + jobs.get("running", 0),
            "failed": jobs.get("failed", 0),
        },
        "failed_imports": failed_imports,
        "last_successful_sync": last_sync.isoformat() if last_sync else None,
        "game_data": {
            "version_id": active.id if active else None,
            "activated_at": active.activated_at.isoformat() if active and active.activated_at else None,
        },
        "secret_key_source": "generated" if container.secret_generated else "environment",
        "registration_open": settings.allow_registration,
        "raw_import_retention_days": settings.raw_import_retention_days,
        "worker_running": settings.start_worker,
    }


class AppSettingsIn(BaseModel):
    sprite_source: str = Field(pattern="^(none|pokeapi|custom)$")
    sprite_url_template: str | None = Field(default=None, max_length=300)


@router.get("/settings", response_model=dict[str, Any])
def get_app_settings(
    auth: AuthContext = Depends(get_auth), container: Container = Depends(get_container)
) -> dict[str, Any]:
    template = container.sprite_template
    source = "none" if not template else ("pokeapi" if template == POKEAPI_SPRITE_TEMPLATE else "custom")
    return {
        "sprite_source": source,
        "sprite_url_template": template or None,
        # A server text: {code, text}, with the Dutch text as the fallback (ADR-0025).
        "sprite_notice": {
            "code": "SPRITE_NOTICE",
            "text": "Pokémon-afbeeldingen zijn auteursrechtelijk beschermd (The Pokémon Company). OAK levert ze "
            "niet mee. Als je een externe bron inschakelt, laadt je browser de afbeeldingen daar direct. Dat is je "
            "eigen keuze en verantwoordelijkheid (ADR-0020).",
        },
        "timezone": container.settings.timezone,
        "base_url": container.settings.base_url,
    }


@router.put("/settings", response_model=dict[str, Any])
def put_app_settings(
    body: AppSettingsIn,
    auth: AuthContext = Depends(require_owner),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    if body.sprite_source == "none":
        template = ""
    elif body.sprite_source == "pokeapi":
        template = POKEAPI_SPRITE_TEMPLATE
    else:
        template = (body.sprite_url_template or "").strip()
        if not template.startswith("https://") or "{dex}" not in template:
            raise ValidationFailedError(
                "Een eigen spritebron moet met https:// beginnen en {dex} bevatten.", context="sprite_template"
            )
    set_setting(session, SPRITE_KEY, template)
    audit(
        session,
        auth.user.id,
        "settings_changed",
        "sprites",
        container,
        {"source": body.sprite_source},
    )
    session.commit()
    container.sprite_template = template
    return get_app_settings(auth, container)


# --- users (owner only) ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)
    email: str | None = Field(default=None, max_length=254)


class UserPatch(BaseModel):
    status: str | None = Field(default=None, pattern="^(active|disabled)$")
    password: str | None = Field(default=None, max_length=256)


@router.get("/users", response_model=list[UserOut])
def list_users(auth: AuthContext = Depends(require_owner), session: Session = Depends(get_session)) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in session.scalars(select(User).order_by(User.id))]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreate,
    auth: AuthContext = Depends(require_owner),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> UserOut:
    username = validate_username(body.username)
    if session.scalar(select(User.id).where(User.username == username)):
        raise ConflictError("Deze gebruikersnaam bestaat al.", context="username_taken")
    now = container.clock.now()
    user = User(
        username=username,
        email=body.email,
        password_hash=hash_password(body.password),
        role="user",
        status="active",
        preferences={},
        created_at=now,
        password_changed_at=now,
    )
    session.add(user)
    session.flush()
    audit(session, auth.user.id, "user_created", username, container)
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserPatch,
    auth: AuthContext = Depends(require_owner),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> UserOut:
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError("Gebruiker niet gevonden.", context="user")
    if user.id == auth.user.id and body.status == "disabled":
        raise ValidationFailedError("Je kunt jezelf niet uitschakelen.", context="disable_self")
    if user.id == auth.user.id and body.password:
        # Without the current password, a stolen session could take over the owner account.
        raise ValidationFailedError(
            "Wijzig je eigen wachtwoord via Wachtwoord wijzigen, met je huidige wachtwoord.", context="own_password"
        )
    now = container.clock.now()
    if body.status:
        user.status = body.status
        if body.status == "disabled":
            revoke_all_for_user(session, user.id, now)
    if body.password:
        user.password_hash = hash_password(body.password)
        user.password_changed_at = now
        revoke_all_for_user(session, user.id, now)
    # Never the password itself, only that it was reset.
    audit(
        session,
        auth.user.id,
        "user_updated",
        user.username,
        container,
        {"status": body.status, "password_reset": bool(body.password)},
    )
    return UserOut.model_validate(user)


@router.get("/audit", response_model=list[dict[str, Any]])
def audit_log(
    auth: AuthContext = Depends(require_owner), session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    rows = session.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(200)).all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "action": r.action,
            "target": r.target,
            "at": r.created_at.isoformat(),
        }
        for r in rows
    ]


# --- backups (owner only) -------------------------------------------------------------------------


@router.get("/backups", response_model=list[dict[str, Any]])
def list_backups(
    auth: AuthContext = Depends(require_owner), container: Container = Depends(get_container)
) -> list[dict[str, Any]]:
    files = sorted(container.settings.backups_dir.glob("oak-*.db"), reverse=True)
    return [
        {
            "name": f.name,
            "size_bytes": f.stat().st_size,
            "created_at": datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).isoformat(),
        }
        for f in files
    ]


@router.post("/backups", response_model=dict[str, Any], status_code=201)
async def create_backup(
    request: Request,
    auth: AuthContext = Depends(require_owner),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    path = await run_in_threadpool(backup_database, container.settings, "manual")
    with container.db.transaction() as session:
        audit(session, auth.user.id, "backup_created", path.name if path else None, container)
    if path is None:
        raise ConflictError("Er is nog geen database om te back-uppen.", context="no_database")
    return {"name": path.name, "size_bytes": path.stat().st_size}


@router.get("/backups/{name}")
def download_backup(
    name: str,
    auth: AuthContext = Depends(require_owner),
    container: Container = Depends(get_container),
) -> Response:
    if "/" in name or "\\" in name or not name.startswith("oak-") or not name.endswith(".db"):
        raise NotFoundError("Back-up niet gevonden.", context="backup")
    path = container.settings.backups_dir / name
    if not path.is_file():
        raise NotFoundError("Back-up niet gevonden.", context="backup")
    with container.db.transaction() as session:
        audit(session, auth.user.id, "backup_downloaded", name, container)
    return FileResponse(path, media_type="application/vnd.sqlite3", filename=name)


@router.delete("/backups/{name}", status_code=204)
def delete_backup(
    name: str,
    auth: AuthContext = Depends(require_owner),
    container: Container = Depends(get_container),
) -> Response:
    if "/" in name or "\\" in name or not name.startswith("oak-") or not name.endswith(".db"):
        raise NotFoundError("Back-up niet gevonden.", context="backup")
    (container.settings.backups_dir / name).unlink(missing_ok=True)
    return Response(status_code=204)
