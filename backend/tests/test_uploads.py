"""Multipart uploads: login first, a hard size cap, and the expected form fields (audit A04)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from tests.conftest import TEST_LIMITS, Api, gamedata_files

BOUNDARY = "oak-test-boundary"
MIB = 1024 * 1024


def _multipart(size: int) -> bytes:
    head = (
        f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="file"; filename="PGSStats.json"\r\n'
        "Content-Type: application/json\r\n\r\n"
    ).encode()
    return head + b"x" * size + f"\r\n--{BOUNDARY}--\r\n".encode()


def test_oversized_upload_is_refused_on_its_declared_length(owner: Api, container: Any) -> None:
    container.settings.max_import_mb = 1
    response = owner.post("/api/v1/imports/upload", files={"file": ("big.json", b"x" * (2 * MIB), "application/json")})
    assert response.status_code == 413


def test_size_limit_holds_without_content_length(owner: Api, container: Any) -> None:
    container.settings.max_import_mb = 1
    body = _multipart(2 * MIB)

    def chunks() -> Iterator[bytes]:
        for start in range(0, len(body), 64 * 1024):
            yield body[start : start + 64 * 1024]

    response = owner.client.post(
        "/api/v1/imports/upload",
        content=chunks(),
        headers={"content-type": f"multipart/form-data; boundary={BOUNDARY}", **owner.headers},
    )
    assert response.status_code == 413


def test_upload_needs_multipart_and_a_file(owner: Api) -> None:
    account = owner.account()
    assert owner.post("/api/v1/imports/upload", data={"account_id": str(account)}).status_code == 415
    no_file = owner.post(
        "/api/v1/imports/upload",
        files={"other": ("x.txt", b"{}", "text/plain")},
        data={"account_id": str(account)},
    )
    assert no_file.status_code == 422 and no_file.json()["error"]["code"] == "FILE_REQUIRED"


def test_gamedata_upload_accepts_all_source_files(owner: Api, container: Any) -> None:
    container.gamedata.limits = TEST_LIMITS
    files = gamedata_files()
    fields = {
        "pokeminers": "pokeminers",
        "pvpoke": "pvpoke",
        "rankings_great": "pvpoke-rankings-great",
        "rankings_ultra": "pvpoke-rankings-ultra",
        "rankings_master": "pvpoke-rankings-master",
    }
    response = owner.post(
        "/api/v1/gamedata/upload",
        files={field: (f"{field}.json", files[source], "application/json") for field, source in fields.items()},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "activated"
    assert container.gamedata.active() is not None
