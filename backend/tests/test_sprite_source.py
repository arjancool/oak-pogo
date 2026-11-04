"""An own sprite source is checked strictly before its host goes into the CSP (issue #51)."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.middleware import content_security_policy
from app.core.sprites import sprite_origin
from app.main import create_app
from app.repositories.settings import set_setting
from app.services.settings import POKEAPI_SPRITE_TEMPLATE, SPRITE_KEY, load_sprite_template
from tests.conftest import Api

UNSAFE = [
    "http://sprites.example.org/{dex}.png",
    "https://sprites.example.org/{dex}.png; script-src *",
    "https://sprites.example.org,https://evil.example/{dex}.png",
    "https://sprites example.org/{dex}.png",
    "https://sprites.example.org/{dex}'.png",
    'https://sprites.example.org/{dex}".png',
    "https://user:secret@sprites.example.org/{dex}.png",
    "https://[::1]/{dex}.png",
    "https://sprites_example.org/{dex}.png",
    "https://-sprites.example.org/{dex}.png",
    "https://sprites.example.org:99999/{dex}.png",
    "https://sprites.example.org/sprite.png",
    "javascript:alert(1)//{dex}",
    "",
]


@pytest.mark.parametrize("template", UNSAFE)
def test_unsafe_templates_have_no_origin(template: str) -> None:
    assert sprite_origin(template) is None
    assert "example" not in content_security_policy(template)


def test_safe_templates_give_only_scheme_host_and_port() -> None:
    assert sprite_origin(POKEAPI_SPRITE_TEMPLATE) == "https://raw.githubusercontent.com"
    assert sprite_origin("https://Sprites.Example.org:8443/a/{dex}.png") == "https://sprites.example.org:8443"
    assert sprite_origin("https://bücher.example/{dex}.png") == "https://xn--bcher-kva.example"
    policy = content_security_policy("https://sprites.example.org/path/{dex}.png?x=1")
    assert "img-src 'self' data: blob: https://sprites.example.org;" in policy


@pytest.mark.parametrize("template", UNSAFE[1:4])
def test_the_setting_refuses_an_unsafe_template(owner: Api, template: str) -> None:
    response = owner.put("/api/v1/settings", {"sprite_source": "custom", "sprite_url_template": template})
    assert response.status_code == 422
    assert response.json()["error"]["data"]["context"] == "sprite_template"


def test_an_unsafe_stored_value_never_reaches_the_csp(owner: Api, container: Any) -> None:
    with container.db.transaction() as session:
        set_setting(session, SPRITE_KEY, "https://x.example/{dex}; script-src *")
    assert load_sprite_template(container.db, container.settings) == ""
    container.sprite_template = load_sprite_template(container.db, container.settings)
    response = owner.get("/api/v1/settings")
    assert response.status_code == 200
    assert "script-src *" not in response.headers["content-security-policy"]
    assert response.json()["sprite_source"] == "none"


class Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def test_an_unsafe_environment_value_is_ignored_with_a_message(settings: Settings) -> None:
    settings.sprite_url_template = "https://x.example/{dex}.png, https://evil.example"
    collect = Collect()
    logger = logging.getLogger("oak.settings")
    with TestClient(create_app(settings)) as client:
        # OAK's own logging setup runs when the app starts, so the handler is added after it.
        logger.addHandler(collect)
        try:
            client.app.state.container.sprite_template = load_sprite_template(  # type: ignore[attr-defined]
                client.app.state.container.db,  # type: ignore[attr-defined]
                settings,
            )
        finally:
            logger.removeHandler(collect)
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert "evil" not in response.headers["content-security-policy"]
    assert any("sprite source ignored" in m for m in collect.messages)
