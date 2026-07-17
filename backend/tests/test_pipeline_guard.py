from models import AxisMapping
from pipeline.pipeline import _keep_axes_on_type_change


def m(**kw) -> AxisMapping:
    d = dict(x_column="cut", y_column="price", chart_type="bar")
    d.update(kw)
    return AxisMapping(**d)


CURRENT = m()


def test_pure_type_change_restores_swapped_axes():
    # LLM tried to swap axes to numeric columns to satisfy scatter
    swapped = m(chart_type="scatter", x_column="x", y_column="y")
    fixed = _keep_axes_on_type_change(swapped, CURRENT, "make it scatter plot")
    assert (fixed.x_column, fixed.y_column) == ("cut", "price")


def test_explicit_columns_are_kept():
    named = m(chart_type="scatter", x_column="carat", y_column="price")
    fixed = _keep_axes_on_type_change(named, CURRENT, "make it a scatter of carat vs price")
    assert (fixed.x_column, fixed.y_column) == ("carat", "price")


def test_single_letter_column_uses_word_boundary():
    # 'x' must not be considered "named" just because 'box' contains it
    swapped = m(chart_type="scatter", x_column="x", y_column="price")
    fixed = _keep_axes_on_type_change(swapped, CURRENT, "make it a box plot")
    assert fixed.x_column == "cut"


def test_no_change_when_axes_unchanged():
    same = m(chart_type="box_plot")   # only chart_type changed
    fixed = _keep_axes_on_type_change(same, CURRENT, "make it a box plot")
    assert (fixed.x_column, fixed.y_column) == ("cut", "price")
