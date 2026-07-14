import csv
from datetime import datetime

from models import ColumnInfo, ColumnType, Schema


class DataLoader:
    SAMPLE_SIZE = 3
    DATE_FORMATS = [
        # date only
        "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y",
        # datetime
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S",
        # time only
        "%H:%M:%S", "%H:%M",
    ]

    def load(self, file_path: str) -> tuple[Schema, list[dict]]:
        with open(file_path, newline="", encoding="utf-8") as f:
            sample = f.read(2048)
            dialect = csv.Sniffer().sniff(sample)
            f.seek(0)
            reader = csv.DictReader(f, dialect=dialect)
            rows = list(reader)

        columns = []
        for col in rows[0].keys():
            values = [row[col] for row in rows]
            col_type = self._detect_type(values)
            sample = [v for v in values if v.strip()][:self.SAMPLE_SIZE]
            columns.append(ColumnInfo(name=col, type=col_type, sample=sample))

        schema = Schema(columns=columns, row_count=len(rows))
        self._validate(schema)

        return schema, rows

    def _detect_type(self, values: list[str]) -> ColumnType:
        non_empty = [v for v in values if v.strip()]

        for fmt in self.DATE_FORMATS:
            if all(self._try_parse_date(v, fmt) for v in non_empty):
                return ColumnType.DATE

        if all(self._try_parse_float(v) for v in non_empty):
            return ColumnType.FLOAT

        return ColumnType.STRING

    def _try_parse_date(self, value: str, fmt: str) -> bool:
        try:
            datetime.strptime(value, fmt)
            return True
        except ValueError:
            return False

    def _try_parse_float(self, value: str) -> bool:
        try:
            float(value)
            return True
        except ValueError:
            return False

    def _validate(self, schema: Schema) -> None:
        types = {col.type for col in schema.columns}
        if ColumnType.DATE not in types:
            raise ValueError("Dataset must contain at least one temporal column.")
        if ColumnType.FLOAT not in types:
            raise ValueError("Dataset must contain at least one numeric column.")
