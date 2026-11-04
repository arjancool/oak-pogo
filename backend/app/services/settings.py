"""Installation-wide settings that the owner can change in the UI."""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings
from app.core.db import Database
from app.core.sprites import sprite_origin
from app.repositories.settings import get_setting

log = logging.getLogger("oak.settings")

SPRITE_KEY = "ui.sprite_url_template"
POKEAPI_SPRITE_TEMPLATE = (
    "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{shiny_path}{dex}.png"
)


def load_sprite_template(db: Database, settings: Settings) -> str:
    """The stored choice wins; without one the OAK_SPRITE_URL_TEMPLATE default applies."""
    with db.read() as session:
        value: Any = get_setting(session, SPRITE_KEY, None)
    template = settings.sprite_url_template if value is None else str(value)
    if template and sprite_origin(template) is None:
        # An unsafe value never reaches the CSP. OAK then shows no sprites instead (issue #51).
        source = "OAK_SPRITE_URL_TEMPLATE" if value is None else "settings"
        log.warning(
            "sprite source ignored: it must be an https URL with an ordinary host name and {dex}",
            extra={"source": source},
        )
        return ""
    return template
