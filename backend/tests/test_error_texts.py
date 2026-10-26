"""Every error message the API sends has a text in the interface catalog (ADR-0025).

An error has a code, a Dutch message and the values in that message (``data``). A code raised with
more than one message has a context per message. The interface shows ``server.errors.<CODE>`` or
``server.errors.<CODE>_<context>`` from frontend/src/i18n in the chosen language, and falls back to
the Dutch message when the catalog has no text. This test reads every place that raises an error
and checks that both catalogs have its text, that the Dutch text reads exactly like the message,
and that ``data`` holds every value the texts need.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from app.api.v1.pokemon import PURIFY_ERRORS
from app.core.errors import AppError
from app.domain.query import UNSUPPORTED_TERMS, QuerySyntaxError, parse_query

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"
LANGUAGES = ("nl", "en")
PLACEHOLDER = re.compile(r"{{\s*([\w.]+)\s*(?:,[^}]*)?}}")
# A value the message gets from a variable, such as {year} in an f-string.
HOLE = "\x00"
# Values serverText derives from the data (frontend/src/lib/serverText.ts).
DERIVED = {"leagueName": "league", "typeName": "type", "period": "starts_at"}


def _codes() -> dict[str, str]:
    codes = {"AppError": AppError.code}
    todo = [AppError]
    while todo:
        for cls in todo.pop().__subclasses__():
            codes[cls.__name__] = cls.code
            todo.append(cls)
    # The search parser's error becomes QUERY_SYNTAX; its second argument is the context.
    codes["QuerySyntaxError"] = "QUERY_SYNTAX"
    return codes


CODES = _codes()
# Places that pass on a message written elsewhere; test_passed_on_messages checks those texts.
PASSED_ON = {
    ("api/v1/pokemon.py", "QUERY_SYNTAX"),  # a QuerySyntaxError from the search parser
    ("api/v1/pokemon.py", "VALIDATION_FAILED"),  # why purify() cannot calculate
    ("domain/query.py", "QUERY_SYNTAX"),  # a search term OAK does not support yet
    ("main.py", "HTTP_ERROR"),  # Starlette's own reason, such as "Method Not Allowed": not an OAK text
}


@dataclass(frozen=True)
class Site:
    where: str
    code: str
    context: str | None
    # The message with HOLE for each value; None when the message is not written at this place.
    message: str | None
    # The keys of data; None when data is not written out at this place.
    data: frozenset[str] | None

    @property
    def key(self) -> str:
        return f"{self.code}_{self.context}" if self.context else self.code


def _catalog(language: str) -> dict[str, str]:
    path = ROOT / "frontend" / "src" / "i18n" / f"{language}.json"
    return json.loads(path.read_text(encoding="utf-8"))["server"]["errors"]


def _string(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _text(node: ast.expr | None, constants: dict[str, str]) -> str | None:
    if _string(node) is not None:
        return _string(node)
    if isinstance(node, ast.JoinedStr):
        return "".join(_string(v) or HOLE for v in node.values)
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _text(node.left, constants), _text(node.right, constants)
        return left + right if left is not None and right is not None else None
    return None


def _argument(call: ast.Call, keyword: str, position: int | None) -> ast.expr | None:
    for item in call.keywords:
        if item.arg == keyword:
            return item.value
    return call.args[position] if position is not None and len(call.args) > position else None


def _site(call: ast.Call, name: str, where: str, constants: dict[str, str]) -> tuple[Site, bool]:
    """The error raised by this call, and whether its message and context are written out here."""
    query = name == "QuerySyntaxError"
    code_node = _argument(call, "code", None)
    code = _string(code_node) or CODES[name]
    context_node = _argument(call, "context", 1 if query else None)
    context = _string(context_node)
    data_node = _argument(call, "data", 2 if query else None)
    data: frozenset[str] | None = frozenset()
    if isinstance(data_node, ast.Dict):
        data = frozenset(key for key in map(_string, data_node.keys) if key is not None)
    elif data_node is not None:
        data = None
    message = _text(call.args[0] if call.args else None, constants)
    static = message is not None and (context_node is None or context is not None)
    return Site(where, code, context, message, data), static


def _sites() -> tuple[list[Site], set[tuple[str, str]]]:
    sites: list[Site] = []
    passed_on: set[tuple[str, str]] = set()
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = {
            target.id: node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        where = path.relative_to(APP).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            if name not in CODES:
                continue
            site, static = _site(node, name, f"{where}:{node.lineno}", constants)
            if static:
                sites.append(site)
            else:
                passed_on.add((where, site.code))
    return sites, passed_on


def _reads_as(template: str, message: str) -> bool:
    """Whether the catalog text, with any value for its placeholders, is the message."""
    pattern = "".join(".+" if i % 2 else re.escape(part) for i, part in enumerate(PLACEHOLDER.split(template)))
    return re.fullmatch(pattern, message, flags=re.DOTALL) is not None


def _needs(template: str) -> set[str]:
    return {DERIVED.get(name, name) for name in PLACEHOLDER.findall(template) if isinstance(name, str)}


SITES, PASSED_ON_FOUND = _sites()


def test_the_scan_finds_the_errors() -> None:
    assert len(SITES) > 100, "the scan still finds the places that raise an error"
    assert {"VALIDATION_FAILED", "NOT_FOUND", "QUERY_SYNTAX", "RATE_LIMITED", "INTERNAL_ERROR"} <= {
        s.code for s in SITES
    }


def test_every_error_message_has_an_interface_text() -> None:
    catalogs = {language: _catalog(language) for language in LANGUAGES}
    problems: list[str] = []
    for site in SITES:
        assert site.message is not None
        for language, catalog in catalogs.items():
            text = catalog.get(site.key)
            if text is None:
                problems.append(f"{site.where}: add server.errors.{site.key} to {language}.json")
                continue
            if language == "nl" and not _reads_as(text, site.message):
                problems.append(f"{site.where}: nl {site.key} {text!r} does not read as {site.message!r}")
            if site.data is not None and not _needs(text) <= site.data:
                problems.append(f"{site.where}: {language} {site.key} needs {sorted(_needs(text) - site.data)} in data")
    assert not problems, "\n".join(problems)


def test_only_known_places_pass_on_a_message() -> None:
    assert PASSED_ON_FOUND == PASSED_ON


def test_passed_on_messages() -> None:
    nl, en = _catalog("nl"), _catalog("en")
    tree = ast.parse((APP / "analysis" / "purify.py").read_text(encoding="utf-8"))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "purify")
    reasons = {
        n.value.value
        for n in ast.walk(function)
        if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
    }
    assert reasons == set(PURIFY_ERRORS), "every reason purify() returns has a context in PURIFY_ERRORS"
    for reason, context in PURIFY_ERRORS.items():
        assert nl[f"VALIDATION_FAILED_{context}"] == reason
        assert f"VALIDATION_FAILED_{context}" in en
    for term in UNSUPPORTED_TERMS:
        with pytest.raises(QuerySyntaxError) as raised:
            parse_query(term)
        assert nl[f"QUERY_SYNTAX_{raised.value.context}"] == raised.value.message
        assert f"QUERY_SYNTAX_{raised.value.context}" in en


def test_no_unused_texts() -> None:
    used = {site.key for site in SITES}
    used |= {f"VALIDATION_FAILED_{context}" for context in PURIFY_ERRORS.values()}
    used |= {f"QUERY_SYNTAX_{context}" for context, _ in UNSUPPORTED_TERMS.values()}
    assert sorted(set(_catalog("nl")) - used) == []


def test_error_body(owner: Any, export: dict[str, Any]) -> None:
    """The values in the message travel in data, next to the code, the message and the details."""
    account = owner.account()
    bad = owner.get("/api/v1/pokemon", account_id=account, q="cp>abc").json()["error"]
    assert bad == {
        "code": "QUERY_SYNTAX",
        "message": "'abc' is geen getal voor cp.",
        "details": None,
        "data": {"value": "abc", "field": "cp", "context": "not_a_number"},
    }
    missing = owner.get("/api/v1/nothing-here").json()["error"]
    assert missing["code"] == "NOT_FOUND" and missing["data"] == {"context": "path"}
    invalid = owner.post("/api/v1/auth/change-password", json={}).json()["error"]
    assert invalid["code"] == "VALIDATION_FAILED" and invalid["data"] == {"context": "request"}
    assert invalid["details"] and invalid["details"][0]["loc"]
