"""Install the test subset of the Game Data into an OAK data directory, for end-to-end tests.

Usage:
    OAK_DATA_DIR=<dir> python scripts/e2e_seed_gamedata.py

The subset in fixtures/gamedata is far smaller than a real Game Master, so it would fail the
production validation limits. This script lowers those limits for the test install only. The
running server never does this: it validates every update with the normal limits.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.clock import SystemClock  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.gamedata.fetch import Downloaded  # noqa: E402
from app.gamedata.validate import ValidationLimits  # noqa: E402
from app.main import build_container  # noqa: E402

FIXTURES = ROOT / "fixtures" / "gamedata"
FILES = {
    "pokeminers": "pokeminers-subset.json",
    "pvpoke": "pvpoke-subset.json",
    "pvpoke-rankings-great": "pvpoke-rankings-great-subset.json",
    "pvpoke-rankings-ultra": "pvpoke-rankings-ultra-subset.json",
    "pvpoke-rankings-master": "pvpoke-rankings-master-subset.json",
    "pvpoke-rankings-fantasy-1500": "pvpoke-rankings-fantasy-1500-subset.json",
}
SUBSET_LIMITS = ValidationLimits(min_species=10, min_forms=20, min_moves=20, min_cpm_entries=80)


def main() -> int:
    settings = Settings(start_worker=False, gamedata_auto_update=False)
    settings.ensure_directories()
    container = build_container(settings, SystemClock())
    container.gamedata.limits = SUBSET_LIMITS
    downloads = {
        sid: Downloaded(
            id=sid,
            url=f"fixture://{name}",
            content=(FIXTURES / name).read_bytes(),
            etag=None,
            retrieved_at="2026-10-23T00:00:00+00:00",
        )
        for sid, name in FILES.items()
    }
    result = container.gamedata.update_from_downloads(downloads, origin="upload")
    container.db.engine.dispose()
    print(f"{result.status}: {result.message}")
    return 0 if result.status in ("activated", "unchanged") else 1


if __name__ == "__main__":
    raise SystemExit(main())
