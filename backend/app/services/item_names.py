"""Names of the items in a PGSharp export, in Dutch and English (issue #31).

English is the game's own text. The Pokémon GO app has a file of English texts, ``i18n_english``,
which PokeMiners publishes in ``PokeMiners/pogo_assets`` (``Texts/Latest APK/JSON``). An item is
named there under ``item_<name>_name``, with the PGSharp ``itemName`` in snake case: ``KingsRock``
is ``item_kings_rock_name``. Checked on 6 November 2026.

Pokémon GO has no Dutch version, so Dutch players see the English names in the game. OAK uses
them in Dutch too, except where it has a plain Dutch translation, such as for the incubators.

An item the game texts do not name keeps the name PGSharp gives it, split into words, with a
note here. OAK does not make up a name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ItemName:
    nl: str
    en: str
    group: str


def _same(name: str, group: str) -> ItemName:
    return ItemName(name, name, group)


ITEMS: dict[str, ItemName] = {
    "PokeBall": _same("Poké Ball", "balls"),
    "GreatBall": _same("Great Ball", "balls"),
    "UltraBall": _same("Ultra Ball", "balls"),
    "MasterBall": _same("Master Ball", "balls"),
    "PremierBall": _same("Premier Ball", "balls"),
    "BeastBall": _same("Beast Ball", "balls"),
    "WildBall": _same("GO Safari Ball", "balls"),
    "Potion": _same("Potion", "healing"),
    "SuperPotion": _same("Super Potion", "healing"),
    "HyperPotion": _same("Hyper Potion", "healing"),
    "MaxPotion": _same("Max Potion", "healing"),
    "Revive": _same("Revive", "healing"),
    "MaxRevive": _same("Max Revive", "healing"),
    "RazzBerry": _same("Razz Berry", "berries"),
    "NanabBerry": _same("Nanab Berry", "berries"),
    "PinapBerry": _same("Pinap Berry", "berries"),
    "GoldenRazzBerry": _same("Golden Razz Berry", "berries"),
    "GoldenPinapBerry": _same("Silver Pinap Berry", "berries"),
    "RareCandy": _same("Rare Candy", "candy"),
    "XlRareCandy": _same("Rare Candy XL", "candy"),
    "MoveRerollFastAttack": _same("Fast TM", "tm"),
    "MoveRerollSpecialAttack": _same("Charged TM", "tm"),
    "MoveRerollEliteFastAttack": _same("Elite Fast TM", "tm"),
    "MoveRerollEliteSpecialAttack": _same("Elite Charged TM", "tm"),
    "FreeRaidTicket": _same("Raid Pass", "raid"),
    "PaidRaidTicket": _same("Premium Battle Pass", "raid"),
    "RemoteRaidTicket": _same("Remote Raid Pass", "raid"),
    "LegendaryRaidTicket": _same("EX Raid Pass", "raid"),
    "SunStone": _same("Sun Stone", "evolution"),
    "KingsRock": _same("King's Rock", "evolution"),
    "MetalCoat": _same("Metal Coat", "evolution"),
    "DragonScale": _same("Dragon Scale", "evolution"),
    "UpGrade": _same("Upgrade", "evolution"),
    "Gen4EvolutionStone": _same("Sinnoh Stone", "evolution"),
    "Gen5EvolutionStone": _same("Unova Stone", "evolution"),
    "OtherEvolutionStoneA": _same("Gimmighoul Coins", "evolution"),
    "OtherEvolutionStoneMapleA": _same("Sweet Apple", "evolution"),
    "OtherEvolutionStoneMapleB": _same("Tart Apple", "evolution"),
    "OtherEvolutionStoneMapleC": _same("Syrupy Apple", "evolution"),
    "IncenseOrdinary": _same("Incense", "incense"),
    "IncenseDailyAdventure": _same("Daily Adventure Incense", "incense"),
    "TroyDisk": _same("Lure Module", "incense"),
    "TroyDiskMossy": _same("Mossy Lure Module", "incense"),
    "TroyDiskGlacial": _same("Glacial Lure Module", "incense"),
    "TroyDiskMagnetic": _same("Magnetic Lure Module", "incense"),
    "TroyDiskRainy": _same("Rainy Lure Module", "incense"),
    "TroyDiskSparkly": _same("Golden Lure Module", "incense"),
    "LuckyEgg": _same("Lucky Egg", "boosts"),
    "StarPiece": _same("Star Piece", "boosts"),
    "IncubatorBasicUnlimited": ItemName("Onbeperkte broedmachine", "Incubator ∞", "incubators"),
    "IncubatorBasic": ItemName("Broedmachine", "Egg Incubator", "incubators"),
    "IncubatorSuper": ItemName("Super-broedmachine", "Super Incubator", "incubators"),
    # Not in the game texts; English keeps the PGSharp name.
    "IncubatorSpecial": ItemName("Speciale broedmachine", "Incubator Special", "incubators"),
    "LeaderMapFragment": ItemName("Mysterieus onderdeel", "Mysterious Component", "rocket"),
    "LeaderMap": _same("Rocket Radar", "rocket"),
    "GiovanniMap": _same("Super Rocket Radar", "rocket"),
    "ShadowGemFragment": ItemName("Shadow-scherf", "Shadow Shard", "rocket"),
    "ShadowGem": _same("Purified Gem", "rocket"),
    "Mp": _same("Max Particle", "max"),
    "MpReplenish": _same("Max Particle Pack", "max"),
    "MaxBoost": _same("Max Mushroom", "max"),
    "SpecialCamera": _same("Camera", "other"),
    "Poffin": _same("Poffin", "other"),
    # The game calls ITEM_BREAKFAST the Zygarde Cube, and ITEM_BEANS the Zygarde Cell.
    "Breakfast": _same("Zygarde Cube", "other"),
    "Beans": _same("Zygarde Cell", "other"),
    # Not in the game texts. "Sfida" is the game's internal name for Pokémon GO Plus.
    "SoftSfida": ItemName("Soft Sfida (onbekend item)", "Soft Sfida (unknown item)", "other"),
}

_WORDS = re.compile(r"(?<=[a-z])(?=[A-Z0-9])")


def item_name(name: str | None, item_id: int) -> ItemName:
    """The names of an item. An unknown item keeps its PGSharp name, split into words, in both
    languages; the caller decides the group."""
    if name and name in ITEMS:
        return ITEMS[name]
    label = _WORDS.sub(" ", name) if name else f"Item #{item_id}"
    return ItemName(label, label, "event" if name and name.startswith("EventPassPoint") else "other")
