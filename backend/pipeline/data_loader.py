import csv
from datetime import datetime

from models import ColumnInfo, ColumnType, Schema
from pipeline.numeric import PLACEHOLDERS, is_number


class DataLoader:
    SAMPLE_SIZE = 3
    # How many leading rows to scan when hunting for the real header. Exported
    # sheets often carry a title / blank rows above the table.
    HEADER_SCAN = 15
    DATE_FORMATS = [
        # date only
        "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y",
        # Month Day Year (e.g. "Jan 1 2000", "Aug 19 2004")
        "%b %d %Y",
        # datetime
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S",
        # time only
        "%H:%M:%S", "%H:%M",
    ]

    def load(self, file_path: str) -> tuple[Schema, list[dict]]:
        with open(file_path, newline="", encoding="utf-8-sig") as f:
            sample = f.read(2048)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
            except csv.Error:
                dialect = csv.excel
            f.seek(0)
            raw = [row for row in csv.reader(f, dialect)]

        header_idx = self._detect_header(raw)
        header, rows = self._build_rows(raw, header_idx)

        if not rows:
            raise ValueError("CSV must have at least a header row and one data row.")

        columns = []
        for col in header:
            values = [row[col] for row in rows]
            col_type = self._detect_type(values)
            sample = [v for v in values if v.strip()][:self.SAMPLE_SIZE]
            columns.append(ColumnInfo(name=col, type=col_type, sample=sample))

        schema = Schema(columns=columns, row_count=len(rows))
        self._validate(schema)

        return schema, rows

    # ── header / preamble detection ──────────────────────────────────────
    def _detect_header(self, raw: list[list[str]]) -> int:
        """Find the row index that is the real table header.

        Skips title banners and blank rows above the table by picking the first
        row that (a) has >= 2 non-empty, mostly-textual cells and (b) is followed
        by a data row filling the same columns. Falls back to the first row.
        """
        for i in range(min(len(raw), self.HEADER_SCAN)):
            filled = [j for j, c in enumerate(raw[i]) if c.strip()]
            if len(filled) < 2:
                continue  # e.g. a lone title cell
            labels = [raw[i][j] for j in filled]
            if not self._mostly_text(labels):
                continue  # a row of numbers is data, not a header
            nxt = raw[i + 1] if i + 1 < len(raw) else []
            nxt_filled = {j for j, c in enumerate(nxt) if c.strip()}
            if len(set(filled) & nxt_filled) >= max(2, len(filled) // 2):
                return i
        return 0

    def _mostly_text(self, cells: list[str]) -> bool:
        numeric = sum(1 for c in cells if is_number(c))
        return numeric <= len(cells) // 2

    def _build_rows(self, raw: list[list[str]], header_idx: int) -> tuple[list[str], list[dict]]:
        """Slice from the header row, keep only named columns (drops trailing/
        interior empty columns), de-duplicate header names, and skip blank rows."""
        header_row = raw[header_idx]
        keep = [(j, name.strip()) for j, name in enumerate(header_row) if name.strip()]

        header: list[str] = []
        seen: dict[str, int] = {}
        cols: list[tuple[int, str]] = []
        for j, name in keep:
            if name in seen:
                seen[name] += 1
                name = f"{name}_{seen[name]}"
            else:
                seen[name] = 0
            header.append(name)
            cols.append((j, name))

        rows: list[dict] = []
        for r in raw[header_idx + 1:]:
            if not any(cell.strip() for cell in r):
                continue  # blank separator row
            rows.append({name: (r[j] if j < len(r) else "") for j, name in cols})

        return header, rows

    # ── type detection ───────────────────────────────────────────────────
    def _detect_type(self, values: list[str]) -> ColumnType:
        # Treat lone-punctuation placeholders (-, +, .) as empty: a numeric
        # column with a "-" gap should still read as numeric.
        non_empty = [v for v in values if v.strip() and v.strip() not in PLACEHOLDERS]

        for fmt in self.DATE_FORMATS:
            if all(self._try_parse_date(v, fmt) for v in non_empty):
                return ColumnType.DATE

        if non_empty and all(is_number(v) for v in non_empty):
            return ColumnType.FLOAT

        return ColumnType.STRING

    def _try_parse_date(self, value: str, fmt: str) -> bool:
        try:
            datetime.strptime(value, fmt)
            return True
        except ValueError:
            return False

    def _validate(self, schema: Schema) -> None:
        types = {col.type for col in schema.columns}
        if ColumnType.FLOAT not in types:
            raise ValueError("Dataset must contain at least one numeric column.")
