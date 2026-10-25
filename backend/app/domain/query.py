"""OAK search syntax for the Pokémon Box (spec §9.4). Documented in ``docs/QUERY_SYNTAX.md``.

Terms are separated by spaces or ``&`` and combined with AND. ``!`` negates a term.

    gyarados cp>2500 shiny !favorite year:2018 iv>=90 ivs:15/15/15 #130 move:waterfall

Pure code: the parser produces :class:`Term` objects; the repository turns them into SQL.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Op = Literal["=", ">", ">=", "<", "<=", "range", "contains"]

NUMERIC_FIELDS = {
    "cp": "cp",
    "hp": "max_hp",
    "iv": "iv_percent",
    "atk": "iv_attack",
    "def": "iv_defense",
    "sta": "iv_stamina",
    "hp_iv": "iv_stamina",
    "level": "level",
    "lvl": "level",
    "year": "caught_year",
    "dex": "species_id",
    "great": "great_rank",
    "gl": "great_rank",
    "ultra": "ultra_rank",
    "ul": "ultra_rank",
    "battle": "battle",
    "bruikbaarheid": "battle",
    "keep": "keep",
    "bewaar": "keep",
}
FLAG_TERMS = {
    "shiny",
    "lucky",
    "shadow",
    "purified",
    "favorite",
    "legendary",
    "mythical",
    "ultrabeast",
    "dynamax",
    "gigantamax",
    "costume",
    "background",
    "hundo",
    "shundo",
    "nundo",
    "traded",
    "new",
    "protected",
    "untagged",
    "duplicate",
    "mega",
    "missing",
    "egg_hatched",
    "buddy",
    "nicknamed",
    "vintage",
    "unknown_date",
}
FLAG_ALIASES = {
    "fav": "favorite",
    "favourite": "favorite",
    "legendarisch": "legendary",
    "mythisch": "mythical",
    "ub": "ultrabeast",
    "dmax": "dynamax",
    "gmax": "gigantamax",
    "kostuum": "costume",
    "locationcard": "background",
    "achtergrond": "background",
    "4*": "hundo",
    "0*": "nundo",
    "nieuw": "new",
    "beschermd": "protected",
    "dup": "duplicate",
    "dubbel": "duplicate",
    "verdwenen": "missing",
    "hatched": "egg_hatched",
    "geruild": "traded",
    "datumonbekend": "unknown_date",
}
TEXT_FIELDS = {"move", "family", "type", "tag", "status", "league", "form", "name"}
# Terms users may expect but OAK cannot answer from the database alone. They fail loudly
# instead of silently matching nothing.
UNSUPPORTED_TERMS = {
    "evolvable": "Zoeken op evolueerbaar kan nog niet. De Evolutieplanner toont welke evoluties mogelijk zijn.",
    "evolueerbaar": "Zoeken op evolueerbaar kan nog niet. De Evolutieplanner toont welke evoluties mogelijk zijn.",
}
_COMPARISON = re.compile(r"^(?P<field>[a-z_]+)(?P<op>>=|<=|>|<|:|=)(?P<value>.+)$")
_RANGE = re.compile(r"^(?P<low>\d+(?:\.\d+)?)-(?P<high>\d+(?:\.\d+)?)$")
_IVS = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{1,2})$")
_DEX = re.compile(r"^#(\d{1,4})$")
MAX_TERMS = 20


class QuerySyntaxError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Term:
    kind: Literal["numeric", "flag", "text", "free", "ivs"]
    field: str
    op: Op = "="
    value: float | str | tuple[float, float] | tuple[int, int, int] | None = None
    negate: bool = False


def parse_query(query: str) -> list[Term]:
    tokens = [t for t in re.split(r"[\s&]+", query.strip().lower()) if t]
    if len(tokens) > MAX_TERMS:
        raise QuerySyntaxError(f"Maximaal {MAX_TERMS} zoektermen.")
    return [_parse_token(token) for token in tokens]


def _parse_token(token: str) -> Term:
    negate = token.startswith("!")
    body = token[1:] if negate else token
    if not body:
        raise QuerySyntaxError("Losse '!' zonder zoekterm.")

    dex = _DEX.match(body)
    if dex:
        return Term("numeric", "species_id", "=", float(dex.group(1)), negate)
    ivs = _IVS.match(body)
    if ivs:
        values = tuple(int(v) for v in ivs.groups())
        if any(v > 15 for v in values):
            raise QuerySyntaxError("IV's lopen van 0 tot 15.")
        return Term("ivs", "ivs", "=", values, negate)  # type: ignore[arg-type]

    if body in UNSUPPORTED_TERMS:
        raise QuerySyntaxError(UNSUPPORTED_TERMS[body])
    flag = FLAG_ALIASES.get(body, body)
    if flag in FLAG_TERMS:
        return Term("flag", flag, negate=negate)

    match = _COMPARISON.match(body)
    if match:
        field, op, value = match["field"], match["op"], match["value"]
        if field == "ivs":
            ivs_value = _IVS.match(value)
            if not ivs_value:
                raise QuerySyntaxError("Gebruik ivs:15/15/15.")
            numbers = tuple(int(v) for v in ivs_value.groups())
            if any(v > 15 for v in numbers):
                raise QuerySyntaxError("IV's lopen van 0 tot 15.")
            return Term("ivs", "ivs", "=", numbers, negate)  # type: ignore[arg-type]
        if field in NUMERIC_FIELDS:
            column = NUMERIC_FIELDS[field]
            if op in (":", "="):
                range_match = _RANGE.match(value)
                if range_match:
                    low, high = float(range_match["low"]), float(range_match["high"])
                    return Term("numeric", column, "range", (min(low, high), max(low, high)), negate)
                op = "="
            try:
                number = float(value)
            except ValueError as exc:
                raise QuerySyntaxError(f"'{value}' is geen getal voor {field}.") from exc
            return Term("numeric", column, op, number, negate)  # type: ignore[arg-type]
        if field in TEXT_FIELDS and op in (":", "="):
            return Term("text", field, "contains", value.replace("_", " ").strip(), negate)
        raise QuerySyntaxError(f"Onbekend zoekveld '{field}'.")

    if re.fullmatch(r"20\d{2}", body):
        return Term("numeric", "caught_year", "=", float(body), negate)
    return Term("free", "name", "contains", body, negate)
