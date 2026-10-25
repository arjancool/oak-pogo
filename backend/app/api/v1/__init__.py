"""Version 1 of the OAK API."""

from fastapi import APIRouter

from app.api.v1 import (
    account_data,
    accounts,
    auth,
    battles,
    cleanup,
    events,
    gamedata,
    imports,
    ingest,
    pokemon,
    sync,
    system,
)

router = APIRouter()
for module in (
    auth,
    accounts,
    ingest,
    imports,
    sync,
    pokemon,
    cleanup,
    battles,
    events,
    gamedata,
    system,
    account_data,
):
    router.include_router(module.router)
