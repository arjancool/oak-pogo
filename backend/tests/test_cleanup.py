"""Cleanup engine rules (spec §24.4, ADR-0019)."""

from __future__ import annotations

from typing import Any

import pytest

from app.analysis.league import Subject, analyze_leagues
from app.analysis.raid import raid_potential
from app.analysis.stats import IVs
from app.core.errors import ValidationFailedError
from app.recommendations.cleanup import CollectionContext, PokemonView, Recommendation, Status, evaluate
from app.recommendations.rules import CleanupRules

CTX = CollectionContext(has_game_data=True, last_import_partial=False)
MEDICHAM = "308:MEDICHAMNORMAL"


def view(
    i: int,
    gd: Any = None,
    key: str = "129:MAGIKARPNORMAL",
    ivs: tuple[int, int, int] = (5, 5, 5),
    level: float = 20.0,
    cp: int = 200,
    with_raid: bool = False,
    **flags: Any,
) -> PokemonView:
    v = PokemonView(
        id=i,
        name="Magikarp" if key.startswith("129") else "Medicham",
        group_key=f"{key}|regular",
        cp=cp,
        level=level,
        iv_attack=ivs[0],
        iv_defense=ivs[1],
        iv_stamina=ivs[2],
        iv_percent=round(sum(ivs) / 45 * 100, 1),
        caught_year=flags.pop("caught_year", 2024),
        form_resolution="exact",
        **flags,
    )
    if gd is not None:
        v.leagues = analyze_leagues(
            gd,
            Subject(key, IVs(*ivs), level, cp, v.shadow, v.purified, v.lucky, 50),
            max_level=50.0,
            include_best_buddy=False,
            ready_cp_fraction=0.95,
            elite_tm_available=False,
        )
        # The test Game Data holds about fifty species, so every raid rank in it is far better
        # than in the real field. Raid potential is only added where a test asks for it.
        if with_raid:
            v.raid = raid_potential(
                gd, key, ivs[0], level=50.0, shadow=v.shadow, current_moves=v.moves, elite_tm_available=False
            )
    return v


def result_of(results: list[Recommendation], i: int) -> Recommendation:
    return next(r for r in results if r.pokemon_id == i)


def status_of(results: list[Recommendation], i: int) -> Status:
    return result_of(results, i).status


def codes(items: list[dict[str, Any]]) -> set[str]:
    return {item["code"] for item in items}


# --- vintage: hard protection, full analysis -----------------------------------------------------


@pytest.mark.parametrize("year", [2016, 2017, 2018, 2019])
def test_vintage_is_always_protected(year: int) -> None:
    rules = CleanupRules(keep_min_per_species=0)
    result = evaluate([view(1, ivs=(0, 0, 0), caught_year=year)], rules, CTX)[0]
    assert result.status is Status.PROTECT
    reason = result.protection_reasons[0]
    assert reason["code"] == "VINTAGE" and reason["data"]["year"] == year
    assert reason["text"].startswith("Vintage Pokémon (2016–2019)")
    assert result.keep_score is not None and result.keep_score < rules.review_threshold  # low score, still protected


def test_2020_is_not_vintage() -> None:
    result = evaluate([view(1, caught_year=2020)], CleanupRules(keep_min_per_species=0), CTX)[0]
    assert "VINTAGE" not in codes(result.protection_reasons)
    assert result.status is Status.TRANSFER_CANDIDATE


def test_vintage_is_fully_analysed_and_compared(gamedata: Any) -> None:
    old = view(1, gamedata, key=MEDICHAM, ivs=(15, 3, 2), level=30.0, cp=1100, caught_year=2017)
    newer = view(2, gamedata, key=MEDICHAM, ivs=(5, 15, 15), level=50.0, cp=1499, caught_year=2024)
    results = evaluate([old, newer], CleanupRules(), CTX)
    vintage = result_of(results, 1)
    assert vintage.status is Status.PROTECT
    assert vintage.battle_score is not None and vintage.scores["battle"]["parts"]  # analysed
    assert any(p["code"] == "GREAT" for p in vintage.scores["battle"]["parts"])
    comparison = next(r for r in vintage.reasons if r["code"] == "VINTAGE_COMPARISON")
    assert comparison["data"]["pokemon_id"] == 2 and "blijft beschermd" in comparison["text"]
    assert vintage.alternatives[0]["pokemon_id"] == 2 and vintage.alternatives[0]["better"] is True
    assert status_of(results, 2) in (Status.KEEP, Status.BUILD)


def test_vintage_can_hold_a_battle_role(gamedata: Any) -> None:
    old = view(1, gamedata, key=MEDICHAM, ivs=(5, 15, 15), level=50.0, cp=1499, caught_year=2016)
    newer = view(2, gamedata, key=MEDICHAM, ivs=(15, 3, 2), level=30.0, cp=1100, caught_year=2024)
    results = evaluate([old, newer], CleanupRules(), CTX)
    assert any(r["role"] == "best_great" for r in result_of(results, 1).roles)
    assert "VINTAGE_BEST" in codes(result_of(results, 1).reasons)
    assert status_of(results, 2) in (Status.TRANSFER_CANDIDATE, Status.REVIEW)


def test_vintage_override_keeps_a_warning() -> None:
    result = evaluate([view(1, caught_year=2018, override_status="TRANSFER_CANDIDATE")], CleanupRules(), CTX)[0]
    assert result.status is Status.TRANSFER_CANDIDATE
    assert result.warnings[0]["code"] == "VINTAGE_OVERRIDE"


@pytest.mark.parametrize("year", [None, 1970, 2015])
def test_unknown_catch_date_is_never_assumed_new(year: int | None) -> None:
    rules = CleanupRules(keep_min_per_species=0)
    result = evaluate([view(1, ivs=(0, 1, 0), caught_year=year)], rules, CTX)[0]
    assert result.status is Status.REVIEW
    assert result.reasons[0]["code"] == "UNKNOWN_DATE"
    assert "UNKNOWN_DATE" in codes(result.warnings)


# --- favorites: soft protection ------------------------------------------------------------------


def test_favorite_is_not_a_hard_protection() -> None:
    rules = CleanupRules(keep_min_per_species=0, keep_points_best_copy=0)
    result = evaluate([view(1, favorite=True)], rules, CTX)[0]
    assert result.status is not Status.PROTECT
    assert "FAVORITE" not in codes(result.protection_reasons)
    assert result.status is Status.REVIEW  # never a direct transfer candidate
    assert result.reasons[0]["code"] == "FAVORITE_REVIEW"


def test_favorite_with_a_better_copy_goes_to_review_with_explanation(gamedata: Any) -> None:
    best = view(1, gamedata, key=MEDICHAM, ivs=(5, 15, 15), level=50.0, cp=1499)
    favorite = view(2, gamedata, key=MEDICHAM, ivs=(15, 3, 2), level=30.0, cp=1100, favorite=True)
    results = evaluate([best, favorite], CleanupRules(), CTX)
    assert status_of(results, 1) in (Status.KEEP, Status.BUILD)
    fav = result_of(results, 2)
    assert fav.status is Status.REVIEW
    assert fav.warnings[0]["code"] == "FAVORITE"
    assert [r["code"] for r in fav.reasons][:2] == ["FAVORITE_REVIEW", "BETTER_DUPLICATE"]
    assert "FAVORITE" not in codes(fav.protection_reasons)
    better = fav.reasons[1]
    assert better["data"]["pokemon_id"] == 1
    assert "IV-rang" in better["text"] or "bruikbaarheid" in better["text"]


def test_best_favorite_is_kept() -> None:
    results = evaluate([view(1, ivs=(10, 10, 10), favorite=True), view(2, ivs=(1, 1, 1))], CleanupRules(), CTX)
    assert status_of(results, 1) is Status.KEEP
    assert status_of(results, 2) is Status.TRANSFER_CANDIDATE


def test_favorite_adds_keep_points_but_never_battle_points(gamedata: Any) -> None:
    plain = view(1, gamedata, key=MEDICHAM, ivs=(5, 15, 15), level=50.0, cp=1499)
    favorite = view(1, gamedata, key=MEDICHAM, ivs=(5, 15, 15), level=50.0, cp=1499, favorite=True)
    rules = CleanupRules()
    a = evaluate([plain], rules, CTX)[0]
    b = evaluate([favorite], rules, CTX)[0]
    assert a.battle_score == b.battle_score
    assert a.scores["battle"] == b.scores["battle"]
    assert b.keep_score is not None and a.keep_score is not None
    assert b.keep_score - a.keep_score == min(rules.keep_points_favorite, 100 - a.keep_score)
    assert "FAVORITE" in codes(b.scores["keep"]["parts"])


def test_favorite_weight_is_configurable() -> None:
    rules = CleanupRules(keep_points_favorite=0, keep_min_per_species=0)
    result = evaluate([view(1, favorite=True)], rules, CTX)[0]
    part = next(p for p in result.scores["keep"]["parts"] if p["code"] == "FAVORITE")
    assert part["value"] == 0


# --- scores ---------------------------------------------------------------------------------------


def test_scores_are_transparent_and_count_each_property_once(gamedata: Any) -> None:
    v = view(
        1,
        gamedata,
        key=MEDICHAM,
        ivs=(15, 15, 15),
        level=40.0,
        cp=1400,
        shiny=True,
        lucky=True,
        favorite=True,
        with_raid=True,
    )
    rules = CleanupRules(protect_hundo=False, protect_shiny=False, protect_lucky=False)
    result = evaluate([v], rules, CTX)[0]
    battle = result.scores["battle"]
    assert result.battle_score == round(max(p["value"] for p in battle["parts"]))  # highest, never a sum
    keep = result.scores["keep"]
    assert result.keep_score == min(100, round(sum(p["value"] for p in keep["parts"])))
    traits = next(p for p in keep["parts"] if p["code"] == "TRAITS")
    assert traits["data"]["traits"] == ["SHINY", "LUCKY"]  # a hundo counts only through the battle score
    assert traits["value"] <= rules.keep_traits_cap


def test_hard_protection_is_independent_of_the_score() -> None:
    rules = CleanupRules(keep_min_per_species=0)
    result = evaluate([view(1, shiny=True, ivs=(0, 0, 0))], rules, CTX)[0]
    assert result.status is Status.PROTECT
    assert result.keep_score is not None


def test_high_keep_score_keeps_and_low_score_transfers() -> None:
    rules = CleanupRules(keep_min_per_species=0, protect_nicknamed=False, keep_points_nickname=80)
    kept = evaluate([view(1, nicknamed=True)], rules, CTX)[0]
    assert kept.status is Status.KEEP and kept.reasons[0]["code"] == "HIGH_KEEP_SCORE"
    low = evaluate([view(2)], rules, CTX)[0]
    assert low.status is Status.TRANSFER_CANDIDATE
    assert "LOW_KEEP_SCORE" in codes(low.reasons)


def test_rules_ignore_removed_settings_and_validate() -> None:
    rules = CleanupRules.from_dict({"protect_favorites": True, "protect_before_year": 2030, "keep_points_favorite": 40})
    assert rules.keep_points_favorite == 40
    with pytest.raises(ValidationFailedError):
        CleanupRules.from_dict({"keep_threshold": 30, "review_threshold": 50})
    with pytest.raises(ValidationFailedError):
        CleanupRules.from_dict({"keep_points_shiny": 101})


def test_raid_potential_uses_evolutions(gamedata: Any) -> None:
    strong = raid_potential(
        gamedata, "129:MAGIKARPNORMAL", 15, level=40.0, shadow=False, current_moves=[], elite_tm_available=False
    )
    weak = raid_potential(
        gamedata, "129:MAGIKARPNORMAL", 0, level=40.0, shadow=False, current_moves=[], elite_tm_available=False
    )
    assert strong is not None and weak is not None
    assert strong.target_name == "Gyarados" and strong.is_evolution
    assert strong.rank >= 1 and strong.rank <= weak.rank
    assert strong.dps > weak.dps


# --- existing behaviour ---------------------------------------------------------------------------


def test_individual_protections() -> None:
    rules = CleanupRules()
    cases: list[dict[str, Any]] = [
        {"lucky": True},
        {"location_card": True},
        {"costume": True},
        {"species_class": "mythical"},
        {"shadow": True},
        {"dynamax": True},
        {"manual_protected": True},
        {"protecting_tags": ["Trade"]},
    ]
    for flags in cases:
        assert evaluate([view(1, **flags)], rules, CTX)[0].status is Status.PROTECT, flags
    assert evaluate([view(1, ivs=(15, 15, 15))], rules, CTX)[0].status is Status.PROTECT


def test_duplicates_keep_best_and_explain(gamedata: Any) -> None:
    views = [
        view(1, gamedata, ivs=(0, 15, 15)),
        view(2, gamedata, ivs=(15, 0, 3)),
        view(3, gamedata, ivs=(9, 2, 1)),
    ]
    results = evaluate(views, CleanupRules(), CTX)
    kept = [r for r in results if r.status in (Status.KEEP, Status.BUILD)]
    transfers = [r for r in results if r.status is Status.TRANSFER_CANDIDATE]
    assert kept and transfers, [r.status for r in results]
    for result in transfers:
        assert "NO_PROTECTION" in codes(result.reasons) and "BETTER_DUPLICATE" in codes(result.reasons)
        better_id = next(r for r in result.reasons if r["code"] == "BETTER_DUPLICATE")["data"]["pokemon_id"]
        assert status_of(results, better_id) in (Status.KEEP, Status.BUILD)
        assert result.alternatives and result.alternatives[0]["better"] is True


def test_good_pvp_candidate_not_thrown_away(gamedata: Any) -> None:
    rules = CleanupRules(keep_min_per_species=0)
    best = view(1, gamedata, key=MEDICHAM, ivs=(5, 15, 15), level=50.0, cp=1499)
    second = view(2, gamedata, key=MEDICHAM, ivs=(5, 15, 14), level=50.0, cp=1494)
    results = evaluate([best, second], rules, CTX)
    assert status_of(results, 1) is Status.KEEP
    assert status_of(results, 2) is Status.REVIEW  # also excellent IVs: review, never transfer


def test_no_transfer_on_partial_import() -> None:
    rules = CleanupRules(keep_min_per_species=0)
    context = CollectionContext(has_game_data=True, last_import_partial=True)
    result = evaluate([view(1)], rules, context)[0]
    assert result.status is Status.REVIEW
    assert "PARTIAL_IMPORT" in codes(result.reasons)


def test_unknown_without_data() -> None:
    no_gd = CollectionContext(has_game_data=False, last_import_partial=False)
    result = evaluate([view(1)], CleanupRules(), no_gd)[0]
    assert result.status is Status.UNKNOWN and result.battle_score is None
    missing = view(2)
    missing.iv_attack = None
    assert evaluate([missing], CleanupRules(), CTX)[0].status is Status.UNKNOWN


def test_minimum_per_species() -> None:
    results = evaluate([view(1, ivs=(1, 1, 1)), view(2, ivs=(10, 10, 10))], CleanupRules(), CTX)
    assert status_of(results, 2) is Status.KEEP
    assert result_of(results, 2).reasons[0]["code"] == "BEST_COPY"
    assert status_of(results, 1) is Status.TRANSFER_CANDIDATE


def test_override_and_review_request() -> None:
    rules = CleanupRules(keep_min_per_species=0)
    assert evaluate([view(1, override_status="KEEP")], rules, CTX)[0].status is Status.KEEP
    assert evaluate([view(1, review_requested=True)], rules, CTX)[0].status is Status.REVIEW


def test_deterministic() -> None:
    rules = CleanupRules()
    a = evaluate([view(i, ivs=(i % 16, 3, 4), favorite=i % 3 == 0) for i in range(10)], rules, CTX)
    b = evaluate([view(i, ivs=(i % 16, 3, 4), favorite=i % 3 == 0) for i in range(10)], rules, CTX)
    assert [(r.status, r.reasons, r.scores) for r in a] == [(r.status, r.reasons, r.scores) for r in b]


def test_favorite_in_doubt_still_shows_the_better_copy(gamedata: Any) -> None:
    best = view(1, gamedata, key=MEDICHAM, ivs=(5, 15, 15), level=50.0, cp=1499)
    favorite = view(2, gamedata, key=MEDICHAM, ivs=(15, 3, 2), level=30.0, cp=1100, favorite=True)
    rules = CleanupRules(keep_points_favorite=60)  # enough for a doubtful keep score
    fav = result_of(evaluate([best, favorite], rules, CTX), 2)
    assert fav.status is Status.REVIEW
    assert [r["code"] for r in fav.reasons][:2] == ["KEEP_SCORE_DOUBT", "BETTER_DUPLICATE"]
    assert fav.warnings[0]["code"] == "FAVORITE"
