"""The generated secret key and the rights in the data directory (issue #43)."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import pytest

from app.core import config
from app.core.config import SECRET_KEY_FILENAME, SecretKeyFileError, Settings
from app.main import build_container

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")


def _settings(tmp_path: Path) -> Settings:
    return Settings(env="test", data_dir=tmp_path / "data", start_worker=False, log_level="WARNING")


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@posix_only
def test_a_new_key_never_has_wider_rights(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    settings.ensure_directories()
    seen: list[int] = []
    original = os.replace

    def watching(source: Any, target: Any) -> None:
        seen.append(_mode(Path(source)))
        original(source, target)

    monkeypatch.setattr(config.os, "replace", watching)
    key, generated = settings.resolve_secret_key()
    path = settings.data_dir / SECRET_KEY_FILENAME
    assert generated and len(key) >= config.MIN_SECRET_KEY_LENGTH
    assert seen == [0o600], "already 0600 before it is put in place"
    assert _mode(path) == 0o600
    assert path.read_text(encoding="utf-8") == key
    assert sorted(p.name for p in settings.data_dir.iterdir() if p.name.endswith(".tmp")) == []
    assert settings.resolve_secret_key() == (key, True), "the same key after a restart"


@posix_only
def test_a_key_with_wide_rights_is_restricted(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.ensure_directories()
    path = settings.data_dir / SECRET_KEY_FILENAME
    path.write_text("k" * 40, encoding="utf-8")
    path.chmod(0o644)
    assert settings.resolve_secret_key() == ("k" * 40, True)
    assert _mode(path) == 0o600


@pytest.mark.parametrize("content", ["", "   \n", "te-kort"])
def test_an_invalid_key_file_stops_oak(tmp_path: Path, content: str) -> None:
    settings = _settings(tmp_path)
    settings.ensure_directories()
    path = settings.data_dir / SECRET_KEY_FILENAME
    path.write_text(content, encoding="utf-8")
    with pytest.raises(SecretKeyFileError, match="OAK start niet"):
        settings.resolve_secret_key()
    assert path.read_text(encoding="utf-8") == content, "the file is left as it was"
    with pytest.raises(SecretKeyFileError):
        build_container(settings)


def test_a_configured_key_needs_no_file(tmp_path: Path) -> None:
    settings = Settings(
        env="test", data_dir=tmp_path / "data", secret_key="x" * 40, start_worker=False, log_level="WARNING"
    )
    settings.ensure_directories()
    assert settings.resolve_secret_key() == ("x" * 40, False)
    assert not (settings.data_dir / SECRET_KEY_FILENAME).exists()


@posix_only
def test_the_data_directory_is_for_oak_alone(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.data_dir.mkdir(mode=0o755)
    settings.data_dir.chmod(0o755)
    settings.ensure_directories()
    assert _mode(settings.data_dir) == 0o700
    for directory in (settings.imports_dir, settings.gamedata_dir, settings.backups_dir):
        assert _mode(directory) & 0o077 == 0, directory


@posix_only
def test_a_directory_that_cannot_be_changed_does_not_stop_oak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    settings = _settings(tmp_path)
    settings.data_dir.mkdir(mode=0o755)
    settings.data_dir.chmod(0o755)

    def refuse(_path: Path, _mode: int) -> None:
        raise PermissionError

    monkeypatch.setattr(Path, "chmod", refuse)
    settings.ensure_directories()
    assert "could not restrict permissions" in caplog.text
