import csv
import io
import logging

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


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
        raise ValueError(f"File too large ({mb:.1f} MB). Maximum allowed size is 10 MB.")


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
            stripped = cell.strip()
            if stripped and stripped[0] in _FORMULA_PREFIXES and not _is_numeric(stripped):
                flagged.append((row_idx, col_idx, stripped[:30]))

    if flagged:
        logger.warning(
            "CSV contains %d cell(s) with potential formula injection. "
            "First occurrence: row %d col %d value %r",
            len(flagged), flagged[0][0], flagged[0][1], flagged[0][2],
        )
        raise ValueError(
            "CSV contains cells that look like spreadsheet formulas "
            "(values starting with =, +, @). Please export a clean CSV without formulas."
        )


def _is_numeric(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False
