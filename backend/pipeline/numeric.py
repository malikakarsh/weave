"""Tolerant numeric parsing shared across the pipeline.

Real-world spreadsheets write numbers as `$6.52`, `-1,200.00`, `(350.00)`
(accounting negatives), `+1,200`, `85%`. A plain `float()` rejects all of
these, which breaks type detection, charting, and trips the CSV formula guard.
`parse_number` recognises them; everything else stays a string.
"""

import re

# Currency symbols we strip before parsing. Extend as needed.
_CURRENCY = "$€£¥₹"
_MINUS = "-−–—"  # ASCII hyphen plus common unicode minus/dash glyphs
# Lone punctuation that spreadsheets use as an empty/zero placeholder — never a
# number and never a formula.
PLACEHOLDERS = {"-", "+", ".", "--", "−", "–", "—", "@"}

_STRIP = re.compile(r"[,\s%" + re.escape(_CURRENCY) + r"]")


def parse_number(s) -> float | None:
    """Parse a possibly-formatted numeric string. Return None if it isn't one.

    Handles currency symbols, thousands separators, trailing percent, and
    parenthesised / unicode-minus negatives. Plain floats pass straight through.

    Fast path first: a bare ``float()`` handles the overwhelmingly common case
    (plain ints/floats, surrounding whitespace, leading sign) as a single C call.
    Only genuinely formatted values fall through to the slower regex cleaning —
    this keeps type detection and per-row transforms cheap on large datasets.
    """
    if s is None:
        return None
    if not isinstance(s, str):
        try:
            return float(s)
        except (TypeError, ValueError):
            return None

    try:
        return float(s)  # fast path: plain numbers, whitespace, +/- sign
    except ValueError:
        pass

    # slow path: currency, thousands separators, percent, accounting negatives
    t = s.strip()
    if not t:
        return None
    neg = False
    if t[0] in _MINUS and len(t) > 1:
        neg, t = True, t[1:]
    if t.startswith("(") and t.endswith(")"):
        neg, t = True, t[1:-1]

    cleaned = _STRIP.sub("", t)
    if cleaned in ("", "+", "-", "."):
        return None
    try:
        v = float(cleaned)
    except ValueError:
        return None
    return -v if neg else v


def is_number(s) -> bool:
    return parse_number(s) is not None
