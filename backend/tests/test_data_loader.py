import pytest

from models import ColumnType, Schema, ColumnInfo
from pipeline.data_loader import DataLoader


@pytest.fixture
def loader():
    return DataLoader()


# ── _detect_type ──────────────────────────────────────────────────────────────

class TestDetectType:
    def test_floats(self, loader):
        assert loader._detect_type(["1.5", "2", "-3.0", "0"]) == ColumnType.FLOAT

    def test_integers_are_float(self, loader):
        assert loader._detect_type(["10", "20", "30"]) == ColumnType.FLOAT

    def test_iso_dates(self, loader):
        assert loader._detect_type(["2024-01-01", "2024-06-15", "2023-12-31"]) == ColumnType.DATE

    def test_slash_dates_dmy(self, loader):
        assert loader._detect_type(["01/01/2024", "15/06/2024"]) == ColumnType.DATE

    def test_slash_dates_mdy(self, loader):
        assert loader._detect_type(["01/15/2024", "06/30/2024"]) == ColumnType.DATE

    def test_abbrev_month_dates(self, loader):
        assert loader._detect_type(["Jan 01 2024", "Aug 19 2004"]) == ColumnType.DATE

    def test_datetime(self, loader):
        assert loader._detect_type(["2024-01-01 12:00:00", "2024-06-15 08:30:00"]) == ColumnType.DATE

    def test_strings(self, loader):
        assert loader._detect_type(["Alice", "Bob", "Charlie"]) == ColumnType.STRING

    def test_mixed_strings_not_float(self, loader):
        assert loader._detect_type(["100", "N/A", "200"]) == ColumnType.STRING

    def test_empty_values_skipped_float(self, loader):
        # empty strings are filtered; remaining values are float → FLOAT
        assert loader._detect_type(["", "1.5", "", "3.0"]) == ColumnType.FLOAT

    def test_empty_values_skipped_string(self, loader):
        assert loader._detect_type(["", "hello", ""]) == ColumnType.STRING

    def test_all_empty_vacuous_truth(self, loader):
        # all() on empty list returns True — first date format matches vacuously → DATE
        assert loader._detect_type(["", "  "]) == ColumnType.DATE


# ── load() ────────────────────────────────────────────────────────────────────

class TestLoad:
    def test_basic_csv(self, tmp_csv, loader):
        rows = [{"name": "Alice", "score": "90"}, {"name": "Bob", "score": "80"}]
        path = tmp_csv(rows)
        schema, loaded = loader.load(path)

        assert schema.row_count == 2
        assert len(schema.columns) == 2

        name_col = next(c for c in schema.columns if c.name == "name")
        score_col = next(c for c in schema.columns if c.name == "score")
        assert name_col.type == ColumnType.STRING
        assert score_col.type == ColumnType.FLOAT

    def test_rows_match_csv_content(self, tmp_csv, loader):
        rows = [{"x": "A", "y": "10"}, {"x": "B", "y": "20"}]
        path = tmp_csv(rows)
        _, loaded = loader.load(path)
        assert loaded[0]["x"] == "A"
        assert loaded[1]["y"] == "20"

    def test_sample_capped_at_three(self, tmp_csv, loader):
        rows = [{"name": f"item{i}", "val": str(i)} for i in range(10)]
        path = tmp_csv(rows)
        schema, _ = loader.load(path)
        val_col = next(c for c in schema.columns if c.name == "val")
        assert len(val_col.sample) <= 3

    def test_date_column_detected(self, tmp_csv, loader):
        rows = [{"date": "2024-01-01", "amount": "100"}, {"date": "2024-02-01", "amount": "200"}]
        path = tmp_csv(rows)
        schema, _ = loader.load(path)
        date_col = next(c for c in schema.columns if c.name == "date")
        assert date_col.type == ColumnType.DATE

    def test_row_count_matches(self, tmp_csv, loader):
        rows = [{"a": "1", "b": "x"}] * 5
        path = tmp_csv(rows)
        schema, loaded = loader.load(path)
        assert schema.row_count == 5
        assert len(loaded) == 5


# ── header / preamble detection ───────────────────────────────────────────────

def _write_raw(tmp_path, text: str) -> str:
    p = tmp_path / "raw.csv"
    p.write_text(text)
    return str(p)


class TestHeaderDetection:
    def test_title_banner_skipped(self, tmp_path, loader):
        # a title row + blank row above the real table (as exported from Sheets)
        text = (
            "Expenses-USA - Sept-25,,,\n"
            "\n"
            "Item,Date of Purchase,Price (USD),Category\n"
            "Gym Lock,09/02/25,$6.52,Room Essentials\n"
            "Mint Gummies,09/02/25,$3.27,Food\n"
        )
        schema, rows = loader.load(_write_raw(tmp_path, text))
        names = [c.name for c in schema.columns]
        assert names == ["Item", "Date of Purchase", "Price (USD)", "Category"]
        assert rows[0]["Item"] == "Gym Lock"
        price = next(c for c in schema.columns if c.name == "Price (USD)")
        assert price.type == ColumnType.FLOAT  # $6.52 parsed as numeric

    def test_trailing_empty_columns_dropped(self, tmp_path, loader):
        text = "Item,Price,,,\nGym Lock,6.52,,,\nMint Gummies,3.27,,,\n"
        schema, rows = loader.load(_write_raw(tmp_path, text))
        assert [c.name for c in schema.columns] == ["Item", "Price"]
        assert rows[0] == {"Item": "Gym Lock", "Price": "6.52"}

    def test_no_preamble_uses_first_row(self, tmp_path, loader):
        text = "name,score\nAlice,90\nBob,80\n"
        schema, rows = loader.load(_write_raw(tmp_path, text))
        assert [c.name for c in schema.columns] == ["name", "score"]
        assert len(rows) == 2


# ── _validate() ───────────────────────────────────────────────────────────────

class TestValidate:
    def test_raises_when_no_float_column(self, loader):
        schema = Schema(
            columns=[
                ColumnInfo(name="name", type=ColumnType.STRING, sample=["Alice"]),
                ColumnInfo(name="date", type=ColumnType.DATE, sample=["2024-01-01"]),
            ],
            row_count=1,
        )
        with pytest.raises(ValueError, match="numeric column"):
            loader._validate(schema)

    def test_passes_with_float_column(self, loader):
        schema = Schema(
            columns=[
                ColumnInfo(name="name", type=ColumnType.STRING, sample=["Alice"]),
                ColumnInfo(name="value", type=ColumnType.FLOAT, sample=["42"]),
            ],
            row_count=1,
        )
        loader._validate(schema)  # must not raise

    def test_passes_with_only_float_column(self, loader):
        schema = Schema(
            columns=[ColumnInfo(name="value", type=ColumnType.FLOAT, sample=["1"])],
            row_count=1,
        )
        loader._validate(schema)
