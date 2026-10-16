"""Phone number normalisation to E.164 and masking for logs."""
from __future__ import annotations

import re

E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize(raw: str | None, default_country_code: str = "") -> str | None:
    """Return an E.164 number or None when the input cannot be a valid international number.

    MPM stores numbers as entered by operators, so local formats ("0788 123 456") are converted using the
    deployment's default country code, and the international "00" prefix is accepted.
    """
    if not raw:
        return None
    digits = re.sub(r"[\s\-().]", "", str(raw))
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    elif not digits.startswith("+"):
        if digits.startswith("0") and default_country_code:
            digits = f"+{default_country_code}{digits[1:]}"
        elif default_country_code and digits.startswith(default_country_code):
            digits = "+" + digits
        else:
            return None
    return digits if E164.match(digits) else None


def is_valid(phone: str | None) -> bool:
    return bool(phone and E164.match(phone))


def mask(phone: str | None) -> str:
    if not phone or len(phone) < 8:
        return "***"
    return f"{phone[:4]}•••{phone[-3:]}"
