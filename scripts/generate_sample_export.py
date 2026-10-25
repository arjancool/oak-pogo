"""Generate a synthetic, anonymized PGSStats.json for tests and demos.

The structure (every key, nesting and value type) follows a real PGSharp export from
October 2026. All values are invented: trainer name, identifiers, locations and Pokémon are
generated from a fixed seed. CP and HP are computed from the Game Master subset, so the
sample is internally consistent.

Usage (from the repository root):
    backend/.venv/bin/python scripts/generate_sample_export.py
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.gamedata.model import GameData  # noqa: E402
from app.gamedata.transform import build_dataset  # noqa: E402

SEED = 20261023
OUT = ROOT / "fixtures" / "pgsharp" / "PGSStats.sample.json"
FIXTURES = ROOT / "fixtures" / "gamedata"
EXPORT_TIME = "2026-10-20 09:30:00 CEST"
BASE_TIME_MS = 1_760_000_000_000
DAY_MS = 86_400_000
# Species (dex, PGSharp formName) that appear in the sample, with how many copies.
ROSTER = [
    (1, "BulbasaurNormal", 3), (2, "IvysaurNormal", 1), (3, "VenusaurNormal", 1), (4, "CharmanderNormal", 2),
    (6, "CharizardNormal", 1), (7, "SquirtleNormal", 2), (19, "RattataAlola", 2), (19, "RattataNormal", 3),
    (25, "PikachuNormal", 3), (52, "MeowthGalarian", 2), (66, "MachopNormal", 3), (68, "MachampNormal", 1),
    (129, "MagikarpNormal", 6), (130, "GyaradosNormal", 2), (133, "EeveeNormal", 4), (134, "VaporeonNormal", 1),
    (147, "DratiniNormal", 2), (149, "DragoniteNormal", 1), (150, "MewtwoNormal", 1), (151, "MewNormal", 1),
    (183, "MarillNormal", 3), (184, "AzumarillNormal", 2), (194, "WooperNormal", 3), (195, "QuagsireNormal", 1),
    (302, "SableyeNormal", 2), (307, "MedititeNormal", 2), (308, "MedichamNormal", 2), (351, "CastformNormal", 1),
    (379, "RegisteelNormal", 1), (382, "KyogreNormal", 1), (793, "NihilegoNormal", 1), (831, "WoolooNormal", 3),
    (863, "PerrserkerNormal", 1), (888, "ZacianHero", 1), (4, "CharmanderFutureCostume2099", 1),
]
FORM_IDS = {name: 1000 + i for i, (_, name, _) in enumerate(ROSTER)}


def load_gamedata() -> GameData:
    pokeminers = json.loads((FIXTURES / "pokeminers-subset.json").read_text())
    pvpoke = json.loads((FIXTURES / "pvpoke-subset.json").read_text())
    rankings = {
        league: json.loads((FIXTURES / f"pvpoke-rankings-{league}-subset.json").read_text())
        for league in ("great", "ultra", "master")
    }
    return GameData(build_dataset(pokeminers, pvpoke=pvpoke, rankings=rankings, sources=[], generated_at="x"), 1)


def display(rng: random.Random, form_name: str, *, shiny: bool, alignment: int, costume: int,
            location_card: int | None, bread: int) -> dict[str, object]:
    return {
        "alignment": alignment,
        "breadModeEnum": bread,
        "costume": costume,
        "currentTempEvolution": 0,
        "displayId": rng.randint(-(2**63), 2**63 - 1),
        "form": FORM_IDS.get(form_name, 0),
        "formName": form_name,
        "gender": rng.choice([1, 2]),
        "isStrongPokemon": False,
        "locationCard": {"locationCard": location_card} if location_card else None,
        "lockedTempEvolution": 0,
        "megaEvolutionLevel": None,
        "originalCostume": 0,
        "pokemonBadge": 0,
        "shiny": shiny,
        "tempEvolutionIsLocked": False,
        "temporaryEvolutionFinishMs": 0,
        "weatherBoostedCondition": rng.choice([0, 0, 0, 1, 3, 4]),
    }


def pokemon_record(rng: random.Random, gd: GameData, dex: int, form_name: str, index: int,
                   special: dict[str, object]) -> dict[str, object]:
    resolution = gd.resolve_form(dex, form_name)
    form = resolution.form
    assert form is not None, (dex, form_name)
    stats = form["stats"]
    ivs = special.get("ivs") or (rng.randint(0, 15), rng.randint(0, 15), rng.randint(0, 15))
    level = special.get("level") or rng.choice([10.0, 15.0, 20.0, 20.5, 25.0, 28.0, 30.0, 35.0, 40.0])
    cpm = gd.cpm(float(level))
    assert cpm is not None
    atk, dfn, sta = (stats["atk"] + ivs[0], stats["def"] + ivs[1], stats["sta"] + ivs[2])
    cp = max(10, math.floor(atk * math.sqrt(dfn) * math.sqrt(sta) * cpm**2 / 10))
    hp = max(10, math.floor(sta * cpm))
    fast = form["fast_moves"][index % len(form["fast_moves"])]
    charged = form["charged_moves"][index % len(form["charged_moves"])]
    second = form["charged_moves"][(index + 1) % len(form["charged_moves"])] if special.get("second_move") else None
    caught_ms = BASE_TIME_MS - int(special.get("age_days", rng.randint(1, 2500))) * DAY_MS
    record: dict[str, object] = {
        "additionalCpMultiplier": 0.0,
        "battlesAttacked": rng.randint(0, 5),
        "battlesDefended": 0,
        "bonusStatLevel": None,
        "breadMoves": [{"moveLevel": 1, "moveType": 1}] if special.get("bread") else [],
        "buddyCandyAwarded": 0,
        "buddyKmWalked": 0.0,
        "capturedS2CellId": rng.randint(10**17, 10**18),
        "caughtInParty": False,
        "coinsReturned": 0,
        "cp": cp,
        "cpMultiplier": cpm,
        "cpMultiplierBeforeTrading": 0.0,
        "creationTimeMs": caught_ms,
        "deployedDurationMs": 0,
        "deployedFortId": "",
        "deployedGymLatDegree": 0.0,
        "deployedGymLngDegree": 0.0,
        "deployedReturnedTimestampMs": 0,
        "deployedStationExpirationTimeMs": 0,
        "deployedStationId": "",
        "displayCp": 0,
        "displayPokemonId": 0,
        "eggDistribution": None,
        "eggIncubatorId": "",
        "eggKmWalkedStart": 0.0,
        "eggKmWalkedTarget": 0.0,
        "eggSlotType": 0,
        "eggTelemetry": None,
        "eggType": 0,
        "evolutionQuestInfo": [],
        "favorite": bool(special.get("favorite", rng.random() < 0.3)),
        "fromFort": rng.random() < 0.2,
        "hasMegaEvolved": False,
        "hatchedFromEgg": rng.random() < 0.15,
        "heightM": round(rng.uniform(0.3, 6.0), 4),
        # Unsigned 64-bit IDs; about half exceed 2^63 like in real exports.
        "id": rng.randint(2**53 + 1, 2**64 - 1),
        "inEscrow": False,
        "individualAttack": ivs[0],
        "individualDefense": ivs[1],
        "individualStamina": ivs[2],
        "irisSocialDeployment": None,
        "isActivelyTraining": False,
        "isBad": False,
        "isComponent": False,
        "isEgg": False,
        "isFusion": False,
        "isLucky": bool(special.get("lucky", False)),
        "isStampCollectionReward": False,
        "limitedPokemonIdentifier": "",
        "markedRemoteTradable": False,
        "maxStamina": hp,
        "megaEvolvedForms": [],
        "move1": int(gd.moves[fast]["id"]),
        "move2": int(gd.moves[charged]["id"]),
        "move2IsPurifiedExclusive": False,
        "move3": int(gd.moves[second]["id"]) if second else 0,
        "nickname": special.get("nickname", ""),
        "npcCombatStats": None,
        "numUpgrades": rng.randint(0, 10),
        "originDetail": {"originDetail": None, "originDetailCase": rng.choice([1, 2, 4, 6])},
        "originEvents": special.get("events", []),
        "originalOwnerNickname": "Ruilvriend" if special.get("traded") else "",
        "ownerName": "",
        "pokeball": rng.choice([1, 2, 3, 5]),
        "pokemonContestInfo": None,
        "pokemonDisplay": display(
            rng, form_name, shiny=bool(special.get("shiny", False)), alignment=int(special.get("alignment", 0)),
            costume=int(special.get("costume", 0)), location_card=special.get("location_card"),  # type: ignore[arg-type]
            bread=1 if special.get("bread") else 0,
        ),
        "pokemonId": dex,
        "pokemonTagIds": special.get("tags", []),
        "preBoostedAdditionalCpMultiplier": 0.0,
        "preBoostedCp": 0,
        "pvpCombatStats": None,
        "size": rng.choice([0, 3, 3, 3, 4]),
        "stamina": hp,
        "tempEvoCp": 0,
        "tempEvoCpMultiplier": 0.0,
        "tempEvoStaminaModifier": 0.0,
        "tradedTimeMs": caught_ms + DAY_MS if special.get("traded") else 0,
        "tradingOriginalOwnerHash": rng.randint(10**8, 10**9) if special.get("traded") else 0,
        "weightKg": round(rng.uniform(1.0, 200.0), 4),
    }
    return record


def egg(rng: random.Random) -> dict[str, object]:
    return {
        "id": rng.randint(2**53 + 1, 2**64 - 1), "isEgg": True, "pokemonId": 0, "pokemonDisplay": None, "cp": 0,
        "eggKmWalkedTarget": 5.0, "eggKmWalkedStart": 0.0, "eggType": 1, "eggIncubatorId": "",
        "creationTimeMs": BASE_TIME_MS, "capturedS2CellId": rng.randint(10**17, 10**18),
    }


def specials(index: int, dex: int) -> dict[str, object]:
    """Deterministic special cases, so tests can rely on them."""
    table: dict[int, dict[str, object]] = {
        0: {"favorite": True},
        1: {"shiny": True, "favorite": False},
        2: {"lucky": True, "traded": True, "favorite": False},
        3: {"ivs": (15, 15, 15), "favorite": False},
        4: {"age_days": 3500, "favorite": False},  # caught in 2016
        5: {"location_card": 18, "favorite": False},
        6: {"alignment": 1, "favorite": False},
        7: {"alignment": 2, "favorite": False},
        8: {"bread": True, "favorite": False},
        9: {"nickname": "Bewaren", "favorite": False},
        10: {"events": ["community_day_test_event_name"], "favorite": False},
        11: {"tags": [12292984323225294185], "favorite": False},
        12: {"second_move": True, "favorite": False},
    }
    if dex == 129:  # Magikarp copies: weak IVs and one that is a strong Great League Gyarados
        return {0: {"ivs": (0, 15, 15), "level": 20.0, "favorite": False},
                1: {"ivs": (3, 2, 1), "level": 20.0, "favorite": False}}.get(index % 6, {"favorite": False})
    return table.get(index, {"favorite": False} if index % 3 else {})


def main() -> None:
    rng = random.Random(SEED)
    gd = load_gamedata()
    pokemons: list[dict[str, object]] = []
    counter = 0
    for dex, form_name, copies in ROSTER:
        for copy in range(copies):
            special = specials(counter if dex != 129 else copy, dex)
            if form_name.endswith("Costume2099"):
                special = {**special, "costume": 11}
            pokemons.append(pokemon_record(rng, gd, dex, form_name, copy, special))
            counter += 1
    pokemons.extend(egg(rng) for _ in range(3))
    rng.shuffle(pokemons)
    export = {
        "account": {
            "activeTrainingPokemon": [], "ageLevel": 3, "battleLockoutEndMs": 0, "creationTimeMs": BASE_TIME_MS - 3600 * DAY_MS,
            "currencyBalance": [
                {"currencyType": "POKECOIN", "fiatCurrencyCostE6": 0, "fiatCurrencyType": "", "fiatPurchasedQuantity": 0, "quantity": 250},
                {"currencyType": "STARDUST", "fiatCurrencyCostE6": 0, "fiatCurrencyType": "", "fiatPurchasedQuantity": 0, "quantity": 1234567},
            ],
            "combatLog": {
                "currentSeasonResults": {"currentStreak": 1, "longestWinStreak": 4, "rank": 12, "rating": 1800.5, "season": 24,
                                         "stardustEarned": 10000, "totalBattles": 50, "totalWins": 30},
                "lifetimeResults": {"currentStreak": 1, "longestWinStreak": 9, "rank": 0, "rating": 0.0, "season": 0,
                                    "stardustEarned": 90000, "totalBattles": 400, "totalWins": 250},
            },
            "helpshiftUserId": "synthetic-helpshift-id",
            "maxItemStorage": 4000, "maxPokemonStorage": 500,
            "name": "TestTrainer",
            "obfuscatedPlayerId": "synthetic-obfuscated-player-0001",
            "playerSupportId": "SYNTHETIC1",
            "quagoPlayerId": "synthetic-quago-id",
            "team": 2,
            "buddyObservedData": {"attractivePoiId": "synthetic-poi-id"},
            "timeZoneOffsetMs": 7200000,
        },
        "items": [
            {"claimableExpirationConsolationCount": 0, "count": c, "expirationTime": "", "ignoreInventoryCount": False,
             "item": i, "itemName": n, "timePeriodCounter": None, "unconvertedLocalExpirationTimeMs": 0, "unseen": False}
            for i, n, c in ((1, "PokeBall", 120), (2, "GreatBall", 80), (3, "UltraBall", 60), (101, "Potion", 20),
                            (201, "Revive", 30), (701, "RazzBerry", 40), (1301, "RareCandy", 25), (1302, "XlRareCandy", 3),
                            (1201, "MoveRerollFastAttack", 4), (1202, "MoveRerollSpecialAttack", 6),
                            (1203, "MoveRerollEliteFastAttack", 1), (1401, "FreeRaidTicket", 2), (1506, "Mp", 800))
        ],
        "player": {
            "combatStats": {"badges": {"52": {"numTotal": 60, "numWon": 35}, "53": {"numTotal": 20, "numWon": 9},
                                       "54": {"numTotal": 5, "numWon": 1}}},
            "experience": 98765432, "kmWalked": 4321.5, "level": 45, "nextLevelExp": 102_000_000,
            "numEggsHatched": 800, "numEvolutions": 1500, "numPokemonCaptured": 30000, "numPokemonEncountered": 33000,
            "numRaidBattleWon": 400, "numRaidBattleTotal": 450, "pokeStopVisits": 25000,
            "numPokemonCaughtByType": [0] + [100] * 18,
        },
        "pokemons": pokemons,
        "time": EXPORT_TIME,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(export, indent=1))
    print(f"wrote {OUT.relative_to(ROOT)} with {len(pokemons)} records")


if __name__ == "__main__":
    main()
