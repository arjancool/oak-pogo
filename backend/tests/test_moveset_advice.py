"""Moveset advice for one Pokémon: a move it already knows needs no TM, and the advice says when
it would overwrite a move a normal TM does not give back (elite, legacy or Purified)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update

from app.analysis.league import LeagueTarget, MovesetAdvice, Subject, analyze_leagues, recommended_moveset
from app.analysis.moves import Availability, LostMove, lost_moves
from app.analysis.purify import purify
from app.analysis.stats import IVs
from app.models import Pokemon
from app.recommendations.scores import MOVESET_PENALTY, moveset_factor
from tests.conftest import Api

VENUSAUR, IVYSAUR, CHARIZARD = "3:VENUSAURNORMAL", "2:IVYSAURNORMAL", "6:CHARIZARDNORMAL"
PVPOKE = ["VINE_WHIP_FAST", "FRENZY_PLANT", "SLUDGE"]


def test_a_known_elite_move_keeps_the_pvpoke_moveset(gamedata: Any) -> None:
    form = gamedata.forms[VENUSAUR]
    assert gamedata.ranking("great", form["pvpoke_id"], shadow=False)["moveset"] == PVPOKE
    without = recommended_moveset(gamedata, form, "great", shadow=False, elite_tm_available=False)
    assert without is not None and without.source == "pvpoke_usage_filtered"
    assert "FRENZY_PLANT" not in without.moveset and without.known_special == []
    knows = recommended_moveset(
        gamedata, form, "great", shadow=False, elite_tm_available=False, known=("VINE_WHIP_FAST", "FRENZY_PLANT")
    )
    assert knows == MovesetAdvice(PVPOKE, "pvpoke_ranking", ["FRENZY_PLANT"], [], ["FRENZY_PLANT"])
    # With an Elite TM the PvPoke moveset was in reach anyway, so the known move changes nothing.
    tm = recommended_moveset(gamedata, form, "great", shadow=False, elite_tm_available=True, known=("FRENZY_PLANT",))
    assert tm == MovesetAdvice(PVPOKE, "pvpoke_ranking", ["FRENZY_PLANT"], [], [])


def _targets(gamedata: Any, form_key: str, moves: tuple[str, ...]) -> list[LeagueTarget]:
    subject = Subject(form_key, IVs(10, 10, 10), 20.0, None, False, False, False, 40, moves)
    return analyze_leagues(
        gamedata,
        subject,
        max_level=50.0,
        include_best_buddy=False,
        ready_cp_fraction=0.95,
        elite_tm_available=False,
    )["great"]


def test_the_analysis_counts_the_moves_of_the_form_it_has_now(gamedata: Any) -> None:
    venusaur = next(t for t in _targets(gamedata, VENUSAUR, ("VINE_WHIP_FAST", "FRENZY_PLANT")) if not t.is_evolution)
    assert venusaur.moveset is not None and venusaur.moveset.moveset == PVPOKE
    # An evolution does not keep its moves, so the same move does not count for it.
    evolved = next(
        t for t in _targets(gamedata, IVYSAUR, ("VINE_WHIP_FAST", "FRENZY_PLANT")) if t.target_key == VENUSAUR
    )
    assert evolved.is_evolution and evolved.moveset is not None
    assert evolved.moveset.source == "pvpoke_usage_filtered" and evolved.moveset.known_special == []


def test_the_battle_score_note_stays_the_same(gamedata: Any) -> None:
    known = next(t for t in _targets(gamedata, VENUSAUR, ("FRENZY_PLANT",)) if not t.is_evolution)
    assert moveset_factor(known) == (1.0, {"code": "KNOWS_SPECIAL_MOVE", "text": "kent de speciale aanval al"})
    unknown = next(t for t in _targets(gamedata, VENUSAUR, ()) if not t.is_evolution)
    assert moveset_factor(unknown)[0] == MOVESET_PENALTY


def test_overwriting_a_move_no_normal_tm_gives_back(gamedata: Any) -> None:
    venusaur, charizard = gamedata.forms[VENUSAUR], gamedata.forms[CHARIZARD]
    normal = ["VINE_WHIP_FAST", "SLUDGE_BOMB", "SLUDGE"]
    # One charged move, the second still locked: both slots go to the advice.
    assert lost_moves(venusaur, "VINE_WHIP_FAST", ["FRENZY_PLANT"], normal) == [
        LostMove("FRENZY_PLANT", Availability.ELITE_TM)
    ]
    assert lost_moves(venusaur, "VINE_WHIP_FAST", ["FRENZY_PLANT"], PVPOKE) == [], "the advice keeps it"
    assert lost_moves(venusaur, "VINE_WHIP_FAST", ["FRENZY_PLANT", "SLUDGE"], ["VINE_WHIP_FAST", "SLUDGE"]) == [], (
        "a slot is left for it"
    )
    # Frustration is a move players want to lose; Return is not.
    assert lost_moves(venusaur, "VINE_WHIP_FAST", ["FRUSTRATION"], normal) == []
    assert lost_moves(venusaur, "VINE_WHIP_FAST", ["RETURN"], normal) == [LostMove("RETURN", Availability.SPECIAL)]
    # An elite fast move counts too.
    assert lost_moves(charizard, "EMBER_FAST", ["FIRE_BLAST"], ["FIRE_SPIN_FAST", "FIRE_BLAST"]) == [
        LostMove("EMBER_FAST", Availability.ELITE_TM)
    ]
    assert lost_moves(charizard, "EMBER_FAST", ["FIRE_BLAST"], []) == []


def _make(container: Any, pokemon_id: int, form_key: str, fast: str, charged: str) -> None:
    with container.db.transaction() as session:
        session.execute(
            update(Pokemon)
            .where(Pokemon.id == pokemon_id)
            .values(
                species_id=int(form_key.split(":", maxsplit=1)[0]),
                form_key=form_key,
                move_fast_key=fast,
                move_charged_1_key=charged,
                move_charged_2_key=None,
                move_charged_2=None,
            )
        )


def test_the_analysis_page_shows_both(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    owner.upload(account, export)
    container.runner.drain()
    with container.db.read() as session:
        ids = session.scalars(
            select(Pokemon.id)
            .where(
                Pokemon.trainer_account_id == account,
                Pokemon.iv_attack.is_not(None),
                Pokemon.level.is_not(None),
            )
            .limit(2)
        ).all()
    venusaur, charizard = ids
    _make(container, venusaur, VENUSAUR, "VINE_WHIP_FAST", "FRENZY_PLANT")
    _make(container, charizard, CHARIZARD, "FIRE_SPIN_FAST", "FLAMETHROWER")

    great = owner.get(f"/api/v1/pokemon/{venusaur}/analysis").json()["leagues"]["great"]
    moveset = next(t for t in great["targets"] if t["target_key"] == VENUSAUR)["moveset"]
    assert moveset["moveset"] == PVPOKE and moveset["known_special"] == ["FRENZY_PLANT"]
    assert moveset["loses"] == []

    great = owner.get(f"/api/v1/pokemon/{charizard}/analysis").json()["leagues"]["great"]
    moveset = next(t for t in great["targets"] if t["target_key"] == CHARIZARD)["moveset"]
    assert moveset["source"] == "pvpoke_usage_filtered" and "FLAMETHROWER" not in moveset["moveset"]
    assert moveset["loses"] == [{"key": "FLAMETHROWER", "name": "Flamethrower", "availability": "elite_tm"}]


def test_purifying_swaps_the_shadow_move(gamedata: Any) -> None:
    subject = Subject(VENUSAUR, IVs(10, 10, 10), 20.0, None, True, False, False, 40, ("VINE_WHIP_FAST", "FRUSTRATION"))
    result = purify(subject, gamedata.forms[VENUSAUR], gamedata.mechanics.get("purification"))
    assert not isinstance(result, str)
    assert result.subject.moves == ("VINE_WHIP_FAST", "RETURN")
