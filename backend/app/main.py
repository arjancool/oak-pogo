"""Application factory. Started with ``uvicorn --factory app.main:create_app``."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app import __version__
from app.api.health import router as health_router
from app.api.v1 import router as v1_router
from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.core.container import Container
from app.core.db import Database, create_sqlite_engine
from app.core.errors import AppError, RateLimitedError
from app.core.logging import configure_logging
from app.core.middleware import (
    RequestLogMiddleware,
    SecurityHeadersMiddleware,
    content_security_policy,
)
from app.core.migrations import migrate
from app.gamedata.store import GameDataStore
from app.ingestion.processor import ImportProcessor
from app.jobs.runner import JobRunner
from app.jobs.tasks import register_tasks, schedule_outdated_analyses
from app.services.settings import load_sprite_template

log = logging.getLogger("oak")
DEFAULT_FRONTEND_DIR = Path(__file__).resolve().parent / "static"


def build_container(settings: Settings, clock: Clock | None = None) -> Container:
    settings.ensure_directories()
    clock = clock or SystemClock()
    engine = create_sqlite_engine(settings.database_url)
    migrate(settings, engine)
    db = Database(engine)
    secret, generated = settings.resolve_secret_key()
    gamedata = GameDataStore(settings, db)
    runner = JobRunner(db, clock)
    processor = ImportProcessor(settings, db, gamedata, clock)
    container = Container(
        settings=settings,
        db=db,
        clock=clock,
        secret=secret,
        secret_generated=generated,
        gamedata=gamedata,
        runner=runner,
        processor=processor,
        started_at=clock.now(),
    )
    register_tasks(container)
    container.sprite_template = load_sprite_template(db, settings)
    gamedata.load_active()
    runner.recover()
    schedule_outdated_analyses(container)
    return container


def create_app(settings: Settings | None = None, clock: Clock | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = build_container(settings, clock)
        app.state.container = container
        if container.secret_generated:
            log.warning("OAK_SECRET_KEY not set; using a generated key stored in the data directory")
        if settings.start_worker:
            container.runner.start()
            container.runner.notify()
        log.info("OAK started", extra={"version": __version__, "env": settings.env})
        try:
            yield
        finally:
            container.runner.stop()
            container.db.engine.dispose()

    app = FastAPI(
        title="OAK — Pokémon GO Manager",
        version=__version__,
        lifespan=lifespan,
        # In production neither the interactive docs nor the schema are published.
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
    )

    def csp() -> str:
        container: Container | None = getattr(app.state, "container", None)
        template = container.sprite_template if container is not None else settings.sprite_url_template
        return content_security_policy(template)

    app.add_middleware(SecurityHeadersMiddleware, https=settings.secure_cookies, csp_provider=csp)
    app.add_middleware(RequestLogMiddleware)
    if settings.trusted_proxies:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.trusted_proxies)

    _register_error_handlers(app)
    _register_routes(app)
    _register_frontend(app, settings.frontend_dir or DEFAULT_FRONTEND_DIR)
    return app


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        headers = {"Retry-After": str(exc.retry_after)} if isinstance(exc, RateLimitedError) else None
        return JSONResponse(exc.to_payload(), status_code=exc.status_code, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "loc": [str(p) for p in err.get("loc", [])],
                "msg": err.get("msg"),
                "type": err.get("type"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            {
                "error": {
                    "code": "VALIDATION_FAILED",
                    "message": "De invoer is ongeldig.",
                    "details": details,
                }
            },
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        message = "Niet gevonden." if exc.status_code == 404 else str(exc.detail)
        return JSONResponse(
            {"error": {"code": code, "message": message, "details": None}},
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return JSONResponse(
            {
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Er ging iets mis aan de serverkant.",
                    "details": None,
                }
            },
            status_code=500,
        )


def _register_routes(app: FastAPI) -> None:
    app.include_router(health_router)
    app.include_router(v1_router, prefix="/api/v1")


def _register_frontend(app: FastAPI, frontend_dir: Path) -> None:
    index = frontend_dir / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> Response:
        if full_path.startswith(("api/", "health/")):
            return JSONResponse(
                {"error": {"code": "NOT_FOUND", "message": "Niet gevonden.", "details": None}},
                status_code=404,
            )
        candidate = (frontend_dir / full_path).resolve()
        if full_path and candidate.is_file() and frontend_dir.resolve() in candidate.parents:
            cache = "public, max-age=31536000, immutable" if full_path.startswith("assets/") else "no-cache"
            return FileResponse(candidate, headers={"Cache-Control": cache})
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return JSONResponse(
            {
                "error": {
                    "code": "FRONTEND_MISSING",
                    "message": "De frontend is niet gebouwd.",
                    "details": None,
                }
            },
            status_code=404,
        )
