"""Upcoming events and their effect on the cleanup advice (ADR-0021)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth, get_container, get_session, owned_account, require_owner
from app.core.container import Container
from app.core.errors import NotFoundError, ValidationFailedError
from app.jobs.tasks import enqueue
from app.models import GameEvent, PokemonAnalysis
from app.recommendations.events import MANUAL, relevant
from app.services.analysis import rules_for
from app.services.events import (
    FEED,
    IGNORED_KEY,
    account_events,
    event_info,
    feed_status,
    ignored_events,
    species_for,
)

router = APIRouter(prefix="/events", tags=["events"])
MAX_DAYS = 365
MAX_SPECIES = 20


def _held_counts(session: Session, account_id: int) -> dict[str, int]:
    """How many of the account's Pokémon the latest analysis holds, per event."""
    counts: dict[str, int] = {}
    for reasons in session.scalars(
        select(PokemonAnalysis.reasons).where(PokemonAnalysis.trainer_account_id == account_id)
    ):
        for reason in reasons or []:
            if reason.get("code") == "EVENT_HOLD":
                event_id = str((reason.get("data") or {}).get("event_id"))
                counts[event_id] = counts.get(event_id, 0) + 1
    return counts


@router.get("", response_model=dict[str, Any])
def list_events(
    account_id: int,
    days: int = Query(60, ge=1, le=MAX_DAYS),
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    account = owned_account(session, auth.user, account_id)
    rules = rules_for(account)
    gd = container.gamedata.active()
    now = container.clock.now()
    ignored = ignored_events(account)
    held = _held_counts(session, account.id)
    infos = [(event, event_info(event, gd)) for event in account_events(session, account.id)]
    # Events the rules use now: within reach, not ignored, and only when events are switched on.
    usable = (i for e, i in infos if e.source == MANUAL or e.external_id not in ignored)
    in_reach = {e.id for e in relevant(usable, now, rules.event_hold_days)} if rules.use_events else set()
    limit = now + timedelta(days=days)
    items = []
    for event, info in infos:
        if event.ends_at <= now or event.starts_at > limit:
            continue
        if event.source == MANUAL:
            species = [
                {"dex": d, "name": (gd.species_record(d) or {}).get("name") if gd else None} for d in event.featured_dex
            ]
            unknown: list[str] = []
        elif gd is not None:
            dex, unknown = species_for(event.featured, gd)
            species = [{"dex": d, "name": (gd.species_record(d) or {}).get("name")} for d in dex]
        else:
            species, unknown = [], list(event.featured)
        items.append(
            {
                "id": event.id,
                "external_id": event.external_id,
                "source": info.source,
                "name": event.name,
                "kind": info.kind,
                "starts_at": event.starts_at.isoformat(),
                "ends_at": event.ends_at.isoformat(),
                "local_time": event.local_time,
                "link": event.link,
                "species": species,
                "unknown_names": unknown,
                "bonuses": list(event.bonuses),
                "transfer_bonus": info.transfer_bonus,
                "ignored": event.source == FEED and event.external_id in ignored,
                "in_reach": info.id in in_reach,
                "held": held.get(info.id, 0),
            }
        )
    return {
        "feed": feed_status(session, container.settings),
        "rules": {"use_events": rules.use_events, "event_hold_days": rules.event_hold_days},
        "game_data_version": gd.version_id if gd else None,
        "events": items,
    }


class IgnoreBody(BaseModel):
    account_id: int
    ignored: bool


@router.put("/{external_id}/ignore", response_model=dict[str, Any])
def ignore_event(
    external_id: str,
    body: IgnoreBody,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    account = owned_account(session, auth.user, body.account_id)
    exists = session.scalar(
        select(GameEvent.id).where(GameEvent.source == FEED, GameEvent.external_id == external_id).limit(1)
    )
    if exists is None:
        raise NotFoundError("Event niet gevonden.")
    ignored = ignored_events(account)
    ignored = ignored | {external_id} if body.ignored else ignored - {external_id}
    account.settings = {**(account.settings or {}), IGNORED_KEY: sorted(ignored)}
    session.commit()
    enqueue(container, "analysis", account.id)
    return {"external_id": external_id, "ignored": body.ignored}


class ManualEventBody(BaseModel):
    account_id: int
    name: str = Field(min_length=1, max_length=200)
    starts_at: datetime
    ends_at: datetime
    species: list[int] = Field(min_length=1, max_length=MAX_SPECIES)


@router.post("/manual", response_model=dict[str, Any], status_code=201)
def add_manual_event(
    body: ManualEventBody,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """An event of your own: its Pokémon and their evolution families are kept until it ends."""
    account = owned_account(session, auth.user, body.account_id)
    starts = body.starts_at if body.starts_at.tzinfo else body.starts_at.replace(tzinfo=UTC)
    ends = body.ends_at if body.ends_at.tzinfo else body.ends_at.replace(tzinfo=UTC)
    if ends <= starts:
        raise ValidationFailedError("Het einde moet na het begin liggen.")
    gd = container.gamedata.active()
    species = list(dict.fromkeys(body.species))
    if gd is not None and any(gd.species_record(d) is None for d in species):
        raise ValidationFailedError("Een van de gekozen Pokémon staat niet in de Game Data.")
    event = GameEvent(
        source=MANUAL,
        external_id=f"manual-{uuid.uuid4().hex[:12]}",
        trainer_account_id=account.id,
        name=body.name.strip(),
        kind=MANUAL,
        starts_at=starts.astimezone(UTC),
        ends_at=ends.astimezone(UTC),
        local_time=False,
        link=None,
        featured=[],
        featured_dex=species,
        bonuses=[],
        feed_version=None,
        created_at=container.clock.now(),
    )
    session.add(event)
    session.commit()
    enqueue(container, "analysis", account.id)
    return {"id": event.id, "external_id": event.external_id}


@router.delete("/manual/{event_id}", status_code=204)
def delete_manual_event(
    event_id: int,
    account_id: int,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> Response:
    account = owned_account(session, auth.user, account_id)
    event = session.get(GameEvent, event_id)
    if event is None or event.source != MANUAL or event.trainer_account_id != account.id:
        raise NotFoundError("Event niet gevonden.")
    session.delete(event)
    session.commit()
    enqueue(container, "analysis", account.id)
    return Response(status_code=204)


@router.post("/update", response_model=dict[str, Any], status_code=202)
def update_now(
    auth: AuthContext = Depends(require_owner),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    session.commit()
    enqueue(container, "events_update")
    return {"queued": True}
