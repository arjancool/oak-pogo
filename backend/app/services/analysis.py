"""Recomputing PvP rankings and cleanup recommendations for one trainer account.

Inputs are read in one short transaction, the computation runs without holding a lock, and
the results replace the previous projection in one ``BEGIN IMMEDIATE`` transaction.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, insert, select

from app.analysis.gym import gym_potential
from app.analysis.league import LeagueTarget, Subject, analyze_leagues
from app.analysis.raid import raid_potential
from app.analysis.stats import IVs
from app.core.clock import Clock
from app.core.config import Settings
from app.core.db import Database
from app.domain.pokemon import Alignment, BreadMode, extreme_size
from app.gamedata.store import GameDataStore
from app.models import (
    AnalysisRun,
    ImportJob,
    Pokemon,
    PokemonAnalysis,
    PokemonUserMetadata,
    PvpRanking,
    SyncRun,
    TagLabel,
    TrainerAccount,
)
from app.recommendations.cleanup import CollectionContext, evaluate
from app.recommendations.model import PokemonView
from app.recommendations.rules import ENGINE_VERSION, CleanupRules
from app.services.events import event_infos, event_key

log = logging.getLogger("oak.analysis")
RULES_KEY = "cleanup_rules"


def rules_for(account: TrainerAccount) -> CleanupRules:
    return CleanupRules.from_dict((account.settings or {}).get(RULES_KEY))


@dataclass(frozen=True, slots=True)
class AnalysisOutcome:
    run_id: int
    counts: dict[str, int]


class AnalysisService:
    def __init__(self, settings: Settings, db: Database, gamedata: GameDataStore, clock: Clock) -> None:
        self.settings = settings
        self.db = db
        self.gamedata = gamedata
        self.clock = clock

    def input_fingerprint(self, session: Any, account: TrainerAccount, rules: CleanupRules) -> str:
        last_sync = session.scalar(select(func.max(SyncRun.id)).where(SyncRun.trainer_account_id == account.id))
        last_meta = session.scalar(
            select(func.max(PokemonUserMetadata.updated_at)).where(PokemonUserMetadata.trainer_account_id == account.id)
        )
        tags = session.scalar(
            select(func.count())
            .select_from(TagLabel)
            .where(TagLabel.trainer_account_id == account.id, TagLabel.protects)
        )
        gd = self.gamedata.active()
        events = event_key(event_infos(session, account, gd), self.clock.now(), rules)
        payload = json.dumps(
            [
                last_sync,
                str(last_meta),
                tags,
                rules.digest,
                gd.version_id if gd else None,
                ENGINE_VERSION,
                account.trainer_level,
                events,
            ]
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def run(self, account_id: int) -> AnalysisOutcome | None:
        started = self.clock.now()
        gd = self.gamedata.active()
        with self.db.read() as session:
            account = session.get(TrainerAccount, account_id)
            if account is None:
                return None
            rules = rules_for(account)
            fingerprint = self.input_fingerprint(session, account, rules)
            trainer_level = account.trainer_level
            rows = session.execute(
                select(Pokemon, PokemonUserMetadata)
                .outerjoin(PokemonUserMetadata, PokemonUserMetadata.pokemon_id == Pokemon.id)
                .where(
                    Pokemon.trainer_account_id == account_id,
                    Pokemon.inventory_status == "in_inventory",
                )
                .order_by(Pokemon.id)
            ).all()
            protecting = {
                t.tag_id: t.label
                for t in session.scalars(
                    select(TagLabel).where(TagLabel.trainer_account_id == account_id, TagLabel.protects)
                )
            }
            last_job = session.scalars(
                select(ImportJob)
                .where(
                    ImportJob.trainer_account_id == account_id,
                    ImportJob.status.in_(("succeeded", "partial")),
                )
                .order_by(ImportJob.id.desc())
                .limit(1)
            ).first()
            last_partial = last_job is not None and last_job.status == "partial"
            events = event_infos(session, account, gd)
            snapshot = [(p, m) for p, m in rows]
            for p, m in snapshot:
                session.expunge(p)
                if m is not None:
                    session.expunge(m)
        # Registered in a short write transaction of its own. A read snapshot cannot become a
        # write once another connection committed after it started (audit F06 of 25 October).
        # The fingerprint describes what was read, so a change in between makes the run stale.
        with self.db.transaction() as session:
            run = AnalysisRun(
                trainer_account_id=account_id,
                status="running",
                engine_version=ENGINE_VERSION,
                game_data_version_id=gd.version_id if gd else None,
                rules_hash=rules.digest,
                rules=rules.to_dict(),
                input_fingerprint=fingerprint,
                started_at=started,
            )
            session.add(run)
            session.flush()
            run_id = run.id

        views: list[PokemonView] = []
        # Cups are stored next to the leagues for the battle pages, but stay out of the cleanup
        # advice: a cup runs for a few weeks and should not decide what you keep (ADR-0027).
        cup_targets: dict[int, dict[str, list[LeagueTarget]]] = {}
        for pokemon, meta in snapshot:
            view = pokemon_view(pokemon, meta, protecting)
            if gd is not None:
                form = gd.forms.get(pokemon.form_key or "") or {}
                view.family = form.get("family") or (gd.species_record(pokemon.species_id) or {}).get("family")
            if gd is not None and pokemon.form_key and view.has_ivs:
                subject = Subject(
                    form_key=pokemon.form_key,
                    ivs=IVs(pokemon.iv_attack, pokemon.iv_defense, pokemon.iv_stamina),  # type: ignore[arg-type]
                    level=pokemon.level,
                    cp=pokemon.cp,
                    shadow=pokemon.alignment == Alignment.SHADOW,
                    purified=pokemon.alignment == Alignment.PURIFIED,
                    lucky=bool(pokemon.lucky),
                    trainer_level=trainer_level,
                )
                options = {
                    "max_level": rules.max_level,
                    "include_best_buddy": rules.include_best_buddy,
                    "ready_cp_fraction": rules.ready_cp_fraction,
                    "elite_tm_available": rules.elite_tm_available,
                }
                view.leagues = analyze_leagues(gd, subject, **options)
                if gd.cups:
                    cup_targets[pokemon.id] = analyze_leagues(gd, subject, **options, leagues=tuple(gd.cups))
                view.raid = raid_potential(
                    gd,
                    pokemon.form_key,
                    pokemon.iv_attack,  # type: ignore[arg-type]
                    level=rules.max_level,
                    shadow=view.shadow,
                    current_moves=view.moves,
                    elite_tm_available=rules.elite_tm_available,
                )
                view.gym = gym_potential(
                    gd,
                    pokemon.form_key,
                    pokemon.iv_defense,  # type: ignore[arg-type]
                    pokemon.iv_stamina,  # type: ignore[arg-type]
                    level=rules.max_level,
                    shadow=view.shadow,
                )
            views.append(view)
        recommendations = evaluate(
            views,
            rules,
            CollectionContext(
                has_game_data=gd is not None,
                last_import_partial=last_partial,
                events=events,
                now=started,
                timezone=self.settings.timezone,
            ),
        )

        finished = self.clock.now()
        counts: dict[str, int] = {}
        recommendation_rows: list[dict[str, Any]] = []
        ranking_rows: list[dict[str, Any]] = []
        for view, rec in zip(views, recommendations, strict=True):
            counts[rec.status.value] = counts.get(rec.status.value, 0) + 1
            great, ultra, master = (view.primary.get(lg) for lg in ("great", "ultra", "master"))
            recommendation_rows.append(
                {
                    "pokemon_id": view.id,
                    "trainer_account_id": account_id,
                    "analysis_run_id": run_id,
                    "status": rec.status.value,
                    "priority": rec.priority,
                    "confidence": rec.confidence.value,
                    "protection_reasons": rec.protection_reasons,
                    "reasons": rec.reasons,
                    "roles": rec.roles,
                    "alternatives": rec.alternatives,
                    "warnings": rec.warnings,
                    "group_key": view.group_key,
                    "great_rank": great.rank if great else None,
                    "great_percent": great.percent if great else None,
                    "ultra_rank": ultra.rank if ultra else None,
                    "ultra_percent": ultra.percent if ultra else None,
                    "master_percent": master.percent if master else None,
                    "battle_score": rec.battle_score,
                    "keep_score": rec.keep_score,
                    "scores": rec.scores,
                    "computed_at": finished,
                }
            )
            for league, targets in [*view.leagues.items(), *cup_targets.get(view.id, {}).items()]:
                for target in targets:
                    ranking_rows.append(_ranking_row(view.id, account_id, run_id, league, target))

        with self.db.immediate_transaction() as session:
            session.execute(delete(PvpRanking).where(PvpRanking.trainer_account_id == account_id))
            session.execute(delete(PokemonAnalysis).where(PokemonAnalysis.trainer_account_id == account_id))
            if recommendation_rows:
                session.execute(insert(PokemonAnalysis), recommendation_rows)
            if ranking_rows:
                session.execute(insert(PvpRanking), ranking_rows)
            run = session.get(AnalysisRun, run_id)
            if run is not None:
                run.status = "done"
                run.finished_at = finished
                run.summary = {
                    "counts": counts,
                    "pokemon": len(views),
                    "rankings": len(ranking_rows),
                }
        log.info(
            "analysis done",
            extra={
                "account_id": account_id,
                "run_id": run_id,
                "counts": counts,
                "seconds": round((finished - started).total_seconds(), 2),
            },
        )
        return AnalysisOutcome(run_id, counts)


def pokemon_view(pokemon: Pokemon, meta: PokemonUserMetadata | None, protecting: dict[str, str]) -> PokemonView:
    """The engine's view of one Pokémon, also used by the transfer guard."""
    shadow = pokemon.alignment == Alignment.SHADOW
    group = f"{pokemon.form_key or pokemon.species_id}|{'shadow' if shadow else 'regular'}"
    name = pokemon.species_name or f"#{pokemon.species_id}"
    return PokemonView(
        id=pokemon.id,
        name=f"{name} ({pokemon.form_label})" if pokemon.form_label else name,
        group_key=group,
        cp=pokemon.cp,
        level=pokemon.level,
        iv_attack=pokemon.iv_attack,
        iv_defense=pokemon.iv_defense,
        iv_stamina=pokemon.iv_stamina,
        iv_percent=pokemon.iv_percent,
        caught_year=pokemon.caught_year,
        species_class=pokemon.pokemon_class,
        favorite=bool(pokemon.favorite),
        shiny=bool(pokemon.shiny),
        lucky=bool(pokemon.lucky),
        shadow=shadow,
        purified=pokemon.alignment == Alignment.PURIFIED,
        costume=bool(pokemon.costume_id),
        location_card=pokemon.location_card is not None,
        dynamax=pokemon.bread_mode == BreadMode.DYNAMAX,
        gigantamax=pokemon.bread_mode == BreadMode.GIGANTAMAX,
        event=bool(pokemon.origin_events) or bool(pokemon.limited_identifier),
        size=extreme_size(pokemon.size_class),
        nicknamed=bool(pokemon.nickname),
        mega_progress=bool(pokemon.has_mega_evolved),
        traded=pokemon.traded_at is not None,
        in_gym=bool(pokemon.in_gym),
        form_resolution=pokemon.form_resolution,
        manual_protected=bool(meta and meta.protected),
        manual_reason=meta.protection_reason if meta else None,
        override_status=meta.override_status if meta else None,
        review_requested=bool(meta and meta.review_status == "to_review"),
        planned_action=meta.planned_action if meta else None,
        protecting_tags=[protecting[t] for t in pokemon.tag_ids if t in protecting],
        moves=[
            m for m in (pokemon.move_fast_key, pokemon.move_charged_1_key, pokemon.move_charged_2_key) if m is not None
        ],
    )


def _ranking_row(pokemon_id: int, account_id: int, run_id: int, league: str, target: LeagueTarget) -> dict[str, Any]:
    return {
        "pokemon_id": pokemon_id,
        "league": league,
        "target_form_key": target.target_key,
        "trainer_account_id": account_id,
        "analysis_run_id": run_id,
        "target_name": target.target_name,
        "is_evolution": target.is_evolution,
        "rank": target.rank,
        "stat_product": target.stat_product,
        "percent_of_best": target.percent,
        "best_cp": target.best_cp,
        "best_level": target.best_level,
        "readiness": target.readiness,
        "stardust_cost": target.cost.stardust if target.cost else None,
        "candy_cost": target.cost.candy if target.cost else None,
        "xl_candy_cost": target.cost.xl_candy if target.cost else None,
        "species_rank": target.species_rank,
        "species_score": target.species_score,
    }
