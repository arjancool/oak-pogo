"""Analysis projections: PvP rankings per Pokémon, cleanup recommendations, battle teams."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONText, UTCDateTime


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (Index("ix_analysis_runs_account", "trainer_account_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_account_id: Mapped[int] = mapped_column(ForeignKey("trainer_accounts.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16))  # running | done | failed
    engine_version: Mapped[str] = mapped_column(String(16))
    game_data_version_id: Mapped[int | None] = mapped_column(Integer)
    rules_hash: Mapped[str] = mapped_column(String(64))
    rules: Mapped[dict[str, Any]] = mapped_column(JSONText)
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    error: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONText)


class PokemonAnalysis(Base):
    """Per-Pokémon result of the latest analysis run (spec entity CleanupRecommendation)."""

    __tablename__ = "cleanup_recommendations"
    __table_args__ = (Index("ix_cleanup_account_status", "trainer_account_id", "status"),)

    pokemon_id: Mapped[int] = mapped_column(ForeignKey("pokemon.id", ondelete="CASCADE"), primary_key=True)
    trainer_account_id: Mapped[int] = mapped_column(ForeignKey("trainer_accounts.id", ondelete="CASCADE"))
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(24))
    priority: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[str] = mapped_column(String(8))
    protection_reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONText, default=list)
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONText, default=list)
    roles: Mapped[list[dict[str, Any]]] = mapped_column(JSONText, default=list)
    alternatives: Mapped[list[dict[str, Any]]] = mapped_column(JSONText, default=list)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONText, default=list)
    group_key: Mapped[str | None] = mapped_column(String(80))
    great_rank: Mapped[int | None] = mapped_column(Integer)
    great_percent: Mapped[float | None] = mapped_column(Float)
    ultra_rank: Mapped[int | None] = mapped_column(Integer)
    ultra_percent: Mapped[float | None] = mapped_column(Float)
    master_percent: Mapped[float | None] = mapped_column(Float)
    # Battle score and keep score, both 0–100 (ADR-0019). None when the battle value cannot be
    # determined, for example without Game Data.
    battle_score: Mapped[int | None] = mapped_column(Integer)
    keep_score: Mapped[int | None] = mapped_column(Integer)
    # Every part of both scores, so the interface can show how they were built.
    scores: Mapped[dict[str, Any]] = mapped_column(JSONText, default=dict)
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime)


class PvpRanking(Base):
    __tablename__ = "pvp_rankings"
    __table_args__ = (Index("ix_pvp_rankings_account_league", "trainer_account_id", "league"),)

    pokemon_id: Mapped[int] = mapped_column(ForeignKey("pokemon.id", ondelete="CASCADE"), primary_key=True)
    league: Mapped[str] = mapped_column(String(16), primary_key=True)
    target_form_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    trainer_account_id: Mapped[int] = mapped_column(ForeignKey("trainer_accounts.id", ondelete="CASCADE"))
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"))
    target_name: Mapped[str] = mapped_column(String(80))
    is_evolution: Mapped[bool] = mapped_column(Boolean)
    rank: Mapped[int] = mapped_column(Integer)
    stat_product: Mapped[float] = mapped_column(Float)
    percent_of_best: Mapped[float] = mapped_column(Float)
    best_cp: Mapped[int] = mapped_column(Integer)
    best_level: Mapped[float] = mapped_column(Float)
    readiness: Mapped[str] = mapped_column(String(16))
    stardust_cost: Mapped[int | None] = mapped_column(Integer)
    candy_cost: Mapped[int | None] = mapped_column(Integer)
    xl_candy_cost: Mapped[int | None] = mapped_column(Integer)
    species_rank: Mapped[int | None] = mapped_column(Integer)
    species_score: Mapped[float | None] = mapped_column(Float)


class BattleTeam(Base):
    __tablename__ = "battle_teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_account_id: Mapped[int] = mapped_column(ForeignKey("trainer_accounts.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))  # pvp | raid | max | rocket
    league: Mapped[str | None] = mapped_column(String(16))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class BattleTeamMember(Base):
    __tablename__ = "battle_team_members"

    team_id: Mapped[int] = mapped_column(ForeignKey("battle_teams.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    pokemon_id: Mapped[int] = mapped_column(ForeignKey("pokemon.id", ondelete="CASCADE"))
    role: Mapped[str | None] = mapped_column(String(16))
