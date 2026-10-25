"""Pokémon state, change history and OAK-owned metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONText, UTCDateTime


class Pokemon(Base):
    """Current state of one Pokémon of one trainer account.

    Columns are grouped into source values (as exported by PGSharp, ``None`` means the export
    did not carry the field), derived values (recomputed from the active Game Data version)
    and inventory status. Rows are never deleted by an import.
    """

    __tablename__ = "pokemon"
    __table_args__ = (
        UniqueConstraint("trainer_account_id", "source_pokemon_id", name="uq_pokemon_identity"),
        Index("ix_pokemon_account_status", "trainer_account_id", "inventory_status"),
        Index("ix_pokemon_account_species", "trainer_account_id", "species_id"),
        Index("ix_pokemon_account_cp", "trainer_account_id", "cp"),
        Index("ix_pokemon_account_iv", "trainer_account_id", "iv_percent"),
        Index("ix_pokemon_account_caught", "trainer_account_id", "caught_at"),
        Index("ix_pokemon_account_family", "trainer_account_id", "family_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_account_id: Mapped[int] = mapped_column(ForeignKey("trainer_accounts.id", ondelete="CASCADE"))
    # PGSharp's unsigned 64-bit id as a decimal string (values exceed 2^63, ADR-0012).
    source_pokemon_id: Mapped[str] = mapped_column(String(24))

    # --- source values ---------------------------------------------------------------------
    species_id: Mapped[int] = mapped_column(Integer)
    form_id: Mapped[int | None] = mapped_column(Integer)
    form_name: Mapped[str | None] = mapped_column(String(80))
    costume_id: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[int | None] = mapped_column(Integer)
    shiny: Mapped[bool | None] = mapped_column(Boolean)
    alignment: Mapped[int | None] = mapped_column(Integer)
    lucky: Mapped[bool | None] = mapped_column(Boolean)
    favorite: Mapped[bool | None] = mapped_column(Boolean)
    cp: Mapped[int | None] = mapped_column(Integer)
    hp: Mapped[int | None] = mapped_column(Integer)
    max_hp: Mapped[int | None] = mapped_column(Integer)
    iv_attack: Mapped[int | None] = mapped_column(Integer)
    iv_defense: Mapped[int | None] = mapped_column(Integer)
    iv_stamina: Mapped[int | None] = mapped_column(Integer)
    cp_multiplier: Mapped[float | None] = mapped_column(Float)
    additional_cp_multiplier: Mapped[float | None] = mapped_column(Float)
    move_fast: Mapped[int | None] = mapped_column(Integer)
    move_charged_1: Mapped[int | None] = mapped_column(Integer)
    move_charged_2: Mapped[int | None] = mapped_column(Integer)
    num_upgrades: Mapped[int | None] = mapped_column(Integer)
    height_m: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    size_class: Mapped[int | None] = mapped_column(Integer)
    pokeball: Mapped[int | None] = mapped_column(Integer)
    caught_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    traded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    hatched_from_egg: Mapped[bool | None] = mapped_column(Boolean)
    in_gym: Mapped[bool | None] = mapped_column(Boolean)
    from_fort: Mapped[bool | None] = mapped_column(Boolean)
    origin_case: Mapped[int | None] = mapped_column(Integer)
    origin_events: Mapped[list[str]] = mapped_column(JSONText, default=list)
    location_card: Mapped[int | None] = mapped_column(Integer)
    bread_mode: Mapped[int | None] = mapped_column(Integer)
    bread_moves: Mapped[list[dict[str, int]]] = mapped_column(JSONText, default=list)
    has_mega_evolved: Mapped[bool | None] = mapped_column(Boolean)
    mega_evolved_forms: Mapped[list[int]] = mapped_column(JSONText, default=list)
    temp_evolution: Mapped[int | None] = mapped_column(Integer)
    nickname: Mapped[str | None] = mapped_column(String(64))
    buddy_km_walked: Mapped[float | None] = mapped_column(Float)
    buddy_candy_awarded: Mapped[int | None] = mapped_column(Integer)
    battles_attacked: Mapped[int | None] = mapped_column(Integer)
    battles_defended: Mapped[int | None] = mapped_column(Integer)
    purified_exclusive_move: Mapped[bool | None] = mapped_column(Boolean)
    limited_identifier: Mapped[str | None] = mapped_column(String(80))
    tag_ids: Mapped[list[str]] = mapped_column(JSONText, default=list)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONText, default=dict)

    # --- derived values (projection, see ADR-0015) -----------------------------------------
    iv_percent: Mapped[float | None] = mapped_column(Float)
    caught_year: Mapped[int | None] = mapped_column(Integer)
    level: Mapped[float | None] = mapped_column(Float)
    species_key: Mapped[str | None] = mapped_column(String(48))
    species_name: Mapped[str | None] = mapped_column(String(64))
    form_key: Mapped[str | None] = mapped_column(String(80))
    form_label: Mapped[str | None] = mapped_column(String(64))
    form_resolution: Mapped[str | None] = mapped_column(String(24))
    type_1: Mapped[str | None] = mapped_column(String(12))
    type_2: Mapped[str | None] = mapped_column(String(12))
    pokemon_class: Mapped[str | None] = mapped_column(String(16))
    family_id: Mapped[str | None] = mapped_column(String(48))
    move_fast_key: Mapped[str | None] = mapped_column(String(48))
    move_charged_1_key: Mapped[str | None] = mapped_column(String(48))
    move_charged_2_key: Mapped[str | None] = mapped_column(String(48))
    derived_version_id: Mapped[int | None] = mapped_column(Integer)

    # --- inventory status ------------------------------------------------------------------
    inventory_status: Mapped[str] = mapped_column(String(20), default="in_inventory")
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_changed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    first_seen_sync_id: Mapped[int | None] = mapped_column(Integer)
    last_seen_sync_id: Mapped[int | None] = mapped_column(Integer)
    disappeared_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    disappeared_sync_id: Mapped[int | None] = mapped_column(Integer)


class PokemonChangeEvent(Base):
    """Immutable history entry. A trigger in the migration rejects UPDATE on this table."""

    __tablename__ = "pokemon_change_events"
    __table_args__ = (
        Index("ix_change_events_account_sync", "trainer_account_id", "sync_run_id"),
        Index("ix_change_events_pokemon", "pokemon_id", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_account_id: Mapped[int] = mapped_column(ForeignKey("trainer_accounts.id", ondelete="CASCADE"))
    pokemon_id: Mapped[int] = mapped_column(ForeignKey("pokemon.id", ondelete="CASCADE"))
    sync_run_id: Mapped[int] = mapped_column(ForeignKey("sync_runs.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(16))
    changes: Mapped[dict[str, Any]] = mapped_column(JSONText)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)


class PokemonUserMetadata(Base):
    """OAK-owned data about a Pokémon. No import ever writes to this table."""

    __tablename__ = "pokemon_user_metadata"

    pokemon_id: Mapped[int] = mapped_column(ForeignKey("pokemon.id", ondelete="CASCADE"), primary_key=True)
    trainer_account_id: Mapped[int] = mapped_column(ForeignKey("trainer_accounts.id", ondelete="CASCADE"), index=True)
    protected: Mapped[bool] = mapped_column(Boolean, default=False)
    protection_reason: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSONText, default=list)
    planned_action: Mapped[str | None] = mapped_column(String(24))
    planned_league: Mapped[str | None] = mapped_column(String(16))
    priority: Mapped[int | None] = mapped_column(Integer)
    review_status: Mapped[str] = mapped_column(String(16), default="none")
    override_status: Mapped[str | None] = mapped_column(String(24))
    last_reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class PlannedAction(Base):
    __tablename__ = "planned_actions"
    __table_args__ = (
        UniqueConstraint("pokemon_id", "list_name", name="uq_planned_actions_pokemon_list"),
        Index("ix_planned_actions_account_list", "trainer_account_id", "list_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_account_id: Mapped[int] = mapped_column(ForeignKey("trainer_accounts.id", ondelete="CASCADE"))
    pokemon_id: Mapped[int] = mapped_column(ForeignKey("pokemon.id", ondelete="CASCADE"))
    list_name: Mapped[str] = mapped_column(String(32), default="cleanup")
    action: Mapped[str] = mapped_column(String(24))
    note: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="open")
    # Protections the user confirmed for this Pokémon, such as "favorite" (transfer_guard.py).
    confirmed: Mapped[list[str]] = mapped_column(JSONText, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
