"""Password hashing with Argon2id (spec §21.1)."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.errors import ValidationFailedError

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 256
_hasher = PasswordHasher()  # argon2-cffi defaults to Argon2id with RFC 9106 parameters
# Verifying against this keeps the response time for an unknown username equal to a known one.
_DUMMY_HASH = _hasher.hash("oak-timing-equalizer")


def hash_password(password: str) -> str:
    validate_password(password)
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    return _hasher.check_needs_rehash(stored_hash)


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationFailedError(f"Een wachtwoord moet minimaal {MIN_PASSWORD_LENGTH} tekens hebben.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValidationFailedError("Dit wachtwoord is te lang.")
