from pipeline.numeric import parse_number, is_number, PLACEHOLDERS


class TestParseNumber:
    def test_plain(self):
        assert parse_number("6.52") == 6.52
        assert parse_number("-350") == -350
        assert parse_number("+1200") == 1200

    def test_currency(self):
        assert parse_number("$6.52") == 6.52
        assert parse_number("€10") == 10
        assert parse_number("-$350") == -350

    def test_thousands_separator(self):
        assert parse_number("1,200.00") == 1200.0
        assert parse_number("-1,200.00") == -1200.0
        assert parse_number("$1,234,567.89") == 1234567.89

    def test_accounting_negative(self):
        assert parse_number("(350.00)") == -350.0
        assert parse_number("($1,200)") == -1200.0

    def test_percent(self):
        assert parse_number("85%") == 85.0

    def test_unicode_minus(self):
        assert parse_number("−350") == -350  # U+2212

    def test_not_numbers(self):
        for v in ("", "-", "+", ".", "N/A", "abc", "=SUM(A1)", "@handle"):
            assert parse_number(v) is None

    def test_placeholders_are_not_numbers(self):
        for p in PLACEHOLDERS:
            assert parse_number(p) is None

    def test_is_number(self):
        assert is_number("$6.52")
        assert not is_number("Room Essentials")
