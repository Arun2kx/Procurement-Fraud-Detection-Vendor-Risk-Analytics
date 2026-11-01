"""Invoice-number normalisation and small string distances.

The same helpers are used when synthetic invoice numbers are created and when
duplicates are detected, so the rule is reproducible.
"""

from __future__ import annotations

import math
import re


def normalize_invoice_number(value: object) -> str:
    """Upper-case a value and remove characters other than letters and digits."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def casefold_invoice_number(value: object) -> str:
    """Compare invoice numbers without treating punctuation as equal."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    return text.upper()


def trailing_integer_parts(normalized: str) -> tuple[str, int] | None:
    """Return the non-digit prefix and trailing integer, when present."""
    match = re.match(r"^(.*?)(\d+)$", normalized)
    if not match:
        return None
    return match.group(1), int(match.group(2))


def is_near_sequential(left: object, right: object, max_delta: int = 80) -> bool:
    """True when two numbers share a prefix and their trailing integers are close.

    Adjacent vendor invoice series are a common benign pattern. A short numeric
    gap is therefore excluded from fuzzy and near-time alerts. A fraud pattern
    that reuses the next serial number will be missed by this heuristic.
    """
    left_norm = normalize_invoice_number(left)
    right_norm = normalize_invoice_number(right)
    left_parts = trailing_integer_parts(left_norm)
    right_parts = trailing_integer_parts(right_norm)
    if left_parts is None or right_parts is None:
        return False
    if left_parts[0] != right_parts[0]:
        return False
    return abs(left_parts[1] - right_parts[1]) <= max_delta


def levenshtein(left: str, right: str) -> int:
    """Classic edit distance for short invoice numbers."""
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + cost,
                )
            )
        previous = current
    return previous[-1]
