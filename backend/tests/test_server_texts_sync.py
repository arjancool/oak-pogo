"""Every sentence about imports, synchronisation, the account, Game Data and events has a text in
the interface catalog (ADR-0025).

The server sends these sentences as a code with data and the Dutch text, or stores the code and
the data next to the Dutch message. The interface builds the sentence in the chosen language from
``server.<group>`` in frontend/src/i18n and falls back to the Dutch text when the code is missing
there. These tests make sure no code, variant or plural form is missing.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from tests.conftest import Api

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "frontend" / "src" / "i18n" / "nl.json"
APP = ROOT / "backend" / "app"
# The catalog group of the sentences each module builds.
MODULES = {
    "imports": (
        "domain/classification.py",
        "normalizers/pgsharp.py",
        "ingestion/receive.py",
        "ingestion/processor.py",
    ),
    "sync": ("api/v1/sync.py", "api/v1/accounts.py"),
    "gamedata": ("gamedata/validate.py", "gamedata/store.py", "api/v1/gamedata.py", "api/v1/system.py"),
    "events": ("normalizers/events.py", "services/events.py", "api/v1/events.py"),
    "account": ("api/v1/account_data.py",),
}
CODE = r'"([A-Z][A-Z0-9_]+)"'
PATTERNS = (
    re.compile(rf"(?:_text|Reason|EventFeedError)\(\s*{CODE}"),
    re.compile(rf'"code": {CODE}'),
    re.compile(rf"Issue\(\s*Severity\.\w+,\s*{CODE}"),
    re.compile(rf"_fail\(\s*\w+,\s*{CODE}"),
    re.compile(rf"DecodedPayload\(\s*\w+,\s*None,\s*{CODE}"),
    re.compile(rf"code = {CODE} if .+ else {CODE}"),
    re.compile(rf"code={CODE},\s*message="),
)
VARIANT = re.compile(r"_(one|other|[a-z]+(?:_[a-z]+)*)$")


def _server() -> dict[str, dict[str, str]]:
    return json.loads(CATALOG.read_text(encoding="utf-8"))["server"]


def module_codes(group: str) -> set[str]:
    codes: set[str] = set()
    for module in MODULES[group]:
        source = (APP / module).read_text(encoding="utf-8")
        for pattern in PATTERNS:
            for match in pattern.finditer(source):
                codes |= {g for g in match.groups() if g}
    return codes


def test_every_code_has_an_interface_text() -> None:
    server = _server()
    for group in MODULES:
        codes = module_codes(group)
        assert codes, f"the patterns still find the codes for '{group}'"
        known = {VARIANT.sub("", key) for key in server.get(group, {})}
        missing = sorted(codes - known)
        assert not missing, f"add these codes under 'server.{group}' in {CATALOG.relative_to(ROOT)}: {missing}"
        unused = sorted(known - codes)
        assert not unused, f"'server.{group}' has texts for codes the server no longer sends: {unused}"
    assert len(module_codes("imports")) > 30, "the patterns still find the import messages"


def _check(group: str, item: dict[str, Any], server: dict[str, dict[str, str]]) -> None:
    """The catalog has the variant and the plural forms this server text asks for."""
    code, data = item.get("code"), item.get("data") or {}
    if code is None:
        return  # a name from outside OAK, such as a licence, stays as it is
    key = f"{code}_{data['context']}" if data.get("context") else code
    texts = server.get(group, {})
    if isinstance(data.get("count"), int):
        assert f"{key}_one" in texts and f"{key}_other" in texts, f"server.{group}.{key} needs _one and _other"
    else:
        assert key in texts, f"server.{group}.{key} is missing"
    for name in re.findall(r"{{\s*(\w+)", texts.get(key) or texts.get(f"{key}_other", "")):
        assert name in data or name == "count", f"server.{group}.{key} uses '{name}', which the server does not send"
        if isinstance(data.get(name), dict):
            _check(name, data[name], server)


def test_texts_from_a_real_sync_have_their_variants(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    server = _server()
    account = owner.account()
    _check("sync", owner.get("/api/v1/sync/status", account_id=account).json()["message"], server)
    _check("sync", owner.post(f"/api/v1/accounts/{account}/webhook").json()["message"], server)
    _check("account", owner.get("/api/v1/history/changes", account_id=account).json()["note"], server)
    assert owner.upload(account, export).status_code == 202
    container.runner.drain()
    items = owner.get("/api/v1/inventory/items", account_id=account).json()
    for text in [items["note"], *(i["group_label"] for i in items["items"])]:
        _check("account", text, server)

    partial = copy.deepcopy(export)
    partial["time"] = "2026-10-21 09:30:00 CEST"
    partial["pokemons"] = partial["pokemons"][:20]
    del partial["account"]
    partial["items"] = [*partial["items"], {"item": "geen nummer"}]
    job_id = owner.upload(account, partial).json()["id"]
    container.runner.drain()
    job = owner.get(f"/api/v1/imports/{job_id}").json()
    warnings = job["sync_run"]["warnings"]
    assert {w["code"] for w in warnings} >= {"ACCOUNT_SECTION_MISSING", "SUSPICIOUS_DROP"}
    issues = owner.get(f"/api/v1/imports/{job_id}/errors").json()
    assert any((i["data"] or {}).get("context") == "section" for i in issues), "the export's own section message"
    for row in [*warnings, *issues]:
        assert row["data"] is not None, "every new message keeps its data"
        _check("imports", {"code": row["code"], "data": row["data"]}, server)
    _check("sync", owner.get("/api/v1/sync/status", account_id=account).json()["message"], server)

    bad = owner.post(
        "/api/v1/imports/upload",
        files={"file": ("PGSStats.json", b'{"pokemons": [', "application/json")},
        data={"account_id": str(account)},
    ).json()
    assert bad["error_code"] == "INVALID_JSON" and bad["error_data"] == {"line": 1, "column": 15}
    status = owner.get("/api/v1/sync/status", account_id=account).json()["message"]
    assert status["code"] == "LAST_IMPORT_ERROR" and status["data"]["imports"]["code"] == "INVALID_JSON"
    _check("sync", status, server)

    gd_status = owner.get("/api/v1/gamedata/status").json()
    for text in gd_status["dependent_analyses"]:
        _check("gamedata", text, server)
    for source in owner.get("/api/v1/gamedata/sources").json():
        for key in ("name", "license", "role"):
            _check("gamedata", source[key], server)
    _check("gamedata", owner.get("/api/v1/settings").json()["sprite_notice"], server)
    events = owner.get("/api/v1/events", account_id=account).json()
    for event in events["events"]:
        _check("events", event["source"], server)
