"""Cleanup Manager (spec §11, §20.5). Advice only: nothing here changes the game."""

from __future__ import annotations

import csv
import html
import io
from collections import defaultdict
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth, get_container, get_session, owned_account
from app.api.v1.pokemon import sync_bounds, tag_label_map
from app.core.container import Container
from app.core.errors import NotFoundError
from app.domain.pokemon import FIRST_GAME_YEAR, VINTAGE_FIRST_YEAR, VINTAGE_LAST_YEAR
from app.jobs.tasks import enqueue
from app.models import (
    AnalysisRun,
    BackgroundJob,
    PlannedAction,
    Pokemon,
    PokemonAnalysis,
    PokemonUserMetadata,
    TrainerAccount,
)
from app.recommendations.rules import ENGINE_VERSION, CleanupRules
from app.services.analysis import RULES_KEY, AnalysisService, rules_for
from app.services.pokemon_view import summarize
from app.services.transfer_guard import GuardContext, check_transfer, confirmation_item, guard_context

router = APIRouter(prefix="/cleanup", tags=["cleanup"])
STATUSES = ("PROTECT", "KEEP", "BUILD", "REVIEW", "TRANSFER_CANDIDATE", "UNKNOWN")
CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _latest_run(session: Session, account_id: int) -> AnalysisRun | None:
    return session.scalars(
        select(AnalysisRun)
        .where(AnalysisRun.trainer_account_id == account_id, AnalysisRun.status == "done")
        .order_by(AnalysisRun.id.desc())
        .limit(1)
    ).first()


def _run_info(session: Session, container: Container, account_id: int) -> dict[str, Any]:
    run = _latest_run(session, account_id)
    account = session.get(TrainerAccount, account_id)
    assert account is not None
    service = AnalysisService(container.settings, container.db, container.gamedata, container.clock)
    current = service.input_fingerprint(session, account, rules_for(account))
    pending = (
        session.scalar(
            select(func.count())
            .select_from(BackgroundJob)
            .where(
                BackgroundJob.trainer_account_id == account_id,
                BackgroundJob.kind == "analysis",
                BackgroundJob.status.in_(("queued", "running")),
            )
        )
        or 0
    )
    return {
        "run_id": run.id if run else None,
        "computed_at": run.finished_at.isoformat() if run and run.finished_at else None,
        "engine_version": run.engine_version if run else ENGINE_VERSION,
        "game_data_version": run.game_data_version_id if run else None,
        "rules_hash": run.rules_hash if run else None,
        "stale": run is None or run.input_fingerprint != current,
        "pending": pending > 0,
        "counts": (run.summary or {}).get("counts", {}) if run else {},
    }


@router.get("/recommendations", response_model=dict[str, Any])
def recommendations(
    account_id: int,
    status: str | None = Query(default=None, description="Komma-gescheiden statussen; leeg is alles"),
    favorite: bool | None = None,
    vintage: bool | None = None,
    unknown_date: bool | None = None,
    sort: str = Query(default="priority", pattern="^(priority|cp|-cp|name|iv|battle|-battle|keep|-keep)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    account = owned_account(session, auth.user, account_id)
    statuses = [s for s in (status or "").split(",") if s in STATUSES]
    stmt = (
        select(Pokemon, PokemonUserMetadata, PokemonAnalysis)
        .join(PokemonAnalysis, PokemonAnalysis.pokemon_id == Pokemon.id)
        .outerjoin(PokemonUserMetadata, PokemonUserMetadata.pokemon_id == Pokemon.id)
        .where(Pokemon.trainer_account_id == account.id, Pokemon.inventory_status == "in_inventory")
    )
    if statuses:
        stmt = stmt.where(PokemonAnalysis.status.in_(statuses))
    if favorite is not None:
        stmt = stmt.where(Pokemon.favorite.is_(True) if favorite else Pokemon.favorite.is_not(True))
    is_vintage = and_(Pokemon.caught_year >= VINTAGE_FIRST_YEAR, Pokemon.caught_year <= VINTAGE_LAST_YEAR)
    if vintage is not None:
        stmt = stmt.where(is_vintage if vintage else not_(is_vintage))
    date_unknown = or_(Pokemon.caught_year.is_(None), Pokemon.caught_year < FIRST_GAME_YEAR)
    if unknown_date is not None:
        stmt = stmt.where(date_unknown if unknown_date else not_(date_unknown))
    order = {
        "priority": [PokemonAnalysis.priority.desc(), Pokemon.cp.desc()],
        "cp": [Pokemon.cp.asc()],
        "-cp": [Pokemon.cp.desc()],
        "name": [Pokemon.species_name.asc(), Pokemon.cp.desc()],
        "iv": [Pokemon.iv_percent.asc()],
        "battle": [PokemonAnalysis.battle_score.asc()],
        "-battle": [PokemonAnalysis.battle_score.desc()],
        "keep": [PokemonAnalysis.keep_score.asc()],
        "-keep": [PokemonAnalysis.keep_score.desc()],
    }[sort]
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.execute(stmt.order_by(*order, Pokemon.id).offset((page - 1) * page_size).limit(page_size)).all()
    gd = container.gamedata.active()
    latest, first = sync_bounds(session, account.id)
    labels = tag_label_map(session, account.id)
    listed = set(
        session.scalars(
            select(PlannedAction.pokemon_id).where(
                PlannedAction.trainer_account_id == account.id, PlannedAction.list_name == "cleanup"
            )
        )
    )
    items = []
    for pokemon, meta, analysis in rows:
        summary = summarize(
            pokemon,
            meta,
            analysis,
            gd,
            tag_labels=labels,
            latest_sync_id=latest,
            first_sync_id=first,
        )
        items.append(
            {
                "pokemon": summary.model_dump(mode="json"),
                "status": analysis.status,
                "priority": analysis.priority,
                "confidence": analysis.confidence,
                "battle_score": analysis.battle_score,
                "keep_score": analysis.keep_score,
                "scores": analysis.scores or {},
                "protection_reasons": analysis.protection_reasons,
                "reasons": analysis.reasons,
                "roles": analysis.roles,
                "alternatives": analysis.alternatives,
                "warnings": analysis.warnings,
                "group_key": analysis.group_key,
                "in_action_list": pokemon.id in listed,
            }
        )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
        "analysis": _run_info(session, container, account.id),
    }


@router.get("/duplicates", response_model=dict[str, Any])
def duplicates(
    account_id: int,
    min_size: int = Query(2, ge=2, le=50),
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Groups of the same species, form and Shadow status, compared side by side (spec §11.4)."""
    account = owned_account(session, auth.user, account_id)
    rows = session.execute(
        select(Pokemon, PokemonUserMetadata, PokemonAnalysis)
        .outerjoin(PokemonUserMetadata, PokemonUserMetadata.pokemon_id == Pokemon.id)
        .outerjoin(PokemonAnalysis, PokemonAnalysis.pokemon_id == Pokemon.id)
        .where(Pokemon.trainer_account_id == account.id, Pokemon.inventory_status == "in_inventory")
    ).all()
    gd = container.gamedata.active()
    groups: dict[str, list[Any]] = defaultdict(list)
    for pokemon, meta, analysis in rows:
        key = f"{pokemon.form_key or pokemon.species_id}|{'shadow' if pokemon.alignment == 1 else 'regular'}"
        groups[key].append((pokemon, meta, analysis))
    result = []
    for key, members in groups.items():
        if len(members) < min_size:
            continue
        members.sort(
            key=lambda m: (
                -(m[2].battle_score if m[2] and m[2].battle_score is not None else -1),
                -(m[0].iv_percent or 0),
                -(m[0].cp or 0),
            )
        )
        first = members[0][0]
        name = first.species_name or f"#{first.species_id}"
        result.append(
            {
                "group_key": key,
                "name": f"{name} ({first.form_label})" if first.form_label else name,
                "shadow": key.endswith("|shadow"),
                "family_id": first.family_id,
                "count": len(members),
                "statuses": {s: sum(1 for m in members if m[2] and m[2].status == s) for s in STATUSES},
                "members": [
                    {
                        **summarize(p, m, a, gd).model_dump(mode="json"),
                        "recommendation": {
                            "status": a.status,
                            "reasons": a.reasons[:3],
                            "roles": a.roles,
                            "battle_score": a.battle_score,
                            "keep_score": a.keep_score,
                        }
                        if a
                        else None,
                    }
                    for p, m, a in members
                ],
            }
        )
    result.sort(key=lambda g: (-g["statuses"].get("TRANSFER_CANDIDATE", 0), -g["count"], g["name"]))
    return {"groups": result, "total_groups": len(result)}


@router.post("/analyze", response_model=dict[str, Any], status_code=202)
def analyze(
    account_id: int,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    account = owned_account(session, auth.user, account_id)
    session.commit()
    enqueue(container, "analysis", account.id)
    return {"queued": True}


@router.get("/rules", response_model=dict[str, Any])
def get_rules(
    account_id: int, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)
) -> dict[str, Any]:
    account = owned_account(session, auth.user, account_id)
    return _rules_out(rules_for(account))


def _rules_out(rules: CleanupRules) -> dict[str, Any]:
    return {
        "rules": rules.to_dict(),
        "defaults": CleanupRules().to_dict(),
        "engine_version": ENGINE_VERSION,
        "fixed": [
            {
                "code": "VINTAGE",
                "text": f"Vintage Pokémon ({VINTAGE_FIRST_YEAR}–{VINTAGE_LAST_YEAR}) zijn altijd beschermd. "
                "Ze worden wel volledig geanalyseerd en vergeleken.",
            },
            {
                "code": "UNKNOWN_DATE",
                "text": "Een Pokémon zonder bruikbare vangstdatum wordt nooit als nieuw behandeld: "
                "hooguit 'Beoordelen'.",
            },
            {
                "code": "FAVORITE",
                "text": "Favorieten krijgen extra bewaarpunten en worden nooit direct als transfer voorgesteld.",
            },
        ],
    }


class RulesIn(BaseModel):
    rules: dict[str, Any]


@router.put("/rules", response_model=dict[str, Any])
def put_rules(
    account_id: int,
    body: RulesIn,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    account = owned_account(session, auth.user, account_id)
    rules = CleanupRules.from_dict({**rules_for(account).to_dict(), **body.rules})
    account.settings = {**(account.settings or {}), RULES_KEY: rules.to_dict()}
    session.commit()
    enqueue(container, "analysis", account.id)
    return _rules_out(rules)


class ActionListRequest(BaseModel):
    account_id: int
    ids: list[int] = Field(default_factory=list, max_length=2000)
    mode: str = Field(default="add", pattern="^(add|remove|replace|clear|done)$")
    list_name: str = Field(default="cleanup", max_length=32)
    # Pokémon the user confirmed one by one: favorites, unknown catch dates, rule protection and
    # vintage Pokémon whose protection was lifted. See app/services/transfer_guard.py.
    confirmed_ids: list[int] = Field(default_factory=list, max_length=2000)


@router.post("/action-list", response_model=dict[str, Any])
def update_action_list(
    body: ActionListRequest,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Maintain the list of Pokémon the user intends to transfer by hand in the game."""
    account = owned_account(session, auth.user, body.account_id)
    now = container.clock.now()
    current = {
        a.pokemon_id: a
        for a in session.scalars(
            select(PlannedAction).where(
                PlannedAction.trainer_account_id == account.id,
                PlannedAction.list_name == body.list_name,
            )
        )
    }
    rows = (
        session.execute(
            select(Pokemon, PokemonUserMetadata, PokemonAnalysis)
            .outerjoin(PokemonUserMetadata, PokemonUserMetadata.pokemon_id == Pokemon.id)
            .outerjoin(PokemonAnalysis, PokemonAnalysis.pokemon_id == Pokemon.id)
            .where(Pokemon.trainer_account_id == account.id, Pokemon.id.in_(body.ids))
        ).all()
        if body.ids
        else []
    )
    found = {p.id: (p, m, a) for p, m, a in rows}
    confirmed = set(body.confirmed_ids)
    guard = guard_context(session, account, container.settings.tz)
    skipped: list[dict[str, Any]] = []
    needs_confirmation: list[dict[str, Any]] = []
    if body.mode in ("replace", "clear"):
        for action in current.values():
            session.delete(action)
        current = {}
    if body.mode in ("add", "replace"):
        for pid in body.ids:
            if pid not in found:
                continue
            pokemon, metadata, _analysis = found[pid]
            check = check_transfer(pokemon, metadata, guard)
            if check.blocked:
                skipped.append({"pokemon_id": pid, "reason": check.blocked})
                continue
            if check.needs and pid not in confirmed:
                needs_confirmation.append(confirmation_item(pokemon, check))
                continue
            if pid in current:
                # Confirming again records the protections that apply now.
                current[pid].confirmed = check.confirmation
                current[pid].updated_at = now
            else:
                session.add(
                    PlannedAction(
                        trainer_account_id=account.id,
                        pokemon_id=pid,
                        list_name=body.list_name,
                        action="transfer",
                        status="open",
                        confirmed=check.confirmation,
                        created_at=now,
                        updated_at=now,
                    )
                )
    if body.mode == "remove":
        for pid in body.ids:
            if pid in current:
                session.delete(current[pid])
    if body.mode == "done":
        for pid in body.ids:
            if pid not in current:
                continue
            if pid in found:
                pokemon, metadata, _analysis = found[pid]
                check = check_transfer(pokemon, metadata, guard)
                if check.blocked or check.unconfirmed(current[pid].confirmed):
                    skipped.append({"pokemon_id": pid, "reason": check.blocked or "; ".join(check.messages)})
                    continue
            current[pid].status = "done"
            current[pid].updated_at = now
    session.commit()
    return {
        **_action_list(session, container, account.id, body.list_name),
        "skipped": skipped,
        "needs_confirmation": needs_confirmation,
    }


def _action_list(
    session: Session, container: Container, account_id: int, list_name: str, sort: str = "cp"
) -> dict[str, Any]:
    rows = session.execute(
        select(PlannedAction, Pokemon, PokemonUserMetadata, PokemonAnalysis)
        .join(Pokemon, Pokemon.id == PlannedAction.pokemon_id)
        .outerjoin(PokemonUserMetadata, PokemonUserMetadata.pokemon_id == Pokemon.id)
        .outerjoin(PokemonAnalysis, PokemonAnalysis.pokemon_id == Pokemon.id)
        .where(PlannedAction.trainer_account_id == account_id, PlannedAction.list_name == list_name)
        .order_by(Pokemon.cp.desc() if sort == "-cp" else Pokemon.cp.asc(), Pokemon.id)
    ).all()
    gd = container.gamedata.active()
    guard = _guard_for(session, account_id, container.settings.tz)
    items = []
    for action, pokemon, meta, analysis in rows:
        summary = summarize(pokemon, meta, analysis, gd)
        reasons = [r["text"] for r in (analysis.reasons if analysis else [])]
        protection = [r["text"] for r in (analysis.protection_reasons if analysis else [])]
        # The protection is checked again on every read: what was fine when the Pokémon was
        # added may be protected now (audit A03).
        check = check_transfer(pokemon, meta, guard)
        unconfirmed = check.unconfirmed(action.confirmed)
        still_in_inventory = pokemon.inventory_status == "in_inventory"
        items.append(
            {
                "pokemon": summary.model_dump(mode="json"),
                "action": action.action,
                "status": action.status,
                "reason": "; ".join(reasons[:3]) or None,
                "protection": protection,
                "still_in_inventory": still_in_inventory,
                "blocked": check.blocked,
                "needs_confirmation": confirmation_item(pokemon, check, action.confirmed)
                if unconfirmed and not check.blocked
                else None,
                "executable": action.status == "open"
                and still_in_inventory
                and check.blocked is None
                and not unconfirmed,
            }
        )
    return {
        "list_name": list_name,
        "count": len(items),
        "items": items,
        "search_hint": search_hint(items),
    }


def _guard_for(session: Session, account_id: int, tz: ZoneInfo) -> GuardContext:
    account = session.get(TrainerAccount, account_id)
    if account is None:  # callers resolve the account through owned_account first
        raise NotFoundError("Onbekend traineraccount.")
    return guard_context(session, account, tz)


def search_hint(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Pokémon GO search strings that narrow the in-game box down to the listed species and CP.

    The game cannot search for OAK's or PGSharp's internal IDs. The string uses the Pokédex
    number and an exact CP per Pokémon, which is precise enough to find each one by hand.
    """
    open_items = [i for i in items if i["executable"]]
    by_species: dict[int, list[int]] = defaultdict(list)
    for item in open_items:
        if item["pokemon"]["cp"] is not None:
            by_species[item["pokemon"]["species_id"]].append(item["pokemon"]["cp"])
    queries = [
        {"species_id": dex, "query": f"{dex}&" + ",".join(f"cp{cp}" for cp in sorted(set(cps)))}
        for dex, cps in sorted(by_species.items())
    ]
    return {
        "note": "Pokémon GO kan niet op Pokémon-ID zoeken. Gebruik per soort het Pokédex-nummer met de exacte CP, "
        "en controleer de Pokémon in het spel voordat je hem overzet. '&!favorite&!shiny&!lucky' sluit "
        "extra veilig uit.",
        "safety_suffix": "&!favorite&!shiny&!lucky&!4*&!legendary&!mythical&!shadow&!costume",
        "queries": queries,
    }


@router.get("/action-list", response_model=dict[str, Any])
def get_action_list(
    account_id: int,
    list_name: str = "cleanup",
    sort: str = Query(default="cp", pattern="^(cp|-cp)$"),
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    account = owned_account(session, auth.user, account_id)
    return _action_list(session, container, account.id, list_name, sort)


def _held_back_reason(item: dict[str, Any]) -> str:
    if item["blocked"]:
        return str(item["blocked"])
    if item["needs_confirmation"]:
        return "Opnieuw bevestigen: " + str(item["needs_confirmation"]["message"])
    if not item["still_in_inventory"]:
        return "Niet meer in inventaris"
    return ""


def _csv_safe(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(CSV_INJECTION_PREFIXES):
        return "'" + value
    return value


@router.get("/export")
def export_action_list(
    account_id: int,
    list_name: str = "cleanup",
    output: str = Query(default="csv", pattern="^(csv|html)$", alias="format"),
    sort: str = Query(default="cp", pattern="^(cp|-cp)$"),
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> Any:
    account = owned_account(session, auth.user, account_id)
    data = _action_list(session, container, account.id, list_name, sort)
    if output == "html":
        rows = "".join(
            "<tr><td>☐</td><td>{}</td><td>{}</td><td>{}</td><td>{}/{}/{}</td><td>{}</td><td>{}</td><td><code>{}</code></td></tr>".format(
                html.escape(str(i["pokemon"]["species_name"] or "")),
                html.escape(str(i["pokemon"]["form_label"] or "")),
                i["pokemon"]["cp"],
                i["pokemon"]["iv_attack"],
                i["pokemon"]["iv_defense"],
                i["pokemon"]["iv_stamina"],
                html.escape(str(i["reason"] or "")),
                html.escape(", ".join(i["protection"]) or "—"),
                html.escape(i["pokemon"]["source_pokemon_id"]),
            )
            for i in data["items"]
            if i["executable"]
        )
        held_back = sum(1 for i in data["items"] if i["status"] == "open" and not i["executable"])
        note = (
            f"<p><strong>{held_back} Pokémon van de lijst staan hier niet op</strong>, omdat ze beschermd zijn, "
            "opnieuw bevestigd moeten worden of niet meer in je inventaris staan. Bekijk ze in OAK.</p>"
            if held_back
            else ""
        )
        page = (
            "<!doctype html><html lang='nl'><head><meta charset='utf-8'><title>OAK cleanup-checklist</title>"
            "<style>body{font-family:system-ui,sans-serif;margin:24px}table{border-collapse:collapse;width:100%}"
            "td,th{border:1px solid #999;padding:4px 6px;font-size:12px;text-align:left}code{font-size:10px}</style>"
            "</head><body><h1>Cleanup-checklist</h1><p>Gesorteerd op CP. OAK voert zelf niets uit: controleer iedere "
            f"Pokémon in het spel voordat je hem overzet.</p>{note}"
            "<table><thead><tr><th></th><th>Pokémon</th><th>Vorm</th>"
            "<th>CP</th><th>IV</th><th>Reden</th><th>Bescherming</th><th>Bron-ID</th></tr></thead><tbody>"
            f"{rows}</tbody></table></body></html>"
        )
        return HTMLResponse(page)
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        [
            "pokemon",
            "vorm",
            "cp",
            "atk",
            "def",
            "sta",
            "iv_pct",
            "reden",
            "bescherming",
            "bron_pokemon_id",
            "status",
            "uitvoerbaar",
            "geblokkeerd",
        ]
    )
    for item in data["items"]:
        p = item["pokemon"]
        writer.writerow(
            [
                _csv_safe(v)
                for v in (
                    p["species_name"],
                    p["form_label"],
                    p["cp"],
                    p["iv_attack"],
                    p["iv_defense"],
                    p["iv_stamina"],
                    p["iv_percent"],
                    item["reason"],
                    ", ".join(item["protection"]),
                    p["source_pokemon_id"],
                    item["status"],
                    "ja" if item["executable"] else "nee",
                    _held_back_reason(item),
                )
            ]
        )
    return StreamingResponse(
        iter(["﻿" + buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="oak-cleanup.csv"'},
    )
