"""The strongest team as the Pokémon are now.

The Team Builder picks it from every Pokémon that may play in the league as it is, scored on the
stat product on its current level. A collection always gets a team when three different Pokémon
fit, also in the Master League, where hardly anyone is at 95 percent of level 40."""

from __future__ import annotations

from typing import Any

from app.analysis.league import Subject, analyze_leagues
from app.analysis.stats import IVs, base_stats_of, stat_product
from app.services.battles import TEAM_POOL, league_candidates
from tests.conftest import Api

GYARADOS = "130:GYARADOSNORMAL"
MAGIKARP = 129
HUNDO = IVs(15, 15, 15)


def _targets(gamedata: Any, level: float, *, form: str = GYARADOS) -> dict[str, Any]:
    subject = Subject(form, HUNDO, level, 0, False, False, False, 50)
    return analyze_leagues(
        gamedata,
        subject,
        max_level=50.0,
        include_best_buddy=False,
        ready_cp_fraction=0.95,
        elite_tm_available=False,
    )


def _own(targets: list[Any], key: str = GYARADOS) -> Any:
    return next(t for t in targets if t.target_key == key)


def test_percent_now_is_the_stat_product_on_the_current_level(gamedata: Any) -> None:
    base = base_stats_of(dict(gamedata.forms[GYARADOS]))
    assert base is not None
    master = _own(_targets(gamedata, 34.0)["master"])
    best = stat_product(base, HUNDO, gamedata.cpm(50.0))
    assert master.percent_now == round(stat_product(base, HUNDO, gamedata.cpm(34.0)) / best * 100, 2)
    assert master.readiness == "power_up", "not ready, but it may play as it is"
    assert 0 < master.percent_now < master.percent == 100.0
    assert _own(_targets(gamedata, 50.0)["master"]).percent_now == 100.0


def test_percent_now_needs_a_pokemon_that_fits_now(gamedata: Any) -> None:
    targets = _targets(gamedata, 34.0)
    assert _own(targets["great"]).percent_now is None, "over the CP cap of the Great League"
    great = _own(_targets(gamedata, _own(targets["great"]).best_level)["great"])
    assert great.percent_now == great.percent, "on its best level it is as strong as it gets"
    magikarp = next(key for key, form in gamedata.forms.items() if form.get("dex") == MAGIKARP)
    for target in _targets(gamedata, 20.0, form=magikarp)["master"]:
        assert (target.percent_now is None) == target.is_evolution, "an evolution cannot play now"


def _imported(owner: Api, container: Any, export: dict[str, Any]) -> int:
    account = owner.account()
    owner.upload(account, export)
    container.runner.drain()
    return account


def _variants(owner: Api, account: int, league: str) -> dict[str, Any]:
    built = owner.post("/api/v1/battles/team-builder", {"account_id": account, "league": league})
    assert built.status_code == 200, built.text
    return {v["mode"]: v for v in built.json()["variants"]}


def test_the_master_league_has_a_team_as_the_pokemon_are_now(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    ready = owner.get("/api/v1/battles/league/master", account_id=account, readiness="direct").json()
    assert ready["total"] < 3, "the sample has too few Pokémon that are ready, like a real collection"
    variant = _variants(owner, account, "master")["now"]
    assert variant["label"]["code"] == "TEAM_NOW"
    team = variant["team"]
    assert team and len({m["pokemon_id"] for m in team}) == 3
    assert any(m["readiness"] != "direct" for m in team)
    for member in team:
        assert not member["is_evolution"]
        assert member["goal_level"] == member["level"] and member["goal_cp"] == member["cp"]
        assert member["stardust"] == 0 and member["candy"] == 0 and member["xl_candy"] == 0
        assert member["percent_now"] is not None
    assert variant["investment"]["stardust"] == 0


def test_the_team_now_picks_the_strongest_pokemon(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    page = owner.get("/api/v1/battles/league/master", account_id=account, sort="-now", limit=500).json()
    scores = [i["suitability_now"] for i in page["items"]]
    known = [s for s in scores if s is not None]
    assert known and known == sorted(known, reverse=True) and scores[: len(known)] == known
    for item in page["items"]:
        assert (item["percent_now"] is None) == (item["suitability_now"] is None)
    with container.db.read() as session:
        now = league_candidates(session, gamedata, account, "master", now=True)
        best = league_candidates(session, gamedata, account, "master")
    assert now and all(c.score == c.score_now and not c.ranking.is_evolution for c in now)
    assert [c.score for c in now] == sorted((c.score for c in now), reverse=True)
    assert any(c.score_now != c.score for c in best), "the other variants keep the score on the best level"
    # The team comes from the strongest Pokémon now, one per target species.
    pool: dict[str, int] = {}
    for candidate in now:
        pool.setdefault(candidate.ranking.target_form_key, candidate.pokemon.id)
    team = _variants(owner, account, "master")["now"]["team"]
    assert all(m["pokemon_id"] in list(pool.values())[:TEAM_POOL] for m in team)


def test_the_team_now_respects_the_cp_cap(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    account = _imported(owner, container, export)
    team = _variants(owner, account, "great")["now"]["team"]
    assert team and all(m["cp"] <= 1500 for m in team)


def test_too_few_pokemon_now_says_how_many(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    export["pokemons"] = [p for p in export["pokemons"] if p["pokemonId"] == MAGIKARP + 1]
    assert len(export["pokemons"]) == 2, "two Gyarados, one target species"
    account = _imported(owner, container, export)
    message = _variants(owner, account, "master")["now"]["message"]
    assert message["code"] == "TEAM_TOO_FEW" and message["data"] == {"found": 1, "needed": 3}
    assert message["text"] == "Te weinig geschikte Pokémon voor deze variant: 1 gevonden, 3 nodig."
