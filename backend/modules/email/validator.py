"""Recipient validation and normalization for outbound email."""

import re

from backend.modules.email.provider import EmailValidationError

_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def is_valid_email(email: str) -> bool:
    """Return True when the address looks like a valid email."""
    if not email or not isinstance(email, str):
        return False
    return bool(_EMAIL_PATTERN.match(email.strip()))


def validate_email(email: str) -> str:
    """Validate and normalize a single email address.

    Raises:
        EmailValidationError: When the address is malformed.
    """
    if not is_valid_email(email):
        raise EmailValidationError(f"Invalid email address: {email!r}")
    return email.strip().lower()


def normalize_recipients(emails) -> tuple:
    """Deduplicate, case-fold and validate a list of addresses.

    Invalid entries are silently dropped while valid ones are lower-cased
    and de-duplicated, so the provider never receives a malformed TO field.
    """
    seen = set()
    result = []
    for address in emails:
        if not is_valid_email(address):
            continue
        normalized = address.strip().lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return tuple(result)