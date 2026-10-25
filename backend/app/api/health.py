"""Liveness and readiness probes (spec §20.8)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(request: Request) -> JSONResponse:
    container = getattr(request.app.state, "container", None)
    if container is None:
        return JSONResponse({"status": "starting"}, status_code=503)
    try:
        with container.db.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "database_unavailable"}, status_code=503)
    return JSONResponse({"status": "ok", "game_data": container.gamedata.active() is not None})
