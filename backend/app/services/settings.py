"""Installation-wide settings that the owner can change in the UI."""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.core.db import Database
from app.repositories.settings import get_setting

SPRITE_KEY = "ui.sprite_url_template"
POKEAPI_SPRITE_TEMPLATE = (
    "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{shiny_path}{dex}.png"
)


def load_sprite_template(db: Database, settings: Settings) -> str:
    """The stored choice wins; without one the OAK_SPRITE_URL_TEMPLATE default applies."""
    with db.read() as session:
        value: Any = get_setting(session, SPRITE_KEY, None)
    return settings.sprite_url_template if value is None else str(value)
