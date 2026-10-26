"""Battle analyses (spec §12–§14, §20.6)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.analysis.league import league_cap
from app.api.deps import (
    AuthContext,
    get_auth,
    get_container,
    get_session,
    owned_account,
    owned_pokemon,
)
from app.core.container import Container
from app.core.errors import NotFoundError, ServiceUnavailableError, ValidationFailedError
from app.gamedata.model import GameData
from app.models import BattleTeam, BattleTeamMember, Pokemon, PvpRanking
from app.services.analysis import rules_for
from app.services.battles import (
    LEAGUE_SORTS,
    TEAM_METHOD,
    build_teams,
    league_candidates,
    max_battle_overview,
    raid_counters,
    rocket_counters,
    sort_candidates,
)
from app.services.gyms import gym_defenders

router = APIRouter(prefix="/battles", tags=["battles"])
MAX_OPPONENTS = 3
SEARCH_LIMIT = 30


def _gd(container: Container) -> GameData:
    gd = container.gamedata.active()
    if gd is None:
        raise ServiceUnavailableError(
            "Geen actieve Game Data. Werk de Game Data bij onder Beheer.", code="NO_GAME_DATA"
        )
    return gd


def _form_label(form: Any) -> str:
    return f"{form['name']} ({form['label']})" if form.get("label") else str(form["name"])


# A league (great) or a cup (fantasy-1500, ADR-0027).
LEAGUE_ID = r"^[a-z0-9]{1,40}(-[0-9]{1,6})?$"
LEAGUE_METHOD = (
    "Per Pokémon de meest competitieve soort die hij kan worden (PvPoke-rang), met zijn IV-rang voor die soort."
)
CUP_METHOD = " Alleen Pokémon die volgens de regels van de cup mee mogen, zoals PvPoke ze beschrijft."
UNRANKED_CUP_METHOD = (
    " PvPoke heeft voor deze cup geen ranglijst."
    " De volgorde volgt daarom alleen de IV-rang, niet hoe sterk een soort is."
)


def league_info(gd: GameData, league_id: str) -> dict[str, Any] | None:
    ranked = gd.rankings.get(league_id, {}).get("count")
    data = gd.leagues.get(league_id)
    if data is not None:
        return {
            "id": league_id,
            "kind": "league",
            "name": data["name"],
            "max_cp": league_cap(gd, league_id),
            "level_cap": None,
            "banned": data.get("banned", []),
            "ranked_species": ranked,
            "eligible_species": None,
            "rules": [],
            "conditions": [],
            "party_size": None,
            "link": None,
            "source": data.get("source"),
        }
    cup = gd.cups.get(league_id)
    if cup is None:
        return None
    return {
        "id": league_id,
        "kind": "cup",
        "name": cup["name"],
        "max_cp": league_cap(gd, league_id),
        "level_cap": cup.get("level_cap"),
        "banned": [],
        "ranked_species": ranked,
        "eligible_species": len(cup.get("eligible", [])),
        "rules": cup.get("rules", []),
        "conditions": cup.get("conditions", []),
        "party_size": cup.get("party_size"),
        "link": cup.get("link"),
        "source": "PvPoke",
    }


def _known_league(gd: GameData, league_id: str) -> dict[str, Any]:
    info = league_info(gd, league_id)
    if info is None:
        raise NotFoundError("Onbekende league of cup. Misschien staat hij niet meer in de Game Data.", context="league")
    return info


@router.get("/leagues", response_model=list[dict[str, Any]])
def leagues(
    auth: AuthContext = Depends(get_auth), container: Container = Depends(get_container)
) -> list[dict[str, Any]]:
    """The three leagues, then the cups PvPoke currently shows."""
    gd = _gd(container)
    cups = sorted(gd.cups, key=lambda cup_id: (gd.cups[cup_id]["name"].lower(), cup_id))
    return [info for league_id in (*gd.leagues, *cups) if (info := league_info(gd, league_id))]


@router.get("/league/{league}", response_model=dict[str, Any])
def league_overview(
    league: str,
    account_id: int,
    readiness: str | None = Query(default=None, description="direct, power_up, evolution"),
    limit: int = Query(100, ge=1, le=500),
    sort: str = Query("-suitability", description="Kolom, met '-' voor aflopend, bijvoorbeeld iv_rank of -percent"),
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    if sort.removeprefix("-") not in LEAGUE_SORTS:
        raise ValidationFailedError(f"Onbekende sortering '{sort}'.", code="UNKNOWN_SORT", data={"sort": sort})
    gd = _gd(container)
    info = _known_league(gd, league)
    account = owned_account(session, auth.user, account_id)
    wanted = tuple(r for r in (readiness or "").split(",") if r) or None
    candidates = sort_candidates(league_candidates(session, gd, account.id, league, readiness=wanted), sort)
    method = LEAGUE_METHOD
    if info["kind"] == "cup":
        method += CUP_METHOD + ("" if info["ranked_species"] else UNRANKED_CUP_METHOD)
    return {
        "league": league,
        "info": info,
        "sort": sort,
        "max_cp": league_cap(gd, league),
        "method": method,
        "items": [
            {
                "pokemon_id": c.pokemon.id,
                "species_id": c.pokemon.species_id,
                "shiny": c.pokemon.shiny,
                "types": [tp for tp in (c.pokemon.type_1, c.pokemon.type_2) if tp],
                "name": c.pokemon.species_name,
                "form_label": c.pokemon.form_label,
                "cp": c.pokemon.cp,
                "level": c.pokemon.level,
                "shadow": c.pokemon.alignment == 1,
                "ivs": [c.pokemon.iv_attack, c.pokemon.iv_defense, c.pokemon.iv_stamina],
                "target": c.ranking.target_name,
                "is_evolution": c.ranking.is_evolution,
                "iv_rank": c.ranking.rank,
                "percent": c.ranking.percent_of_best,
                "best_cp": c.ranking.best_cp,
                "best_level": c.ranking.best_level,
                "readiness": c.ranking.readiness,
                "species_rank": c.ranking.species_rank,
                "species_score": c.ranking.species_score,
                "cost": {
                    "stardust": c.ranking.stardust_cost,
                    "candy": c.ranking.candy_cost,
                    "xl_candy": c.ranking.xl_candy_cost,
                },
                "moveset_quality": c.moveset_quality,
                "recommended_moveset": [str((gd.move(m) or {}).get("name", m)) for m in c.recommended],
                "suitability": round(c.score, 1),
            }
            for c in candidates[:limit]
        ],
        "total": len(candidates),
    }


@router.get("/pokemon/{pokemon_id}", response_model=dict[str, Any])
def pokemon_battle(
    pokemon_id: int,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    pokemon = owned_pokemon(session, auth.user, pokemon_id)
    rankings = session.scalars(select(PvpRanking).where(PvpRanking.pokemon_id == pokemon.id)).all()
    return {
        "pokemon_id": pokemon.id,
        "rankings": [
            {
                "league": r.league,
                "target": r.target_name,
                "target_key": r.target_form_key,
                "is_evolution": r.is_evolution,
                "rank": r.rank,
                "percent": r.percent_of_best,
                "stat_product": r.stat_product,
                "best_cp": r.best_cp,
                "best_level": r.best_level,
                "readiness": r.readiness,
                "species_rank": r.species_rank,
                "species_score": r.species_score,
                "cost": {
                    "stardust": r.stardust_cost,
                    "candy": r.candy_cost,
                    "xl_candy": r.xl_candy_cost,
                },
            }
            for r in rankings
        ],
    }


class TeamBuilderRequest(BaseModel):
    account_id: int
    league: str = Field(pattern=LEAGUE_ID)
    stardust_budget: int | None = Field(default=100_000, ge=0, le=10_000_000)
    include: list[int] = Field(default_factory=list, max_length=3)


@router.post("/team-builder", response_model=dict[str, Any])
def team_builder(
    body: TeamBuilderRequest,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    gd = _gd(container)
    _known_league(gd, body.league)
    account = owned_account(session, auth.user, body.account_id)
    variants = build_teams(session, gd, account.id, body.league, budget=body.stardust_budget, include=body.include)
    return {
        "league": body.league,
        "method": TEAM_METHOD,
        "simulation": False,
        "variants": variants,
        "game_data_version": gd.version_id,
    }


class TeamIn(BaseModel):
    account_id: int
    name: str = Field(min_length=1, max_length=64)
    kind: str = Field(default="pvp", pattern="^(pvp|raid|max|rocket)$")
    league: str | None = Field(default=None, pattern=LEAGUE_ID)
    notes: str | None = Field(default=None, max_length=2000)
    members: list[dict[str, Any]] = Field(default_factory=list, max_length=6)


def _team_out(session: Session, team: BattleTeam) -> dict[str, Any]:
    members = session.execute(
        select(BattleTeamMember, Pokemon)
        .join(Pokemon, Pokemon.id == BattleTeamMember.pokemon_id)
        .where(BattleTeamMember.team_id == team.id)
        .order_by(BattleTeamMember.position)
    ).all()
    return {
        "id": team.id,
        "name": team.name,
        "kind": team.kind,
        "league": team.league,
        "notes": team.notes,
        "updated_at": team.updated_at.isoformat(),
        "members": [
            {
                "position": m.position,
                "role": m.role,
                "pokemon_id": p.id,
                "name": p.species_name,
                "cp": p.cp,
                "in_inventory": p.inventory_status == "in_inventory",
            }
            for m, p in members
        ],
    }


@router.get("/teams", response_model=list[dict[str, Any]])
def list_teams(
    account_id: int, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    account = owned_account(session, auth.user, account_id)
    teams = session.scalars(
        select(BattleTeam).where(BattleTeam.trainer_account_id == account.id).order_by(BattleTeam.id)
    ).all()
    return [_team_out(session, t) for t in teams]


@router.post("/teams", response_model=dict[str, Any], status_code=201)
def save_team(
    body: TeamIn,
    team_id: int | None = None,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    account = owned_account(session, auth.user, body.account_id)
    now = container.clock.now()
    ids = [int(m["pokemon_id"]) for m in body.members if "pokemon_id" in m]
    owned = set(
        session.scalars(select(Pokemon.id).where(Pokemon.trainer_account_id == account.id, Pokemon.id.in_(ids)))
    )
    if set(ids) - owned:
        raise ValidationFailedError("Een teamlid hoort niet bij dit account.", context="team_member")
    if team_id is not None:
        team = session.get(BattleTeam, team_id)
        if team is None or team.trainer_account_id != account.id:
            raise NotFoundError("Team niet gevonden.", context="team")
        team.name, team.kind, team.league, team.notes, team.updated_at = (
            body.name,
            body.kind,
            body.league,
            body.notes,
            now,
        )
        session.execute(delete(BattleTeamMember).where(BattleTeamMember.team_id == team.id))
    else:
        team = BattleTeam(
            trainer_account_id=account.id,
            name=body.name,
            kind=body.kind,
            league=body.league,
            notes=body.notes,
            created_at=now,
            updated_at=now,
        )
        session.add(team)
        session.flush()
    for position, member in enumerate(body.members):
        session.add(
            BattleTeamMember(
                team_id=team.id,
                position=position,
                pokemon_id=int(member["pokemon_id"]),
                role=member.get("role"),
            )
        )
    session.flush()
    return _team_out(session, team)


@router.delete("/teams/{team_id}", status_code=204)
def delete_team(
    team_id: int,
    account_id: int,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
) -> None:
    account = owned_account(session, auth.user, account_id)
    team = session.get(BattleTeam, team_id)
    if team is None or team.trainer_account_id != account.id:
        raise NotFoundError("Team niet gevonden.", context="team")
    session.delete(team)


@router.get("/species", response_model=list[dict[str, Any]])
def search_species(
    q: str = Query(min_length=1, max_length=40),
    auth: AuthContext = Depends(get_auth),
    container: Container = Depends(get_container),
) -> list[dict[str, Any]]:
    """Search forms by name, for choosing a raid boss or Rocket opponent."""
    gd = _gd(container)
    needle = q.strip().lower()
    results = []
    for key, form in gd.forms.items():
        name = _form_label(form)
        if needle in name.lower():
            results.append(
                {
                    "key": key,
                    "name": name,
                    "dex": form["dex"],
                    "types": form.get("types", []),
                    "class": form.get("class"),
                }
            )
        for mega in form.get("mega", []):
            mega_name = f"{form['name']} ({mega['id'].removeprefix('TEMP_EVOLUTION_').replace('_', ' ').title()})"
            if mega.get("stats") and needle in mega_name.lower():
                results.append(
                    {
                        "key": f"{key}|{mega['id']}",
                        "name": mega_name,
                        "dex": form["dex"],
                        "types": mega.get("types") or form.get("types", []),
                        "class": form.get("class"),
                    }
                )
    results.sort(key=lambda r: (r["dex"], r["key"]))
    unique: dict[str, dict[str, Any]] = {}
    for result in results:
        unique.setdefault(result["name"], result)
    return list(unique.values())[:SEARCH_LIMIT]


def _boss(gd: GameData, key: str) -> dict[str, Any]:
    form_key, _, mega_id = key.partition("|")
    form = gd.forms.get(form_key)
    if form is None:
        raise NotFoundError("Onbekende tegenstander.", context="opponent")
    if mega_id:
        mega = next((m for m in form.get("mega", []) if m["id"] == mega_id and m.get("stats")), None)
        if mega is None:
            raise NotFoundError("Onbekende mega-vorm.", context="mega_form")
        return {
            "name": f"{form['name']} ({mega_id.removeprefix('TEMP_EVOLUTION_').title()})",
            "types": mega.get("types") or form.get("types", []),
            "stats": mega["stats"],
        }
    return {"name": _form_label(form), "types": list(form.get("types", [])), "stats": form["stats"]}


class RaidRequest(BaseModel):
    account_id: int
    boss_key: str | None = Field(default=None, max_length=100)


@router.post("/raid-counters", response_model=dict[str, Any])
def raid(
    body: RaidRequest,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    gd = _gd(container)
    account = owned_account(session, auth.user, body.account_id)
    boss = _boss(gd, body.boss_key) if body.boss_key else None
    counters = raid_counters(session, gd, account.id, boss, boss["types"] if boss else [], rules_for(account))
    return {
        "boss": boss,
        "mode": "counters" if boss else "general",
        "method": "Vereenvoudigd PvE-model: cyclus-DPS met STAB, typevoordeel en Shadow-bonus. Geen weer, geen "
        "energie uit schade, geen aanvallen van de baas. Bedoeld om aanvallers te vergelijken.",
        "counters": counters,
        "game_data_version": gd.version_id,
    }


class RocketRequest(BaseModel):
    account_id: int
    opponent_keys: list[str] = Field(min_length=1, max_length=MAX_OPPONENTS)


@router.post("/rocket-counters", response_model=dict[str, Any])
def rocket(
    body: RocketRequest,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    gd = _gd(container)
    account = owned_account(session, auth.user, body.account_id)
    opponents = [_boss(gd, key) for key in body.opponent_keys]
    return {
        "lineup_source": None,
        "lineup_note": "OAK heeft geen gevalideerde, gedateerde bron voor actuele Team GO Rocket-opstellingen. Kies "
        "de tegenstanders zelf.",
        "method": "Heuristiek op typevoordeel, PvP-aanvalswaarden, eigen statistieken en weerstand. Geen simulatie.",
        "results": rocket_counters(session, gd, account.id, opponents),
    }


@router.get("/gym-defenders", response_model=dict[str, Any])
def gym(
    account_id: int,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    gd = _gd(container)
    account = owned_account(session, auth.user, account_id)
    return gym_defenders(session, gd, account.id)


class MaxRequest(BaseModel):
    account_id: int
    boss_key: str | None = Field(default=None, max_length=100)


@router.post("/max-counters", response_model=dict[str, Any])
def max_battles(
    body: MaxRequest,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    gd = _gd(container)
    account = owned_account(session, auth.user, body.account_id)
    boss = _boss(gd, body.boss_key) if body.boss_key else None
    overview = max_battle_overview(session, gd, account.id, boss["types"] if boss else [])
    return {
        "boss": boss,
        **overview,
        "method": "Aanvallers op typevoordeel van Max Attack, verdedigers op weerstand en Defense. Heuristiek.",
    }
