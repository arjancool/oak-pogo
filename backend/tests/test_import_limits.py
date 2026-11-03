"""Limits on the structure of an export, the work outside the write lock and the end of a job that
keeps being interrupted (issue #36)."""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.domain.pokemon import MAX_ISSUES_PER_SEVERITY, Severity
from app.ingestion import receive
from app.ingestion.receive import (
    MAX_CONTAINERS,
    MAX_DEPTH,
    MAX_KEYS,
    MAX_POKEMON_RECORDS,
    MAX_VALUES,
    IncomingPayload,
    decode_payload,
)
from app.jobs.runner import MAX_ATTEMPTS
from app.models import BackgroundJob, ImportIssue, ImportJob, TrainerAccount
from app.normalizers.pgsharp import normalize_export
from tests.conftest import Api
from tests.test_server_texts_sync import _check, _server

LIMIT = 64 * 1024 * 1024


def _decode(text: str) -> receive.DecodedPayload:
    return decode_payload(IncomingPayload(body=text.encode(), source="upload"), LIMIT)


def _rejected_for(text: str) -> str | None:
    decoded = _decode(text)
    assert decoded.data is None or decoded.error_code is None
    return decoded.error_data.get("context") if decoded.error_code == "STRUCTURE_TOO_LARGE" else None


# --- limits on the structure ----------------------------------------------------------------------


def test_many_empty_records_are_refused_before_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_parse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("an export over the limit is never parsed")

    monkeypatch.setattr(receive.json, "loads", no_parse)
    text = '{"pokemons":[' + ",".join(["{}"] * MAX_CONTAINERS) + "]}"
    decoded = _decode(text)
    assert decoded.error_code == "STRUCTURE_TOO_LARGE"
    assert decoded.error_data == {"context": "containers", "max": MAX_CONTAINERS}
    assert decoded.error_message == "De export bevat meer dan 500.000 objecten en lijsten."


def test_brackets_and_commas_inside_text_do_not_count() -> None:
    text = json.dumps({"pokemons": [], "note": "{[," * (MAX_CONTAINERS // 2 + 1), "escaped": 'a\\"{'})
    decoded = _decode(text)
    assert decoded.error_code is None
    assert decoded.data is not None and decoded.data["pokemons"] == []


def test_too_many_values() -> None:
    text = '{"pokemons":[' + ",".join(["0"] * MAX_VALUES) + "]}"
    assert _rejected_for(text) == "values"


def test_too_deep() -> None:
    assert _rejected_for("[" * (MAX_DEPTH + 1) + "]" * (MAX_DEPTH + 1)) == "depth"
    assert _rejected_for("[" * MAX_DEPTH + "]" * MAX_DEPTH) is None
    # Deeper than Python's own parser goes.
    assert _rejected_for("[" * 200_000 + "]" * 200_000) == "depth"


def test_too_many_fields_in_one_object() -> None:
    fields = {f"f{i}": 0 for i in range(MAX_KEYS + 1)}
    assert _rejected_for(json.dumps({"pokemons": [], "player": fields})) == "keys"
    del fields["f0"]
    assert _rejected_for(json.dumps({"pokemons": [], "player": fields})) is None


def test_too_many_pokemon_records() -> None:
    records = [{"id": str(i)} for i in range(MAX_POKEMON_RECORDS + 1)]
    assert _rejected_for(json.dumps({"pokemons": records})) == "pokemons"
    assert _rejected_for(json.dumps({"pokemons": records[1:]})) is None


def test_number_with_too_many_digits() -> None:
    assert _rejected_for('{"pokemons": [], "x": ' + "7" * 5000 + "}") == "number"


def test_sample_export_is_well_within_the_limits(export: dict[str, Any]) -> None:
    decoded = _decode(json.dumps(export))
    assert decoded.error_code is None and decoded.data == export


def test_refused_upload_has_a_text_in_both_languages(owner: Api) -> None:
    account = owner.account()
    job = owner.upload(account, {"pokemons": [{} for _ in range(MAX_POKEMON_RECORDS + 1)]}).json()
    assert job["status"] == "rejected" and job["error_code"] == "STRUCTURE_TOO_LARGE"
    assert job["error_data"] == {"context": "pokemons", "max": MAX_POKEMON_RECORDS}
    assert job["error_message"] == "De export bevat meer dan 25.000 Pokémon-records."
    _check("imports", {"code": job["error_code"], "data": job["error_data"]}, _server())


def test_every_structure_context_has_a_text() -> None:
    texts = _server()["imports"]
    english = json.loads(Path(__file__).parents[2].joinpath("frontend/src/i18n/en.json").read_text())["server"]
    for context in receive.STRUCTURE_MESSAGES:
        assert f"STRUCTURE_TOO_LARGE_{context}" in texts
        assert f"STRUCTURE_TOO_LARGE_{context}" in english["imports"]


# --- work outside the write lock --------------------------------------------------------------------


def _write_lock_free(database: Path) -> bool:
    connection = sqlite3.connect(database, timeout=0.05, isolation_level=None)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("ROLLBACK")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        connection.close()


@pytest.mark.parametrize("source", ["upload", "webhook"])
def test_export_is_filtered_and_stored_without_the_write_lock(
    owner: Api, container: Any, export: dict[str, Any], monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    database = container.settings.data_dir / "oak.db"
    assert database.exists()
    seen: list[bool] = []
    original = receive.sanitize_export

    def watching(data: Any) -> Any:
        seen.append(_write_lock_free(database))
        return original(data)

    monkeypatch.setattr(receive, "sanitize_export", watching)
    account = owner.account()
    if source == "upload":
        assert owner.upload(account, export).status_code == 202
    else:
        assert owner.client.post(owner.webhook_path(account), json=export).status_code == 202
    assert seen == [True], "nobody holds the write lock while the export is filtered"


def test_duplicate_or_refused_upload_leaves_no_file(owner: Api, container: Any, export: dict[str, Any]) -> None:
    imports_dir: Path = container.settings.imports_dir
    account = owner.account()
    assert owner.upload(account, export).status_code == 202
    container.runner.drain()
    first = set(imports_dir.iterdir())
    assert len(first) == 1

    again = owner.upload(account, export)
    assert again.json()["status"] == "duplicate"
    other = owner.account("Ander account")
    stranger = copy.deepcopy(export)
    stranger["account"]["obfuscatedPlayerId"] = "someone-else"
    assert owner.upload(other, stranger).json()["status"] == "queued"
    container.runner.drain()
    mismatch = owner.upload(other, export)
    assert mismatch.status_code == 409, mismatch.text
    assert len(set(imports_dir.iterdir())) == 2, "only the two queued imports keep a file"


def test_failed_write_leaves_no_temporary_file(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        receive.store_payload(tmp_path, {"not json": object()})
    assert list(tmp_path.iterdir()) == []


# --- issues while normalizing ---------------------------------------------------------------------


def test_normalizer_only_counts_issues_after_the_limit() -> None:
    raw = {"account": {"name": "x"}, "player": {}, "items": [], "pokemons": ["bad"] * (MAX_ISSUES_PER_SEVERITY + 1500)}
    result = normalize_export(raw)
    errors = [i for i in result.issues if i.severity is Severity.ERROR]
    assert len(errors) == MAX_ISSUES_PER_SEVERITY
    assert result.issues_dropped >= 1500
    assert any(i.severity is not Severity.ERROR for i in result.issues), "other severities are still kept"
    assert result.unidentifiable_records == MAX_ISSUES_PER_SEVERITY + 1500, "counting the records is unchanged"


def test_stored_issues_report_what_was_left_out(owner: Api, container: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    broken = copy.deepcopy(export)
    broken["pokemons"] = broken["pokemons"] + ["bad"] * (MAX_ISSUES_PER_SEVERITY + 20)
    job_id = owner.upload(account, broken).json()["id"]
    container.runner.drain()
    with container.db.read() as session:
        issues = session.scalars(select(ImportIssue).where(ImportIssue.import_job_id == job_id)).all()
    truncated = [i for i in issues if i.code == "ISSUES_TRUNCATED"]
    assert len([i for i in issues if i.code == "RECORD_NOT_OBJECT"]) == MAX_ISSUES_PER_SEVERITY
    assert len(truncated) == 1 and truncated[0].data["count"] >= 20


# --- a job that keeps being interrupted ------------------------------------------------------------


def test_job_interrupted_too_often_fails(owner: Api, container: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    job_id = owner.upload(account, export).json()["id"]
    with container.db.transaction() as session:
        job = session.get(ImportJob, job_id)
        assert job is not None
        job.status = "processing"
        job.attempts = MAX_ATTEMPTS
        background = session.scalars(select(BackgroundJob).where(BackgroundJob.ref_id == job_id)).one()
        background.status = "running"
        background.attempts = MAX_ATTEMPTS
        other = BackgroundJob(
            kind="analysis",
            status="running",
            trainer_account_id=account,
            attempts=MAX_ATTEMPTS - 1,
            created_at=container.clock.now(),
        )
        session.add(other)
        session.flush()
        other_id = other.id

    container.runner.recover()

    with container.db.read() as session:
        job = session.get(ImportJob, job_id)
        background = session.scalars(select(BackgroundJob).where(BackgroundJob.ref_id == job_id)).one()
        other = session.get(BackgroundJob, other_id)
        trainer = session.get(TrainerAccount, account)
        assert job is not None and other is not None and trainer is not None
        assert background.status == "failed"
        assert other.status == "queued", "a job interrupted fewer times is tried again"
        assert job.status == "failed" and job.error_code == "PROCESSING_INTERRUPTED"
        assert job.error_data == {"attempts": MAX_ATTEMPTS}
        assert trainer.sync_status == "error"
    state = owner.get(f"/api/v1/imports/{job_id}").json()
    _check("imports", {"code": state["error_code"], "data": state["error_data"]}, _server())
    container.runner.drain()
    assert owner.get(f"/api/v1/imports/{job_id}").json()["status"] == "failed", "it does not run again"
