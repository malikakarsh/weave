import pytest

from pipeline.csv_validator import validate_csv, _looks_like_formula


class TestFormulaHeuristic:
    def test_real_formulas_flagged(self):
        for cell in ("=SUM(A1:A9)", "=1+1", "@handle", "+CMD|'/C calc'!A0", "-2+3+cmd"):
            assert _looks_like_formula(cell), cell

    def test_formatted_numbers_allowed(self):
        for cell in ("$6.52", "-350", "-1,200.00", "+1200", "(350.00)", "85%"):
            assert not _looks_like_formula(cell), cell

    def test_placeholders_allowed(self):
        for cell in ("-", "+", ".", "--"):
            assert not _looks_like_formula(cell), cell

    def test_plain_text_allowed(self):
        assert not _looks_like_formula("Room Essentials")


class TestValidateCsv:
    def test_dash_placeholder_passes(self):
        content = b"Item,Price\nGym Lock,-\nMint Gummies,3.27\n"
        validate_csv(content)  # must not raise

    def test_negative_currency_passes(self):
        content = b"Item,Amount\nRefund,\"-1,200.00\"\nFee,350\n"
        validate_csv(content)

    def test_real_formula_rejected(self):
        content = b"Item,Total\nGym Lock,=SUM(B1:B2)\n"
        with pytest.raises(ValueError, match="formula"):
            validate_csv(content)
