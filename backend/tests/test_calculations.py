"""Known reference values for the calculation engine (spec §24.3).

References: base stats and CP multipliers from the Game Master subset; expected totals are the
well-known published power-up totals (1→40: 270,000 Stardust and 304 Candy; 40→50: 250,000
Stardust and 296 XL Candy) and the Level 50 hundo CP of Gyarados (3834).
"""

from __future__ import annotations

from typing import Any

import pytest

from app.analysis.evolution import evolution_paths
from app.analysis.league import Subject, analyze_leagues
from app.analysis.moves import Availability, availability, moveset_needs
from app.analysis.powerup import power_up_cost, reachable_max_level
from app.analysis.pvp import build_rank_table
from app.analysis.stats import BaseStats, IVs, combat_power, hit_points
from app.analysis.stats import base_stats_of as _base_stats_of
from app.domain.pokemon import iv_percent


def base_stats_of(form: Any) -> BaseStats:
    stats = _base_stats_of(form)
    assert stats is not None
    return stats


def _levels(gd: Any, maximum: float = 50.0) -> list[tuple[float, float]]:
    return [(lv, gd.cpm(lv)) for lv in gd.levels(1.0, maximum)]


def test_iv_percent() -> None:
    assert iv_percent(15, 15, 15) == 100.0
    assert iv_percent(0, 0, 0) == 0.0
    assert iv_percent(10, 13, 0) == 51.1
    assert iv_percent(None, 1, 1) is None


def test_cp_and_hp(gamedata: Any) -> None:
    gyarados = base_stats_of(dict(gamedata.forms["130:GYARADOSNORMAL"]))
    assert gyarados == BaseStats(237, 186, 216)
    assert combat_power(gyarados, IVs(15, 15, 15), gamedata.cpm(50.0)) == 3834
    assert combat_power(gyarados, IVs(15, 15, 15), gamedata.cpm(40.0)) == 3391
    assert hit_points(gyarados, IVs(15, 15, 15), gamedata.cpm(40.0)) == 182
    magikarp = base_stats_of(dict(gamedata.forms["129:MAGIKARPNORMAL"]))
    assert combat_power(magikarp, IVs(0, 0, 0), gamedata.cpm(1.0)) == 10  # floor at 10


def test_sample_export_cp_is_consistent(gamedata: Any, export: dict[str, Any]) -> None:
    from app.normalizers.pgsharp import normalize_export

    for pokemon in normalize_export(export).pokemon:
        form = gamedata.resolve_form(pokemon.species_id, pokemon.form_name).form
        cp = combat_power(
            base_stats_of(dict(form)),
            IVs(pokemon.iv_attack, pokemon.iv_defense, pokemon.iv_stamina),  # type: ignore[arg-type]
            pokemon.total_cp_multiplier,  # type: ignore[arg-type]
        )
        assert cp == pokemon.cp


def test_level_from_cpm(gamedata: Any) -> None:
    assert gamedata.level_for_cpm(0.094) == 1.0
    assert gamedata.level_for_cpm(gamedata.cpm(20.5)) == 20.5
    assert gamedata.level_for_cpm(gamedata.cpm(40.0) + 0.00005) == 40.0
    assert gamedata.level_for_cpm(0.5) is None
    assert gamedata.level_for_cpm(None) is None


def test_great_league_rank_medicham(gamedata: Any) -> None:
    table = build_rank_table(base_stats_of(dict(gamedata.forms["308:MEDICHAMNORMAL"])), 1500, _levels(gamedata))
    top = table.top(3)
    assert [ivs for ivs, _ in top[:2]] == [(5, 15, 14), (5, 15, 15)]
    assert top[0][1].rank == top[1][1].rank == 1  # equal stat product shares rank 1
    assert top[2][1].rank == 3
    assert all(entry.cp <= 1500 for _, entry in top)


def test_great_league_rank_azumarill(gamedata: Any) -> None:
    table = build_rank_table(base_stats_of(dict(gamedata.forms["184:AZUMARILLNORMAL"])), 1500, _levels(gamedata))
    best = table.lookup(0, 15, 15)
    assert best is not None and best.rank == 1 and best.level == 45.5 and best.cp == 1499
    worst = table.lookup(15, 15, 15)
    assert worst is not None and worst.rank > 2000


def test_ultra_league_rank_registeel(gamedata: Any) -> None:
    table = build_rank_table(base_stats_of(dict(gamedata.forms["379:REGISTEELNORMAL"])), 2500, _levels(gamedata))
    entry = table.lookup(15, 15, 15)
    assert entry is not None and entry.cp <= 2500
    assert table.eligible_count == 4096


def test_rank_table_matches_brute_force(gamedata: Any) -> None:
    levels = _levels(gamedata)
    for key in ("1:BULBASAURNORMAL", "130:GYARADOSNORMAL", "308:MEDICHAMNORMAL", "150:"):
        base = base_stats_of(dict(gamedata.forms[key]))
        table = build_rank_table(base, 1500, levels)
        for ivs in ((0, 0, 0), (15, 15, 15), (4, 15, 13), (1, 14, 15)):
            expected = None
            for level, cpm in levels:
                if combat_power(base, IVs(*ivs), cpm) <= 1500:
                    expected = (level, combat_power(base, IVs(*ivs), cpm))
            entry = table.lookup(*ivs)
            assert (entry.level, entry.cp) == expected if entry else expected is None


def test_iv_floor(gamedata: Any) -> None:
    table = build_rank_table(
        base_stats_of(dict(gamedata.forms["184:AZUMARILLNORMAL"])),
        1500,
        _levels(gamedata),
        iv_floor=12,
    )
    assert table.eligible_count == 64
    assert table.lookup(0, 15, 15) is None


def _cost(*args: Any, **kwargs: Any) -> Any:
    cost = power_up_cost(*args, **kwargs)
    assert cost is not None
    return cost


def test_power_up_costs(gamedata: Any) -> None:
    mechanics = gamedata.mechanics
    to_40 = power_up_cost(mechanics, 1.0, 40.0)
    assert to_40 is not None
    assert (to_40.stardust, to_40.candy, to_40.xl_candy, to_40.power_ups) == (270_000, 304, 0, 78)
    to_50 = power_up_cost(mechanics, 40.0, 50.0)
    assert to_50 is not None
    assert (to_50.stardust, to_50.candy, to_50.xl_candy) == (250_000, 0, 296)
    assert _cost(mechanics, 1.0, 40.0, shadow=True).stardust == 324_000
    assert _cost(mechanics, 1.0, 40.0, purified=True).stardust == 243_000
    assert _cost(mechanics, 1.0, 40.0, lucky=True).stardust == 135_000
    assert _cost(mechanics, 20.0, 20.0).power_ups == 0
    assert reachable_max_level(mechanics, 47, best_buddy=False) == 50.0
    assert reachable_max_level(mechanics, 47, best_buddy=True) == 51.0
    assert reachable_max_level(mechanics, 30, best_buddy=False) == 40.0


def test_evolution_cp(gamedata: Any) -> None:
    paths = evolution_paths(gamedata.forms, "129:MAGIKARPNORMAL")
    assert [p.target_key for p in paths] == ["130:GYARADOSNORMAL"]
    assert paths[0].total_candy == 400
    gyarados = base_stats_of(dict(gamedata.forms["130:GYARADOSNORMAL"]))
    assert (
        combat_power(gyarados, IVs(0, 15, 15), gamedata.cpm(15.0))
        < 1500
        < combat_power(gyarados, IVs(0, 15, 15), gamedata.cpm(20.0))
    )
    eevee = {p.target_key for p in evolution_paths(gamedata.forms, "133:EEVEENORMAL")}
    assert {"134:VAPOREONNORMAL", "196:ESPEONNORMAL", "700:SYLVEONNORMAL"} <= eevee
    espeon = next(p for p in evolution_paths(gamedata.forms, "133:EEVEENORMAL") if p.target_key == "196:ESPEONNORMAL")
    assert "only_day" in espeon.steps[0].conditions and "must_be_buddy" in espeon.steps[0].conditions


def test_move_availability(gamedata: Any) -> None:
    gyarados = gamedata.forms["130:GYARADOSNORMAL"]
    assert availability(gyarados, "HYDRO_PUMP") is Availability.NORMAL_TM
    assert availability(gyarados, "DRAGON_TAIL_FAST") is Availability.ELITE_TM
    assert availability(gyarados, "FRUSTRATION") is Availability.SPECIAL
    assert availability(gyarados, "PSYSTRIKE") is Availability.NOT_LEARNABLE
    needs = moveset_needs(
        gyarados,
        "BITE_FAST",
        ["CRUNCH"],
        ["DRAGON_TAIL_FAST", "AQUA_TAIL", "CRUNCH"],
        second_move_unlocked=False,
    )
    actions = [n.action for n in needs]
    assert actions == ["elite_fast_tm", "unlock", "elite_charged_tm", "none"]


def test_league_analysis_magikarp_targets_gyarados(gamedata: Any) -> None:
    subject = Subject("129:MAGIKARPNORMAL", IVs(0, 15, 15), 15.0, 250, False, False, False, 47)
    result = analyze_leagues(
        gamedata,
        subject,
        max_level=50.0,
        include_best_buddy=False,
        ready_cp_fraction=0.95,
        elite_tm_available=False,
    )
    great = {t.target_key: t for t in result["great"]}
    assert great["130:GYARADOSNORMAL"].is_evolution
    assert great["130:GYARADOSNORMAL"].readiness == "evolution"
    assert great["130:GYARADOSNORMAL"].evolution_candy == 400
    assert great["130:GYARADOSNORMAL"].cost is not None


def test_readiness_categories(gamedata: Any) -> None:
    def run(level: float, cp: int, key: str = "308:MEDICHAMNORMAL") -> str:
        subject = Subject(key, IVs(5, 15, 15), level, cp, False, False, False, 50)
        targets = analyze_leagues(
            gamedata,
            subject,
            max_level=50.0,
            include_best_buddy=False,
            ready_cp_fraction=0.95,
            elite_tm_available=False,
        )["great"]
        return next(t for t in targets if t.target_key == key).readiness

    assert run(50.0, 1499) == "direct"
    assert run(20.0, 600) == "power_up"
    big = Subject("130:GYARADOSNORMAL", IVs(15, 15, 15), 40.0, 3391, False, False, False, 50)
    targets = analyze_leagues(
        gamedata,
        big,
        max_level=50.0,
        include_best_buddy=False,
        ready_cp_fraction=0.95,
        elite_tm_available=False,
    )["great"]
    assert targets[0].readiness == "not_suitable"


@pytest.mark.parametrize("elite", [False, True])
def test_moveset_advice_respects_elite_setting(gamedata: Any, elite: bool) -> None:
    from app.analysis.league import recommended_moveset

    advice = recommended_moveset(
        gamedata,
        gamedata.forms["130:GYARADOSNORMAL"],
        "ultra",
        shadow=False,
        elite_tm_available=elite,
    )
    if advice is None:
        pytest.skip("geen ranking in subset")
    if not elite:
        assert (
            all(
                availability(gamedata.forms["130:GYARADOSNORMAL"], m) is not Availability.ELITE_TM
                for m in advice.moveset
            )
            or advice.source == "pvpoke_ranking"
        )
