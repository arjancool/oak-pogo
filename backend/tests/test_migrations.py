"""Schema migrations run on an existing database without losing data."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from sqlalchemy import inspect, text

from app.core.config import Settings
from app.core.db import create_sqlite_engine
from app.core.migrations import alembic_config, migrate


def test_upgrade_from_first_revision_keeps_data(tmp_path: Path) -> None:
    settings = Settings(
        env="test",
        data_dir=tmp_path / "data",
        secret_key="test-secret-key-that-is-long-enough-123456",
        start_worker=False,
    )
    settings.ensure_directories()
    engine = create_sqlite_engine(settings.database_url)
    cfg = alembic_config(settings)
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0001")
        connection.execute(
            text("INSERT INTO app_settings (key, value, updated_at) VALUES ('probe', '\"kept\"', '2026-10-23')")
        )

    migrate(settings, engine)

    columns = {c["name"] for c in inspect(engine).get_columns("cleanup_recommendations")}
    assert {"battle_score", "keep_score", "scores"} <= columns
    assert "confirmed" in {c["name"] for c in inspect(engine).get_columns("planned_actions")}
    assert {"external_id", "starts_at", "ends_at", "featured", "trainer_account_id"} <= {
        c["name"] for c in inspect(engine).get_columns("game_events")
    }
    with engine.connect() as connection:
        assert connection.execute(text("SELECT value FROM app_settings WHERE key = 'probe'")).scalar() == '"kept"'
    assert list(settings.backups_dir.glob("oak-pre-migration-0001*.db")), "a backup is made before migrating"
    engine.dispose()
