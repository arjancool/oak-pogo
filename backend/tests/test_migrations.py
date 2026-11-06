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
    assert {"in_gym", "costume_form"} <= {c["name"] for c in inspect(engine).get_columns("pokemon")}
    for table in ("pvp_rankings", "battle_teams"):
        league = next(c for c in inspect(engine).get_columns(table) if c["name"] == "league")
        assert getattr(league["type"], "length", None) == 48, f"{table}.league holds a cup ID"
    assert {"external_id", "starts_at", "ends_at", "featured", "trainer_account_id"} <= {
        c["name"] for c in inspect(engine).get_columns("game_events")
    }
    for table, column in (("import_errors", "data"), ("import_jobs", "error_data"), ("game_data_versions", "errors")):
        assert column in {c["name"] for c in inspect(engine).get_columns(table)}, f"{table}.{column} keeps message data"
    with engine.connect() as connection:
        assert connection.execute(text("SELECT value FROM app_settings WHERE key = 'probe'")).scalar() == '"kept"'
    assert list(settings.backups_dir.glob("oak-pre-migration-0001*.db")), "a backup is made before migrating"
    engine.dispose()


def test_autoincrement_keeps_the_rows_of_every_account(tmp_path: Path) -> None:
    """Migration 0009 rebuilds trainer_accounts. The rows that point to an account stay, and a
    deleted account's ID is not used again (issue #55)."""
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
        command.upgrade(cfg, "0008")
        connection.execute(
            text(
                "INSERT INTO users (id, username, password_hash, role, status, preferences, created_at) "
                "VALUES (1, 'eigenaar', 'x', 'owner', 'active', '{}', '2026-11-06')"
            )
        )
        for account in (1, 2):
            connection.execute(
                text(
                    "INSERT INTO trainer_accounts (id, user_id, nickname, sync_status, settings, created_at) "
                    "VALUES (:id, 1, :name, 'waiting', '{}', '2026-11-06')"
                ),
                {"id": account, "name": f"Account {account}"},
            )
            connection.execute(
                text(
                    "INSERT INTO item_inventory (trainer_account_id, item_id, item_name, count, updated_at) "
                    "VALUES (:id, 1, 'PokeBall', 10, '2026-11-06')"
                ),
                {"id": account},
            )

    migrate(settings, engine)

    with engine.begin() as connection:
        assert connection.execute(text("SELECT count(*) FROM item_inventory")).scalar() == 2, "nothing cascaded"
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1, "foreign keys are on again"
        sql = connection.execute(text("SELECT sql FROM sqlite_master WHERE name = 'trainer_accounts'")).scalar()
        assert "AUTOINCREMENT" in str(sql)
        connection.execute(text("DELETE FROM trainer_accounts WHERE id = 2"))
        assert connection.execute(text("SELECT count(*) FROM item_inventory")).scalar() == 1, "cascade works again"
        connection.execute(
            text(
                "INSERT INTO trainer_accounts (user_id, nickname, sync_status, settings, created_at) "
                "VALUES (1, 'Nieuw', 'waiting', '{}', '2026-11-06')"
            )
        )
        new_id = connection.execute(text("SELECT id FROM trainer_accounts WHERE nickname = 'Nieuw'")).scalar()
    assert new_id == 3, "the ID of the deleted account is not used again"
    assert list(settings.backups_dir.glob("oak-pre-migration-0008*.db")), "a backup is made before migrating"
    engine.dispose()
