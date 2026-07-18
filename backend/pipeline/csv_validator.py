import csv
import io
import logging
import re

from pipeline.numeric import PLACEHOLDERS, is_number

logger = logging.getLogger(__name__)

# Generous ceiling: joining up to 8 files (10 MB each) widens the table, so a
# combined CSV legitimately runs to tens of MB. Only the schema goes to the LLM;
# rows are processed in memory, so this stays safe.
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
# The characters that make a `+`/`-`-prefixed cell an actual formula/DDE payload
# (function call, DDE pipe/bang, concatenation) rather than plain signed data.
_FORMULA_PAYLOAD = re.compile(r"[()|!&]")


def validate_csv(content: bytes) -> None:
    """
    Validate that `content` is a safe, well-formed CSV file.
    Raises ValueError with a user-facing message on any failure.
    """
    _check_size(content)
    text = _check_encoding(content)
    _check_no_null_bytes(content)
    rows = _check_parseable(text)
    _check_structure(rows)
    _check_formula_injection(rows)


def _check_size(content: bytes) -> None:
    if len(content) > MAX_FILE_SIZE:
        mb = len(content) / (1024 * 1024)
        limit_mb = MAX_FILE_SIZE // (1024 * 1024)
        raise ValueError(f"File too large ({mb:.1f} MB). Maximum allowed size is {limit_mb} MB.")


def _check_encoding(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("File could not be decoded as text. Make sure it is a valid CSV file.")


def _check_no_null_bytes(content: bytes) -> None:
    if b"\x00" in content:
        raise ValueError("File contains null bytes and is not a valid CSV file.")


def _check_parseable(text: str) -> list[list[str]]:
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel

    try:
        reader = csv.reader(io.StringIO(text), dialect)
        rows = [row for row in reader if any(cell.strip() for cell in row)]
    except csv.Error as e:
        raise ValueError(f"File could not be parsed as CSV: {e}")

    return rows


def _check_structure(rows: list[list[str]]) -> None:
    if len(rows) < 2:
        raise ValueError("CSV must have at least a header row and one data row.")
    if len(rows[0]) < 1:
        raise ValueError("CSV header row has no columns.")
    if all(cell.strip() == "" for cell in rows[0]):
        raise ValueError("CSV header row is empty.")


def _check_formula_injection(rows: list[list[str]]) -> None:
    flagged = []
    for row_idx, row in enumerate(rows[:100], start=1):
        for col_idx, cell in enumerate(row):
            if _looks_like_formula(cell):
                flagged.append((row_idx, col_idx, cell.strip()[:30]))

    if flagged:
        logger.warning(
            "CSV contains %d cell(s) with potential formula injection. "
            "First occurrence: row %d col %d value %r",
            len(flagged), flagged[0][0], flagged[0][1], flagged[0][2],
        )
        raise ValueError(
            "CSV contains cells that look like spreadsheet formulas "
            "(values starting with =, +, -, @). Please export a clean CSV without formulas."
        )


def _looks_like_formula(cell: str) -> bool:
    """Flag genuine spreadsheet-formula / CSV-injection cells while allowing the
    signed data that's common in real datasets. A cell is risky if it starts
    with `=` or `@` (a formula or DDE trigger), or starts with `+`/`-` AND carries
    a formula/DDE payload (a function call, DDE `|`/`!`, or concatenation). Plain
    signed values (+1 Lap, -5.478, +1,200 pts), formatted numbers, and lone
    punctuation placeholders are not formulas."""
    stripped = cell.strip()
    if not stripped or stripped[0] not in _FORMULA_PREFIXES:
        return False
    if stripped in PLACEHOLDERS or is_number(stripped):
        return False
    if stripped[0] in ("=", "@"):
        return True
    # +, - (tab/CR are stripped above, revealing the real first char)
    return bool(_FORMULA_PAYLOAD.search(stripped))
