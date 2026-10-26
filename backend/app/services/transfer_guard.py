"""Who may go on a transfer action list, and what needs an explicit confirmation (ADR-0019).

* A manually protected Pokémon never goes on the list.
* A vintage Pokémon (2016–2019) only after the user lifted its protection for that one
  Pokémon (override with confirmation), and then still only when confirmed in the request.
  It is never added in bulk.
* A favorite, a Pokémon with an unknown catch date and a Pokémon protected by a rule need
  the user's confirmation for that Pokémon.

The confirmation is per Pokémon: the request lists the ids the user ticked one by one. The
concrete reasons confirmed are stored with the action: ``favorite``, ``unknown_date``,
``vintage``, ``protected:<rule code>`` and ``protected:TAG:<tag id>``. The check runs again whenever
the list is read, exported or completed, and any reason that was not part of the confirmation
needs a new one, also when the Pokémon was already protected for another reason (audit A03).

Rule protection is computed from the current Pokémon, its metadata and the account's rules,
never from the stored analysis, which may be missing or outdated (audit A02). The catch year is
read from the current catch date as well as from the stored year, so a projection that is behind
can never lift the vintage protection (audit F01 of 25 October).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.pokemon import catch_date_known, vintage_year
from app.models import Pokemon, PokemonUserMetadata, TagLabel, TrainerAccount
from app.recommendations.cleanup import protection_reasons
from app.recommendations.rules import CleanupRules
from app.services.analysis import pokemon_view, rules_for

# Hard protections handled on their own above: manual blocks, vintage needs an override. Tags
# are confirmed by their stable id, not by the shared TAG code.
OWN_CHECKS = ("VINTAGE", "MANUAL", "TAG")


@dataclass(frozen=True, slots=True)
class GuardContext:
    rules: CleanupRules
    protecting_tags: dict[str, str]
    tz: ZoneInfo


def guard_context(session: Session, account: TrainerAccount, tz: ZoneInfo) -> GuardContext:
    protecting = {
        t.tag_id: t.label
        for t in session.scalars(select(TagLabel).where(TagLabel.trainer_account_id == account.id, TagLabel.protects))
    }
    return GuardContext(rules_for(account), protecting, tz)


def _catch_years(pokemon: Pokemon, tz: ZoneInfo) -> tuple[int | None, int | None]:
    """The stored catch year and the year of the current catch date."""
    return pokemon.caught_year, pokemon.caught_at.astimezone(tz).year if pokemon.caught_at else None


def _text(code: str, text: str, **data: Any) -> dict[str, Any]:
    """A sentence as a code with data, for the interface's language, plus the Dutch text."""
    return {"code": code, "text": text, **({"data": data} if data else {})}


@dataclass(slots=True)
class TransferCheck:
    blocked: str | None = None
    blocked_text: dict[str, Any] | None = None
    # The kinds of confirmation, for display: vintage, favorite, unknown_date, protected.
    needs: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    message_texts: list[dict[str, Any]] = field(default_factory=list)
    # The concrete reasons a confirmation covers, with a readable text for each.
    reasons: dict[str, str] = field(default_factory=dict)
    reason_texts: dict[str, dict[str, Any]] = field(default_factory=dict)

    def block(self, text: dict[str, Any]) -> None:
        self.blocked, self.blocked_text = text["text"], text

    def need(self, kind: str, message: dict[str, Any], reasons: dict[str, dict[str, Any]]) -> None:
        self.needs.append(kind)
        self.messages.append(message["text"])
        self.message_texts.append(message)
        self.reasons.update({key: text["text"] for key, text in reasons.items()})
        self.reason_texts.update(reasons)

    @property
    def confirmation(self) -> list[str]:
        """What to store when the user confirms this Pokémon now."""
        return list(self.reasons)

    def unconfirmed(self, confirmed: Iterable[str]) -> list[str]:
        """The reasons that still need a confirmation, given what the user already confirmed."""
        done = set(confirmed)
        return [key for key in self.reasons if key not in done]


def bulk_vintage_text(year: int) -> dict[str, Any]:
    """Why a bulk action skipped a vintage Pokémon: it only goes on a list one by one."""
    return _text("VINTAGE_BULK", f"Vintage {year}: nooit via een bulkactie", year=year)


def check_transfer(pokemon: Pokemon, metadata: PokemonUserMetadata | None, context: GuardContext) -> TransferCheck:
    check = TransferCheck()
    if metadata is not None and metadata.protected:
        check.block(_text("BLOCKED_MANUAL", "Handmatig beschermd"))
        return check
    years = _catch_years(pokemon, context.tz)
    year = next((vintage_year(y) for y in years if vintage_year(y) is not None), None)
    overridden = metadata is not None and metadata.override_status == "TRANSFER_CANDIDATE"
    if year is not None:
        if not overridden:
            text = f"Vintage {year}: hef eerst de bescherming op bij deze Pokémon"
            check.block(_text("BLOCKED_VINTAGE", text, year=year))
            return check
        check.need(
            "vintage",
            _text("VINTAGE_LIFTED", f"Vintage {year}, bescherming opgeheven", year=year),
            {"vintage": _text("VINTAGE", f"Vintage {year}", year=year)},
        )
    if pokemon.favorite:
        favorite = _text("FAVORITE", "Favoriet")
        check.need("favorite", favorite, {"favorite": favorite})
    if not all(catch_date_known(y) for y in years):
        unknown = _text("UNKNOWN_DATE", "Vangstdatum onbekend")
        check.need("unknown_date", unknown, {"unknown_date": unknown})
    if year is None and not overridden:
        view = pokemon_view(pokemon, metadata, context.protecting_tags)
        protected = {
            f"protected:{r['code']}": r for r in protection_reasons(view, context.rules) if r["code"] not in OWN_CHECKS
        }
        for tag_id in pokemon.tag_ids:
            if tag_id in context.protecting_tags:
                tag = context.protecting_tags[tag_id]
                protected[f"protected:TAG:{tag_id}"] = _text("TAG", f"Beschermende tag '{tag}'", tag=tag)
        if protected:
            items = list(protected.values())
            check.need(
                "protected",
                _text("PROTECTED", "Beschermd: " + ", ".join(r["text"] for r in items), protections=items),
                {key: _text("PROTECTION", r["text"], protections=r) for key, r in protected.items()},
            )
    return check


def confirmation_item(pokemon: Pokemon, check: TransferCheck, confirmed: Iterable[str] = ()) -> dict[str, Any]:
    """What the user is asked to confirm. ``new_reasons`` names what changed since an earlier
    confirmation of the same Pokémon."""
    name = pokemon.species_name or f"#{pokemon.species_id}"
    earlier = list(confirmed)
    return {
        "pokemon_id": pokemon.id,
        "name": f"{name} ({pokemon.form_label})" if pokemon.form_label else name,
        "cp": pokemon.cp,
        "caught_year": pokemon.caught_year,
        "kinds": check.needs,
        "message": "; ".join(check.messages),
        "message_texts": check.message_texts,
        "new_reasons": [check.reasons[key] for key in check.unconfirmed(earlier)] if earlier else [],
        "new_reason_texts": [check.reason_texts[key] for key in check.unconfirmed(earlier)] if earlier else [],
    }
