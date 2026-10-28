"""Dashboard, trainer statistics, item bag, manual resources, history and exports
(spec §8, §16, §17, §26.3)."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import String, and_, func, or_, select, type_coerce
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth, get_container, get_session, owned_account
from app.api.v1.pokemon import sync_bounds, tag_label_map
from app.core.container import Container
from app.core.errors import ValidationFailedError
from app.domain.changes import change_labels
from app.domain.pokemon import VINTAGE_FIRST_YEAR, VINTAGE_LAST_YEAR
from app.models import (
    InventorySnapshot,
    ItemInventory,
    ManualResource,
    PlannedAction,
    Pokemon,
    PokemonAnalysis,
    PokemonChangeEvent,
    PokemonUserMetadata,
    SyncRun,
    TagLabel,
)
from app.services.pokemon_view import summarize

router = APIRouter(tags=["account"])
DASHBOARD_LIST = 12
HISTORY_LIMIT = 500

# Dutch names and groups for PGSharp ``itemName`` values. Unknown names fall back to the
# CamelCase name split into words, and the group from the Game Data item category.
ITEM_NAMES: dict[str, tuple[str, str]] = {
    "PokeBall": ("Poké Ball", "balls"),
    "GreatBall": ("Great Ball", "balls"),
    "UltraBall": ("Ultra Ball", "balls"),
    "MasterBall": ("Master Ball", "balls"),
    "PremierBall": ("Premier Ball", "balls"),
    "Potion": ("Potion", "healing"),
    "SuperPotion": ("Super Potion", "healing"),
    "HyperPotion": ("Hyper Potion", "healing"),
    "MaxPotion": ("Max Potion", "healing"),
    "Revive": ("Revive", "healing"),
    "MaxRevive": ("Max Revive", "healing"),
    "RazzBerry": ("Razz Berry", "berries"),
    "NanabBerry": ("Nanab Berry", "berries"),
    "PinapBerry": ("Pinap Berry", "berries"),
    "GoldenRazzBerry": ("Golden Razz Berry", "berries"),
    "GoldenPinapBerry": ("Silver Pinap Berry", "berries"),
    "RareCandy": ("Rare Candy", "candy"),
    "XlRareCandy": ("Rare Candy XL", "candy"),
    "MoveRerollFastAttack": ("Fast TM", "tm"),
    "MoveRerollSpecialAttack": ("Charged TM", "tm"),
    "MoveRerollEliteFastAttack": ("Elite Fast TM", "tm"),
    "MoveRerollEliteSpecialAttack": ("Elite Charged TM", "tm"),
    "FreeRaidTicket": ("Raid Pass", "raid"),
    "PaidRaidTicket": ("Premium Battle Pass", "raid"),
    "RemoteRaidTicket": ("Remote Raid Pass", "raid"),
    "LegendaryRaidTicket": ("Legendary Raid Pass", "raid"),
    "SunStone": ("Sun Stone", "evolution"),
    "KingsRock": ("King's Rock", "evolution"),
    "MetalCoat": ("Metal Coat", "evolution"),
    "DragonScale": ("Dragon Scale", "evolution"),
    "UpGrade": ("Up-Grade", "evolution"),
    "Gen4EvolutionStone": ("Sinnoh Stone", "evolution"),
    "Gen5EvolutionStone": ("Unova Stone", "evolution"),
    "OtherEvolutionStoneA": ("Magnetisch lokmiddel-steen (A)", "evolution"),
    "IncenseOrdinary": ("Incense", "incense"),
    "IncenseDailyAdventure": ("Daily Adventure Incense", "incense"),
    "TroyDisk": ("Lure Module", "incense"),
    "TroyDiskMossy": ("Mossy Lure Module", "incense"),
    "TroyDiskGlacial": ("Glacial Lure Module", "incense"),
    "TroyDiskMagnetic": ("Magnetic Lure Module", "incense"),
    "TroyDiskRainy": ("Rainy Lure Module", "incense"),
    "LuckyEgg": ("Lucky Egg", "boosts"),
    "StarPiece": ("Star Piece", "boosts"),
    "IncubatorBasicUnlimited": ("Onbeperkte broedmachine", "incubators"),
    "IncubatorBasic": ("Broedmachine", "incubators"),
    "IncubatorSuper": ("Super-broedmachine", "incubators"),
    "IncubatorSpecial": ("Speciale broedmachine", "incubators"),
    "LeaderMapFragment": ("Mysterieus onderdeel", "rocket"),
    "LeaderMap": ("Rocket Radar", "rocket"),
    "GiovanniMap": ("Super Rocket Radar", "rocket"),
    "ShadowGemFragment": ("Shadow-scherf", "rocket"),
    "ShadowGem": ("Shadow-kristal", "rocket"),
    "Mp": ("Max Particles", "max"),
    "SpecialCamera": ("Camera", "other"),
    "Breakfast": ("Poffin", "other"),
    "SoftSfida": ("Vervalste spullen (onbekend)", "other"),
}
ITEM_GROUP_LABELS = {
    "balls": "Poké Balls",
    "healing": "Potions en Revives",
    "berries": "Berries",
    "candy": "Rare Candy",
    "tm": "TM's",
    "raid": "Raid Passes",
    "evolution": "Evolutie-items",
    "incense": "Incense en Lures",
    "boosts": "Boosts",
    "incubators": "Broedmachines",
    "rocket": "Team GO Rocket",
    "max": "Max Battles",
    "event": "Eventpunten",
    "other": "Overig",
}


def _item_label(gd: Any, name: str | None, item_id: int) -> tuple[str, str]:
    if name and name in ITEM_NAMES:
        return ITEM_NAMES[name]
    if name and name.startswith("EventPassPoint"):
        return re.sub(r"(?<=[a-z])(?=[A-Z0-9])", " ", name), "event"
    group = "other"
    if gd is not None and name:
        info = gd.item(name)
        if info and info.get("category") == "evolution_requirement":
            group = "evolution"
    label = re.sub(r"(?<=[a-z])(?=[A-Z0-9])", " ", name) if name else f"Item #{item_id}"
    return label, group


@router.get("/inventory/items", response_model=dict[str, Any])
def items(
    account_id: int,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    account = owned_account(session, auth.user, account_id)
    gd = container.gamedata.active()
    rows = session.scalars(select(ItemInventory).where(ItemInventory.trainer_account_id == account.id)).all()
    entries = []
    for row in rows:
        label, group = _item_label(gd, row.item_name, row.item_id)
        entries.append(
            {
                "item_id": row.item_id,
                "source_name": row.item_name,
                "name": label,
                "group": group,
                "group_label": {
                    "code": "ITEM_GROUP",
                    "text": ITEM_GROUP_LABELS.get(group, group),
                    "data": {"context": group},
                },
                "count": row.count,
                "updated_at": row.updated_at.isoformat(),
                "source": "pgsharp",
            }
        )
    entries.sort(
        key=lambda e: (
            list(ITEM_GROUP_LABELS).index(e["group"]) if e["group"] in ITEM_GROUP_LABELS else 99,
            e["item_id"],
        )
    )
    total = sum(e["count"] for e in entries if e["group"] not in ("event",))
    return {
        "items": entries,
        "total": total,
        "max_item_storage": account.max_item_storage,
        "note": {
            "code": "ITEMS_FROM_EXPORT",
            "text": "Item-aantallen komen uit de PGSharp-export. Eventpunten tellen niet mee voor de opslag.",
        },
    }


@router.get("/trainer", response_model=dict[str, Any])
def trainer(
    account_id: int,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    account = owned_account(session, auth.user, account_id)
    pokemon = (
        session.scalar(
            select(func.count())
            .select_from(Pokemon)
            .where(Pokemon.trainer_account_id == account.id, Pokemon.inventory_status == "in_inventory")
        )
        or 0
    )
    last_run = session.scalars(
        select(SyncRun).where(SyncRun.trainer_account_id == account.id).order_by(SyncRun.id.desc()).limit(1)
    ).first()
    eggs = last_run.eggs if last_run else 0
    return {
        "nickname": account.nickname,
        "source_nickname": account.source_nickname,
        "level": account.trainer_level,
        "experience": account.experience,
        "stardust": account.stardust,
        "pokecoins": account.pokecoins,
        "team": account.team,
        "storage": {"pokemon": pokemon, "eggs": eggs, "max": account.max_pokemon_storage},
        "item_storage_max": account.max_item_storage,
        "stats": account.stats or {},
        "last_successful_sync_at": account.last_successful_sync_at.isoformat()
        if account.last_successful_sync_at
        else None,
        "source": "pgsharp",
    }


class ResourceIn(BaseModel):
    account_id: int
    kind: str = Field(pattern="^(candy|xl_candy|mega)$")
    key: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=0, le=1_000_000)


@router.get("/resources", response_model=list[dict[str, Any]])
def resources(
    account_id: int, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    account = owned_account(session, auth.user, account_id)
    rows = session.scalars(
        select(ManualResource).where(ManualResource.trainer_account_id == account.id).order_by(ManualResource.key)
    ).all()
    return [
        {
            "kind": r.kind,
            "key": r.key,
            "quantity": r.quantity,
            "updated_at": r.updated_at.isoformat(),
            "source": "manual",
        }
        for r in rows
    ]


@router.put("/resources", response_model=dict[str, Any])
def set_resource(
    body: ResourceIn,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """PGSharp does not export species candy; the user may enter it by hand (spec §16.3)."""
    account = owned_account(session, auth.user, body.account_id)
    if not re.fullmatch(r"FAMILY_[A-Z0-9_]+", body.key):
        raise ValidationFailedError("Gebruik een familie-ID, bijvoorbeeld FAMILY_MAGIKARP.", context="family_id")
    row = session.get(ManualResource, (account.id, body.kind, body.key))
    now = container.clock.now()
    if row is None:
        session.add(
            ManualResource(
                trainer_account_id=account.id,
                kind=body.kind,
                key=body.key,
                quantity=body.quantity,
                updated_at=now,
            )
        )
    else:
        row.quantity = body.quantity
        row.updated_at = now
    return {"kind": body.kind, "key": body.key, "quantity": body.quantity, "source": "manual"}


@router.get("/history/changes", response_model=dict[str, Any])
def history_changes(
    account_id: int,
    kind: str = Query(default="new", pattern="^(new|missing|changed|reappeared)$"),
    sync_run_id: int | None = None,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    account = owned_account(session, auth.user, account_id)
    event_type = {
        "new": "APPEARED",
        "missing": "DISAPPEARED",
        "changed": "CHANGED",
        "reappeared": "REAPPEARED",
    }[kind]
    runs = session.scalars(
        select(SyncRun).where(SyncRun.trainer_account_id == account.id).order_by(SyncRun.id.desc()).limit(50)
    ).all()
    if sync_run_id is None:
        candidates = [r for r in runs if kind != "new" or r.previous_sync_run_id is not None]
        target = candidates[0] if candidates else None
    else:
        target = next((r for r in runs if r.id == sync_run_id), None)
    if target is None:
        return {
            "kind": kind,
            "sync_run": None,
            "items": [],
            "runs": _runs(runs),
            "note": {
                "code": "FIRST_SYNC",
                "text": "Bij de eerste synchronisatie is alles nieuw; vergelijking begint vanaf de tweede.",
            },
        }
    rows = session.execute(
        select(PokemonChangeEvent, Pokemon, PokemonUserMetadata, PokemonAnalysis)
        .join(Pokemon, Pokemon.id == PokemonChangeEvent.pokemon_id)
        .outerjoin(PokemonUserMetadata, PokemonUserMetadata.pokemon_id == Pokemon.id)
        .outerjoin(PokemonAnalysis, PokemonAnalysis.pokemon_id == Pokemon.id)
        .where(
            PokemonChangeEvent.trainer_account_id == account.id,
            PokemonChangeEvent.sync_run_id == target.id,
            PokemonChangeEvent.event_type == event_type,
        )
        .order_by(Pokemon.cp.desc())
        .limit(HISTORY_LIMIT)
    ).all()
    gd = container.gamedata.active()
    labels = tag_label_map(session, account.id)
    items = []
    for event, pokemon, meta, analysis in rows:
        items.append(
            {
                "pokemon": summarize(pokemon, meta, analysis, gd, tag_labels=labels).model_dump(mode="json"),
                "labels": change_labels(event.changes) if event.event_type == "CHANGED" else [],
                "changes": event.changes if event.event_type == "CHANGED" else {},
            }
        )
    return {
        "kind": kind,
        "sync_run": {
            "id": target.id,
            "applied_at": target.applied_at.isoformat(),
            "classification": target.classification,
        },
        "items": items,
        "runs": _runs(runs),
    }


def _runs(runs: Sequence[SyncRun]) -> list[dict[str, Any]]:
    return [
        {
            "id": r.id,
            "applied_at": r.applied_at.isoformat(),
            "classification": r.classification,
            "new": r.new_count,
            "changed": r.changed_count,
            "missing": r.missing_count,
        }
        for r in runs
    ]


@router.get("/history/inventory", response_model=list[dict[str, Any]])
def history_inventory(
    account_id: int, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    account = owned_account(session, auth.user, account_id)
    snapshots = session.scalars(
        select(InventorySnapshot)
        .where(InventorySnapshot.trainer_account_id == account.id)
        .order_by(InventorySnapshot.id.desc())
        .limit(200)
    ).all()
    return [
        {
            "at": s.created_at.isoformat(),
            "sync_run_id": s.sync_run_id,
            "stardust": s.trainer.get("stardust"),
            "level": s.trainer.get("level"),
            "experience": s.trainer.get("experience"),
            "items_total": sum(s.items.values()),
        }
        for s in reversed(snapshots)
    ]


@router.get("/dashboard", response_model=dict[str, Any])
def dashboard(
    account_id: int,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    account = owned_account(session, auth.user, account_id)
    gd = container.gamedata.active()
    base = and_(Pokemon.trainer_account_id == account.id, Pokemon.inventory_status == "in_inventory")
    hundo = and_(Pokemon.iv_attack == 15, Pokemon.iv_defense == 15, Pokemon.iv_stamina == 15)

    def count(*conditions: Any) -> int:
        return int(session.scalar(select(func.count()).select_from(Pokemon).where(base, *conditions)) or 0)

    statuses = dict(
        session.execute(
            select(PokemonAnalysis.status, func.count())
            .join(Pokemon, Pokemon.id == PokemonAnalysis.pokemon_id)
            .where(base)
            .group_by(PokemonAnalysis.status)
        ).all()
    )
    total = count()
    latest, first = sync_bounds(session, account.id)
    labels = tag_label_map(session, account.id)

    def listing(stmt: Any) -> list[dict[str, Any]]:
        rows: list[Any] = list(session.execute(stmt.limit(DASHBOARD_LIST)).all())
        return [
            summarize(r[0], r[1], r[2], gd, tag_labels=labels, latest_sync_id=latest, first_sync_id=first).model_dump(
                mode="json"
            )
            for r in rows
        ]

    select_all = (
        select(Pokemon, PokemonUserMetadata, PokemonAnalysis)
        .outerjoin(PokemonUserMetadata, PokemonUserMetadata.pokemon_id == Pokemon.id)
        .outerjoin(PokemonAnalysis, PokemonAnalysis.pokemon_id == Pokemon.id)
    )
    last_run = session.get(SyncRun, latest) if latest else None
    new_list = (
        listing(select_all.where(base, Pokemon.first_seen_sync_id == latest).order_by(Pokemon.caught_at.desc()))
        if last_run and last_run.previous_sync_run_id
        else []
    )
    valuable_new = [p for p in new_list if p["shiny"] or p["hundo"] or p["lucky"] or p["pokemon_class"]]
    missing = (
        listing(
            select_all.where(Pokemon.trainer_account_id == account.id, Pokemon.disappeared_sync_id == latest).order_by(
                Pokemon.cp.desc()
            )
        )
        if latest
        else []
    )
    favorite_changes = (
        session.scalar(
            select(func.count())
            .select_from(PokemonChangeEvent)
            .where(
                PokemonChangeEvent.trainer_account_id == account.id,
                PokemonChangeEvent.sync_run_id == latest,
                PokemonChangeEvent.event_type == "CHANGED",
                type_coerce(PokemonChangeEvent.changes, String).like('%"favorite"%'),
            )
        )
        if latest
        else 0
    )
    action_list = (
        session.scalar(
            select(func.count())
            .select_from(PlannedAction)
            .where(
                PlannedAction.trainer_account_id == account.id,
                PlannedAction.list_name == "cleanup",
                PlannedAction.status == "open",
            )
        )
        or 0
    )
    return {
        "cards": {
            "total": total,
            "shiny": count(Pokemon.shiny.is_(True)),
            "lucky": count(Pokemon.lucky.is_(True)),
            "shadow": count(Pokemon.alignment == 1),
            "purified": count(Pokemon.alignment == 2),
            "hundo": count(hundo),
            "shundo": count(hundo, Pokemon.shiny.is_(True)),
            "favorite": count(Pokemon.favorite.is_(True)),
            "vintage": count(Pokemon.caught_year >= VINTAGE_FIRST_YEAR, Pokemon.caught_year <= VINTAGE_LAST_YEAR),
            "review": statuses.get("REVIEW", 0),
            "legendary": count(Pokemon.pokemon_class == "legendary"),
            "mythical": count(Pokemon.pokemon_class == "mythical"),
            "ultra_beast": count(Pokemon.pokemon_class == "ultra_beast"),
            "dynamax": count(Pokemon.bread_mode == 1),
            "gigantamax": count(Pokemon.bread_mode == 2),
            "costume": count(or_(Pokemon.costume_id > 0, Pokemon.costume_form.is_(True))),
            "background": count(Pokemon.location_card.is_not(None)),
            "cleanup_candidates": int(statuses.get("TRANSFER_CANDIDATE", 0)),
            "stardust": account.stardust,
            "pokecoins": account.pokecoins,
            "trainer_level": account.trainer_level,
            "storage_max": account.max_pokemon_storage,
            "storage_free": (account.max_pokemon_storage - total - (last_run.eggs if last_run else 0))
            if account.max_pokemon_storage
            else None,
            "action_list_open": action_list,
        },
        "cleanup_statuses": statuses,
        "recent_catches": listing(select_all.where(base).order_by(Pokemon.caught_at.desc().nulls_last())),
        "new_since_last_sync": new_list,
        "valuable_new": valuable_new,
        "missing_since_last_sync": missing,
        "favorite_changes": favorite_changes or 0,
        "investment_candidates": listing(
            select_all.where(base, PokemonAnalysis.status == "BUILD").order_by(PokemonAnalysis.great_rank.asc())
        ),
        "top_cleanup": listing(
            select_all.where(base, PokemonAnalysis.status == "TRANSFER_CANDIDATE").order_by(
                PokemonAnalysis.priority.desc()
            )
        ),
        "last_sync": {
            "id": last_run.id,
            "applied_at": last_run.applied_at.isoformat(),
            "classification": last_run.classification,
            "new": last_run.new_count,
            "changed": last_run.changed_count,
            "missing": last_run.missing_count,
            "missing_unconfirmed": last_run.missing_unconfirmed_count,
            "total": last_run.total_pokemon,
            "warnings": last_run.warnings,
        }
        if last_run
        else None,
        "game_data": gd is not None,
        "year_distribution": dict(
            Counter(y for y in session.scalars(select(Pokemon.caught_year).where(base)) if y is not None)
        ),
    }


@router.get("/export/metadata")
def export_metadata(
    account_id: int,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> JSONResponse:
    """OAK's own data for one account: protection, notes, tags, lists. No PGSharp payload."""
    account = owned_account(session, auth.user, account_id)
    rows = session.execute(
        select(PokemonUserMetadata, Pokemon.source_pokemon_id, Pokemon.species_name)
        .join(Pokemon, Pokemon.id == PokemonUserMetadata.pokemon_id)
        .where(PokemonUserMetadata.trainer_account_id == account.id)
    ).all()
    planned = session.execute(
        select(PlannedAction, Pokemon.source_pokemon_id)
        .join(Pokemon, Pokemon.id == PlannedAction.pokemon_id)
        .where(PlannedAction.trainer_account_id == account.id)
    ).all()
    tags = session.scalars(select(TagLabel).where(TagLabel.trainer_account_id == account.id)).all()
    payload = {
        "format": "oak-metadata-v1",
        "exported_at": container.clock.now().isoformat(),
        "account": {"nickname": account.nickname},
        "pokemon": [
            {
                "source_pokemon_id": sid,
                "species": name,
                "protected": m.protected,
                "protection_reason": m.protection_reason,
                "notes": m.notes,
                "tags": m.tags,
                "planned_action": m.planned_action,
                "planned_league": m.planned_league,
                "priority": m.priority,
                "review_status": m.review_status,
                "override_status": m.override_status,
            }
            for m, sid, name in rows
        ],
        "planned_actions": [
            {"source_pokemon_id": sid, "list": p.list_name, "action": p.action, "status": p.status}
            for p, sid in planned
        ],
        "tag_labels": [{"tag_id": t.tag_id, "label": t.label, "protects": t.protects} for t in tags],
    }
    return JSONResponse(payload, headers={"Content-Disposition": 'attachment; filename="oak-metadata.json"'})
