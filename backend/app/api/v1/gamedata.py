"""Game Data management (spec §6.2, §20.7)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth, get_container, get_session, require_owner
from app.api.uploads import bounded_form, form_file
from app.api.v1.auth import audit
from app.core.container import Container
from app.core.errors import PayloadTooLargeError, ValidationFailedError
from app.gamedata.fetch import source_urls
from app.jobs.tasks import enqueue, enqueue_rederive
from app.models import BackgroundJob, GameDataVersion
from app.repositories.settings import get_setting

router = APIRouter(prefix="/gamedata", tags=["gamedata"])
MAX_GAMEDATA_UPLOAD = 64 * 1024 * 1024
# Form field → Game Data source.
UPLOAD_FIELDS = {
    "pokeminers": "pokeminers",
    "pvpoke": "pvpoke",
    "rankings_great": "pvpoke-rankings-great",
    "rankings_ultra": "pvpoke-rankings-ultra",
    "rankings_master": "pvpoke-rankings-master",
}
# Texts for the interface are {code, text, data}: a code, the Dutch text and its values (ADR-0025).
DEPENDENT_ANALYSES = [
    {"code": "DEPENDS_NAMES", "text": "Soortnamen, vormen en typen in de Pokémon Box"},
    {"code": "DEPENDS_LEVEL", "text": "Pokémon-level uit de CP-multiplier"},
    {"code": "DEPENDS_PVP", "text": "PvP-IV-rangen en league-geschiktheid"},
    {"code": "DEPENDS_COSTS", "text": "Power-up- en evolutiekosten"},
    {"code": "DEPENDS_MOVESETS", "text": "Movesetadvies en Elite TM-beperkingen"},
    {"code": "DEPENDS_CLEANUP", "text": "Cleanup-aanbevelingen"},
    {"code": "DEPENDS_BATTLES", "text": "Raid-, Rocket- en Max Battle-analyse"},
]


def _version_out(v: GameDataVersion) -> dict[str, Any]:
    return {
        "id": v.id,
        "status": v.status,
        "origin": v.origin,
        "created_at": v.created_at.isoformat(),
        "activated_at": v.activated_at.isoformat() if v.activated_at else None,
        "summary": v.summary,
        "sources": v.sources,
        "error": v.error,
        # The same errors one by one, as server texts; None for versions from before OAK kept them.
        "errors": v.errors,
    }


@router.get("/status", response_model=dict[str, Any])
def status(
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    versions = session.scalars(select(GameDataVersion).order_by(GameDataVersion.id.desc()).limit(10)).all()
    active = next((v for v in versions if v.status == "active"), None)
    last_failed = next((v for v in versions if v.status == "failed"), None)
    pending = session.scalar(
        select(BackgroundJob.id)
        .where(
            BackgroundJob.kind.in_(("gamedata_update", "rederive")),
            BackgroundJob.status.in_(("queued", "running")),
        )
        .limit(1)
    )
    return {
        "active": _version_out(active) if active else None,
        "versions": [_version_out(v) for v in versions],
        "last_check": get_setting(session, "gamedata.last_check"),
        "last_error": last_failed.error if last_failed else None,
        "last_errors": last_failed.errors if last_failed else None,
        "update_pending": pending is not None,
        "auto_update": container.settings.gamedata_auto_update,
        "interval_hours": container.settings.gamedata_update_interval_hours,
        "dependent_analyses": DEPENDENT_ANALYSES,
    }


@router.get("/sources", response_model=list[dict[str, Any]])
def sources(
    auth: AuthContext = Depends(get_auth), container: Container = Depends(get_container)
) -> list[dict[str, Any]]:
    urls = source_urls(container.settings)
    return [
        {
            "id": "pokeminers",
            "name": {"text": "PokeMiners Game Master"},
            "url": urls["pokeminers"],
            "license": {
                "code": "LICENSE_NONE",
                "text": "Geen licentie vermeld; "
                "gegevens uit de game. OAK downloadt ze tijdens gebruik en verspreidt ze niet.",
            },
            "role": {"code": "ROLE_PRIMARY", "text": "primair"},
        },
        {
            "id": "pvpoke",
            "name": {"code": "SOURCE_PVPOKE", "text": "PvPoke gamemaster en rankings"},
            "url": urls["pvpoke"],
            "license": {"text": "MIT"},
            "role": {"code": "ROLE_SUPPLEMENT", "text": "aanvullend: namen, legacy-aanvallen, league-rankings"},
        },
    ]


@router.get("/check", response_model=dict[str, Any])
async def check(auth: AuthContext = Depends(get_auth), container: Container = Depends(get_container)) -> dict[str, Any]:
    return await run_in_threadpool(container.gamedata.check_remote)


@router.post("/update", response_model=dict[str, Any], status_code=202)
def update(
    auth: AuthContext = Depends(require_owner),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    audit(session, auth.user.id, "gamedata_update_requested", None, container)
    session.commit()
    enqueue(container, "gamedata_update")
    return {"queued": True}


@router.post("/upload", response_model=dict[str, Any])
async def upload(
    request: Request,
    auth: AuthContext = Depends(require_owner),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Offline installation: upload the source files by hand. The fields are ``pokeminers``
    and optionally ``pvpoke`` and ``rankings_great``, ``rankings_ultra`` and ``rankings_master``.
    The body is only read after the owner check, and never beyond the limit (audit A04)."""
    form = await bounded_form(request, MAX_GAMEDATA_UPLOAD * len(UPLOAD_FIELDS), max_files=len(UPLOAD_FIELDS))
    files: dict[str, bytes] = {}
    try:
        for field_name, source_id in UPLOAD_FIELDS.items():
            upload_file = form_file(form, field_name)
            if upload_file is None:
                continue
            content = await upload_file.read(MAX_GAMEDATA_UPLOAD + 1)
            if len(content) > MAX_GAMEDATA_UPLOAD:
                raise PayloadTooLargeError("Bestand te groot.", context="game_data_file")
            files[source_id] = content
    finally:
        await form.close()
    if "pokeminers" not in files:
        raise ValidationFailedError(
            "Het Game Master-bestand van PokeMiners is verplicht.", code="FILE_REQUIRED", context="game_master"
        )
    result = await run_in_threadpool(container.gamedata.update_from_upload, files)
    if result.status == "activated":
        enqueue_rederive(container)
    return {
        "status": result.status,
        "message": result.text,
        "version_id": result.version_id,
        "warnings": result.warnings,
        "errors": result.errors,
    }


@router.post("/versions/{version_id}/activate", response_model=dict[str, Any])
def activate(
    version_id: int,
    auth: AuthContext = Depends(require_owner),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Roll back (or forward) to a kept version."""
    session.commit()
    container.gamedata.activate(version_id)
    audit(session, auth.user.id, "gamedata_activated", str(version_id), container)
    session.commit()
    enqueue_rederive(container)
    return {"active": version_id}
