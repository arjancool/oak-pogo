"""Deciding what an import may change (spec §4.7).

A Pokémon that is missing from a new export is only marked as gone when the export is a
complete, valid inventory of the same account. Everything else is a partial import: present
Pokémon are updated, absent ones keep their previous state.

Pure domain code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.domain.pokemon import NormalizedExport

# Reasons a user may override by confirming that an export is complete.
CONFIRMABLE_CODES = frozenset(
    {
        "SUSPICIOUS_DROP",
        "EMPTY_POKEMON_LIST",
        "NICKNAME_CHANGED",
        "ACCOUNT_SECTION_MISSING",
        "ACCOUNT_UNVERIFIED",
        "EXPORT_TIME_UNKNOWN",
    }
)


class ImportKind(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    INVALID = "invalid"
    STALE = "stale"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class Reason:
    code: str
    message: str
    # Whether an explicit user confirmation may override this reason.
    confirmable: bool = False
    # The values in the message, so the interface can show it in another language (ADR-0025).
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AccountContext:
    known_fingerprint: str | None
    known_nickname: str | None
    in_inventory_count: int
    last_export_time: datetime | None
    has_previous_sync: bool


@dataclass(frozen=True, slots=True)
class CompletenessPolicy:
    """Thresholds for the suspicious-drop check. Both must be exceeded to trigger it."""

    max_drop_fraction: float = 0.2
    max_drop_absolute: int = 25


@dataclass(slots=True)
class Classification:
    kind: ImportKind
    reasons: list[Reason] = field(default_factory=list)

    @property
    def confirmable(self) -> bool:
        return self.kind is ImportKind.PARTIAL and bool(self.reasons) and all(r.confirmable for r in self.reasons)


def classify(
    export: NormalizedExport,
    context: AccountContext,
    fingerprint: str | None,
    *,
    policy: CompletenessPolicy | None = None,
    confirm_full: bool = False,
) -> Classification:
    policy = policy or CompletenessPolicy()

    if not export.has_pokemon_list:
        return Classification(
            ImportKind.INVALID,
            [Reason("POKEMON_LIST_MISSING", "De export bevat geen Pokémon-lijst.")],
        )
    if fingerprint and context.known_fingerprint and fingerprint != context.known_fingerprint:
        return Classification(
            ImportKind.INVALID,
            [
                Reason(
                    "ACCOUNT_MISMATCH",
                    "Deze export hoort bij een ander Pokémon GO-account dan dit traineraccount. Er is niets gewijzigd.",
                )
            ],
        )
    if export.pokemon_records > 0 and not export.pokemon and not export.unreadable_records:
        return Classification(
            ImportKind.INVALID,
            [Reason("NO_READABLE_POKEMON", "Geen enkel Pokémon-record is leesbaar.")],
        )
    if (
        export.export_time is not None
        and context.last_export_time is not None
        and export.export_time < context.last_export_time
    ):
        return Classification(
            ImportKind.STALE,
            [
                Reason(
                    "EXPORT_OLDER_THAN_CURRENT",
                    "Deze export is ouder dan de laatst verwerkte export. De huidige gegevens blijven staan.",
                )
            ],
        )

    reasons: list[Reason] = []
    if export.unidentifiable_records:
        reasons.append(
            Reason(
                "UNIDENTIFIABLE_RECORDS",
                (
                    "1 record zonder leesbare Pokémon-ID. Welke Pokémon dat is, is onbekend"
                    if export.unidentifiable_records == 1
                    else f"{export.unidentifiable_records} records zonder leesbare Pokémon-ID. Welke "
                    "Pokémon dat zijn is onbekend"
                )
                + ", dus ontbrekende Pokémon worden niet als verdwenen gemarkeerd.",
                data={"count": export.unidentifiable_records},
            )
        )
    if not export.has_account:
        reasons.append(
            Reason(
                "ACCOUNT_SECTION_MISSING",
                "De accountsectie ontbreekt, dus niet vast te stellen is dat de export bij dit account hoort.",
                confirmable=True,
            )
        )
    if (
        context.has_previous_sync
        and (fingerprint is None or context.known_fingerprint is None)
        and export.trainer.nickname
        and context.known_nickname
        and export.trainer.nickname != context.known_nickname
    ):
        reasons.append(
            Reason(
                "NICKNAME_CHANGED",
                f"De trainernaam is gewijzigd van '{context.known_nickname}' naar "
                f"'{export.trainer.nickname}' en het account is niet anders te verifiëren.",
                confirmable=True,
                data={"old": context.known_nickname, "new": export.trainer.nickname},
            )
        )
    # Replacing an existing inventory needs positive proof that the export comes from the
    # same Pokémon GO account. Without it, nothing may be marked as gone.
    verified = fingerprint is not None and fingerprint == context.known_fingerprint
    identity_reasons = {"ACCOUNT_SECTION_MISSING", "NICKNAME_CHANGED"}
    if context.has_previous_sync and not verified and not any(r.code in identity_reasons for r in reasons):
        reasons.append(
            Reason(
                "ACCOUNT_UNVERIFIED",
                "Niet vast te stellen dat deze export bij het gekoppelde Pokémon GO-account hoort.",
                confirmable=True,
            )
        )
    # Without an export time OAK cannot tell an old export from a new one.
    if context.has_previous_sync and export.export_time is None:
        reasons.append(
            Reason(
                "EXPORT_TIME_UNKNOWN",
                "Het exportmoment ontbreekt of is onleesbaar, dus niet vast te stellen is dat deze export "
                "nieuwer is dan de huidige gegevens.",
                confirmable=True,
            )
        )
    present = len(export.pokemon) + len(export.unreadable_records)
    previous = context.in_inventory_count
    if context.has_previous_sync and previous > 0:
        drop = previous - present
        if present == 0:
            reasons.append(
                Reason(
                    "EMPTY_POKEMON_LIST",
                    f"De export bevat geen Pokémon terwijl er {previous} in de inventaris "
                    f"{'staat' if previous == 1 else 'staan'}.",
                    confirmable=True,
                    data={"count": previous},
                )
            )
        elif drop > policy.max_drop_absolute and drop > previous * policy.max_drop_fraction:
            reasons.append(
                Reason(
                    "SUSPICIOUS_DROP",
                    f"De export bevat {present} Pokémon, {drop} minder dan de huidige inventaris "
                    f"({previous}). Bevestig dat dit een volledige export is voordat OAK ze als "
                    "verdwenen markeert.",
                    confirmable=True,
                    data={"present": present, "drop": drop, "previous": previous},
                )
            )

    if confirm_full:
        reasons = [r for r in reasons if not r.confirmable]
    if reasons:
        return Classification(ImportKind.PARTIAL, reasons)
    return Classification(ImportKind.FULL)
