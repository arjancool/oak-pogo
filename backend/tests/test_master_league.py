"""The Master League has no CP cap, so the best level is the highest there is and the last levels
take XL Candy. Usable counts from the level without XL Candy, and limited upgrades stop there."""

from __future__ import annotations

from typing import Any

from app.analysis.league import Subject, analyze_leagues, ready_level
from app.analysis.powerup import Cost, power_up_cost
from app.analysis.stats import IVs, base_stats_of, combat_power
from app.models import Pokemon, PvpRanking
from app.services.battles import _ready_goal
from tests.conftest import Api

GYARADOS = "130:GYARADOSNORMAL"
HUNDO = IVs(15, 15, 15)


def _master(gamedata: Any, level: float) -> Any:
    subject = Subject(GYARADOS, HUNDO, level, 0, False, False, False, 50)
    targets = analyze_leagues(
        gamedata,
        subject,
        max_level=50.0,
        include_best_buddy=False,
        ready_cp_fraction=0.95,
        elite_tm_available=False,
    )["master"]
    return next(t for t in targets if t.target_key == GYARADOS)


def test_the_ready_level_comes_from_the_game_master(gamedata: Any) -> None:
    assert gamedata.mechanics["upgrade"]["xl_min_pokemon_level"] == 40
    assert ready_level(gamedata, None, 50.0) == 40.0
    assert ready_level(gamedata, None, 35.0) == 35.0, "never above the best level"
    assert ready_level(gamedata, 1500, 50.0) == 50.0, "a league with a cap keeps its best level"


def test_a_level_40_pokemon_is_ready_for_the_master_league(gamedata: Any) -> None:
    # A hundo Gyarados has CP 3391 at level 40 and 3834 at level 50, about 88 percent.
    at_40 = _master(gamedata, 40.0)
    assert at_40.cp_now == 3391 and at_40.best_cp == 3834 and at_40.best_level == 50.0
    assert at_40.readiness == "direct", "usable without XL Candy"
    assert at_40.cost is not None and at_40.cost.xl_candy > 0, "the best level still takes XL Candy"
    assert _master(gamedata, 30.0).readiness == "power_up"


def test_the_goal_without_xl_candy(gamedata: Any) -> None:
    ranking = PvpRanking(target_form_key=GYARADOS, best_level=50.0, best_cp=3834)
    pokemon = Pokemon(level=30.0, iv_attack=15, iv_defense=15, iv_stamina=15, alignment=0, lucky=False)
    goal = _ready_goal(gamedata, pokemon, ranking)
    assert goal is not None and goal.level == 40.0 and goal.cp == 3391
    assert goal.cost == power_up_cost(gamedata.mechanics, 30.0, 40.0)
    assert goal.cost is not None and goal.cost.xl_candy == 0
    # Already past level 40: the goal is where it is now, at no cost.
    pokemon.level = 45.0
    goal = _ready_goal(gamedata, pokemon, ranking)
    base = base_stats_of(dict(gamedata.forms[GYARADOS]))
    assert base is not None and goal is not None
    assert goal.level == 45.0 and goal.cp == combat_power(base, HUNDO, gamedata.cpm(45.0))
    assert goal.cost == Cost(0, 0, 0, 0)
    pokemon.iv_attack = None
    assert _ready_goal(gamedata, pokemon, ranking) is None, "unknown IVs give no goal"


def test_limited_upgrades_in_the_master_league_stop_at_level_40(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = owner.account()
    owner.upload(account, export)
    container.runner.drain()
    budget = 100_000
    built = owner.post(
        "/api/v1/battles/team-builder", {"account_id": account, "league": "master", "stardust_budget": budget}
    )
    assert built.status_code == 200, built.text
    variants = {v["mode"]: v for v in built.json()["variants"]}
    limited = variants["limited"]["team"]
    assert limited, "with level 40 as the goal the sample has a team within the budget"
    for member in limited:
        assert member["goal_level"] >= 40.0 and member["best_level"] == 50.0
        assert member["stardust"] is not None and member["stardust"] <= budget
        assert not member["xl_candy"], "no XL Candy within limited upgrades"
        assert member["goal_cp"] <= member["best_cp"]
    assert variants["limited"]["investment"]["stardust"] == sum(m["stardust"] for m in limited)
    # Too few Pokémon are ready now in the sample: the message says how many there are.
    message = variants["direct"]["message"]
    found = message["data"]["found"]
    assert message["code"] == "TEAM_TOO_FEW" and found < message["data"]["needed"] == 3
    assert message["text"] == f"Te weinig geschikte Pokémon voor deze variant: {found} gevonden, 3 nodig."
    future = variants["future"]["team"]
    assert future and all(m["goal_level"] == m["best_level"] and m["goal_cp"] == m["best_cp"] for m in future)
