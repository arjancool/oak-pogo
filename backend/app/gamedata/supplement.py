"""Game rules that neither the Game Master nor PvPoke contains (ADR-0022).

The transform copies these values into every dataset, so the analysis still reads all game
rules from the active dataset. Every rule names where it was checked and when. A change here
raises ``TRANSFORM_REVISION``, so the active dataset is rebuilt with it.
"""

from __future__ import annotations

from typing import Any

# Purifying a Shadow Pokémon raises it to the trainer level, at most level 25, when it is below
# that, and adds 2 to every IV up to 15. The Game Master only has the cost and the charged move.
PURIFICATION: dict[str, Any] = {
    "min_level": 25,
    "capped_by_trainer_level": True,
    "iv_bonus": 2,
    "source": "Bulbapedia, Shadow Pokémon (GO)",
    "checked": "2026-10-25",
}
