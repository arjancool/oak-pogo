"""Layering rules (CLAUDE.md): pure modules import no infrastructure."""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
PURE_PACKAGES = ("domain", "analysis", "recommendations", "normalizers")
PURE_MODULES = ("gamedata/transform.py", "gamedata/validate.py", "gamedata/model.py")
FORBIDDEN = (
    "fastapi",
    "sqlalchemy",
    "starlette",
    "httpx",
    "uvicorn",
    "alembic",
    "app.models",
    "app.api",
    "app.repositories",
    "app.services",
    "app.ingestion",
    "app.core.db",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_pure_layers_have_no_infrastructure_imports() -> None:
    files = [p for pkg in PURE_PACKAGES for p in (APP / pkg).rglob("*.py")]
    files += [APP / m for m in PURE_MODULES]
    violations = [
        f"{path.relative_to(APP)} imports {name}"
        for path in files
        for name in _imports(path)
        if any(name == f or name.startswith(f + ".") for f in FORBIDDEN)
    ]
    assert violations == []


def test_no_ai_provider_dependency() -> None:
    pyproject = (APP.parent / "pyproject.toml").read_text()
    for provider in ("openai", "anthropic", "google-generativeai", "ollama"):
        assert provider not in pyproject
