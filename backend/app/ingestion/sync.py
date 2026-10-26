"""Applying a classified export to the stored state of one trainer account (spec §4.6, steps
11–14). Runs inside the caller's ``BEGIN IMMEDIATE`` transaction, so either everything below is
committed or nothing is.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.domain.changes import STATE_FIELDS, diff_state, snapshot_of
from app.domain.classification import Classification, ImportKind
from app.domain.pokemon import NormalizedExport, NormalizedPokemon
from app.gamedata.model import GameData
from app.ingestion.derive import apply_derived
from app.models import (
    ImportJob,
    InventorySnapshot,
    ItemInventory,
    Pokemon,
    PokemonChangeEvent,
    SyncRun,
    TrainerAccount,
)

IN_INVENTORY = "in_inventory"
NOT_IN_INVENTORY = "not_in_inventory"


def stored_state(row: Pokemon) -> dict[str, Any]:
    return {name: getattr(row, name) for name in STATE_FIELDS}


def _write_state(row: Pokemon, observed: NormalizedPokemon) -> None:
    for name in STATE_FIELDS:
        setattr(row, name, getattr(observed, name))


def apply_export(
    session: Session,
    *,
    account: TrainerAccount,
    export: NormalizedExport,
    classification: Classification,
    job: ImportJob,
    gd: GameData | None,
    tz: ZoneInfo,
    now: datetime,
) -> SyncRun:
    full = classification.kind is ImportKind.FULL
    previous_run_id = session.scalar(
        select(SyncRun.id).where(SyncRun.trainer_account_id == account.id).order_by(SyncRun.id.desc()).limit(1)
    )
    run = SyncRun(
        trainer_account_id=account.id,
        import_job_id=job.id,
        source=job.source,
        classification=classification.kind.value,
        export_time=export.export_time,
        applied_at=now,
        total_pokemon=len(export.pokemon),
        eggs=export.eggs,
        warnings=[{"code": r.code, "message": r.message, "data": r.data} for r in classification.reasons],
        previous_sync_run_id=previous_run_id,
    )
    session.add(run)
    session.flush()

    existing: dict[str, Pokemon] = {
        row.source_pokemon_id: row
        for row in session.scalars(select(Pokemon).where(Pokemon.trainer_account_id == account.id))
    }
    events: list[dict[str, Any]] = []
    new_rows: list[tuple[Pokemon, NormalizedPokemon]] = []
    changed = unchanged = reappeared = 0

    for observed in export.pokemon:
        row = existing.get(observed.source_pokemon_id)
        if row is None:
            row = Pokemon(
                trainer_account_id=account.id,
                source_pokemon_id=observed.source_pokemon_id,
                inventory_status=IN_INVENTORY,
                first_seen_at=now,
                last_seen_at=now,
                last_changed_at=now,
                first_seen_sync_id=run.id,
                last_seen_sync_id=run.id,
            )
            _write_state(row, observed)
            apply_derived(row, gd, tz)
            session.add(row)
            new_rows.append((row, observed))
            continue

        diff = diff_state(stored_state(row), observed)
        was_missing = row.inventory_status == NOT_IN_INVENTORY
        if diff.has_changes:
            _write_state(row, observed)
        # Any change, also a quiet one such as a corrected catch date, recomputes the derived
        # columns: the catch year drives the vintage protection (audit F01 of 25 October).
        if diff.has_changes or was_missing or row.derived_version_id != (gd.version_id if gd else None):
            apply_derived(row, gd, tz)
        row.last_seen_at = now
        row.last_seen_sync_id = run.id
        if was_missing:
            row.inventory_status = IN_INVENTORY
            row.disappeared_at = None
            row.disappeared_sync_id = None
            reappeared += 1
            events.append(_event(account.id, row.id, run.id, "REAPPEARED", diff.significant, now))
        elif diff.significant:
            changed += 1
            events.append(_event(account.id, row.id, run.id, "CHANGED", diff.significant, now))
        else:
            unchanged += 1
        if diff.significant:
            row.last_changed_at = now

    # Records with a readable ID but unreadable content prove the Pokémon is still there.
    for source_id in export.unreadable_records:
        row = existing.get(source_id)
        if row is not None:
            row.last_seen_at = now
            row.last_seen_sync_id = run.id
            unchanged += 1

    session.flush()
    for row, observed in new_rows:
        events.append(_event(account.id, row.id, run.id, "APPEARED", snapshot_of(observed), now))

    seen = {p.source_pokemon_id for p in export.pokemon} | set(export.unreadable_records)
    missing_rows = [row for sid, row in existing.items() if sid not in seen and row.inventory_status == IN_INVENTORY]
    missing = unconfirmed = 0
    if full:
        for row in missing_rows:
            row.inventory_status = NOT_IN_INVENTORY
            row.disappeared_at = now
            row.disappeared_sync_id = run.id
            missing += 1
            events.append(
                _event(
                    account.id,
                    row.id,
                    run.id,
                    "DISAPPEARED",
                    {"last_seen_at": row.last_seen_at.isoformat()},
                    now,
                )
            )
    else:
        unconfirmed = len(missing_rows)

    if events:
        session.execute(insert(PokemonChangeEvent), events)

    run.new_count = len(new_rows)
    run.changed_count = changed
    run.unchanged_count = unchanged
    run.missing_count = missing
    run.missing_unconfirmed_count = unconfirmed
    run.reappeared_count = reappeared
    run.items_changed = _apply_items(session, account, export, run, full=full, now=now)
    _apply_trainer(account, export, now)
    return run


def _event(
    account_id: int, pokemon_id: int, run_id: int, kind: str, changes: dict[str, Any], now: datetime
) -> dict[str, Any]:
    return {
        "trainer_account_id": account_id,
        "pokemon_id": pokemon_id,
        "sync_run_id": run_id,
        "event_type": kind,
        "changes": changes,
        "occurred_at": now,
    }


def _apply_items(
    session: Session,
    account: TrainerAccount,
    export: NormalizedExport,
    run: SyncRun,
    *,
    full: bool,
    now: datetime,
) -> bool:
    if not export.has_items_list:
        return False
    current = {
        row.item_id: row
        for row in session.scalars(select(ItemInventory).where(ItemInventory.trainer_account_id == account.id))
    }
    incoming = {item.item_id: item for item in export.items}
    changed = False
    for item_id, item in incoming.items():
        row = current.get(item_id)
        if row is None:
            session.add(
                ItemInventory(
                    trainer_account_id=account.id,
                    item_id=item_id,
                    item_name=item.name,
                    count=item.count,
                    updated_at=now,
                )
            )
            changed = True
        elif row.count != item.count or row.item_name != item.name:
            row.count = item.count
            row.item_name = item.name or row.item_name
            row.updated_at = now
            changed = True
    if full:
        gone = [item_id for item_id in current if item_id not in incoming]
        if gone:
            session.execute(
                delete(ItemInventory).where(
                    ItemInventory.trainer_account_id == account.id, ItemInventory.item_id.in_(gone)
                )
            )
            changed = True
    trainer = {k: v for k, v in asdict(export.trainer).items() if k != "stats"}
    last_snapshot = session.scalars(
        select(InventorySnapshot)
        .where(InventorySnapshot.trainer_account_id == account.id)
        .order_by(InventorySnapshot.id.desc())
        .limit(1)
    ).first()
    items_map = {str(k): v.count for k, v in sorted(incoming.items())}
    if last_snapshot is None or last_snapshot.items != items_map or last_snapshot.trainer != trainer:
        session.add(
            InventorySnapshot(
                trainer_account_id=account.id,
                sync_run_id=run.id,
                items=items_map,
                trainer=trainer,
                created_at=now,
            )
        )
    return changed


def _apply_trainer(account: TrainerAccount, export: NormalizedExport, now: datetime) -> None:
    trainer = export.trainer
    for attr, value in (
        ("source_nickname", trainer.nickname),
        ("trainer_level", trainer.level),
        ("experience", trainer.experience),
        ("stardust", trainer.stardust),
        ("pokecoins", trainer.pokecoins),
        ("team", trainer.team),
        ("max_pokemon_storage", trainer.max_pokemon_storage),
        ("max_item_storage", trainer.max_item_storage),
    ):
        if value is not None:
            setattr(account, attr, value)
    if trainer.stats:
        account.stats = trainer.stats
    if export.export_time is not None:
        account.last_export_time = export.export_time
    account.last_successful_sync_at = now


def in_inventory_count(session: Session, account_id: int) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(Pokemon)
            .where(Pokemon.trainer_account_id == account_id, Pokemon.inventory_status == IN_INVENTORY)
        )
        or 0
    )
