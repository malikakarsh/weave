from datetime import datetime

from models import AxisMapping

_DATE_FORMATS = [
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%b %d %Y",
    "%B %d %Y",
]


def _parse_dt(s: str) -> datetime | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_comparable(s: str):
    """Return a datetime or float for range comparison, or the raw string."""
    d = _parse_dt(s)
    if d:
        return d
    try:
        return float(s)
    except ValueError:
        return s


def _in_range(raw_x: str, x_min: str | None, x_max: str | None) -> bool:
    if not x_min and not x_max:
        return True
    val = _parse_comparable(raw_x)
    if x_min:
        lo = _parse_comparable(x_min)
        try:
            if val < lo:
                return False
        except TypeError:
            pass
    if x_max:
        hi = _parse_comparable(x_max)
        try:
            if val > hi:
                return False
        except TypeError:
            pass
    return True


def _truncate(s: str, unit: str) -> str | None:
    d = _parse_dt(s)
    if not d:
        return None
    if unit == "year":
        return f"{d.year}-01-01"
    if unit == "month":
        return d.strftime("%Y-%m-01")
    if unit == "day":
        return d.strftime("%Y-%m-%d")
    return s


class Transformer:
    def transform(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        if mapping.label_column:
            return self._transform_labeled(rows, mapping)
        if mapping.group_column:
            return self._transform_grouped(rows, mapping)
        return self._transform_flat(rows, mapping)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sort(data: list[dict], order: str) -> list[dict]:
        if order not in ("asc", "desc"):
            return data
        return sorted(data, key=lambda d: (d["y"] is None, d["y"] or 0), reverse=(order == "desc"))

    @staticmethod
    def _agg(values: list[float | None], func: str) -> float | None:
        non_null = [v for v in values if v is not None]
        if not non_null:
            return None
        if func == "mean":
            return sum(non_null) / len(non_null)
        if func == "count":
            return float(len(non_null))
        if func == "min":
            return min(non_null)
        if func == "max":
            return max(non_null)
        return sum(non_null)  # "sum" and anything else

    @staticmethod
    def _x_key(raw_x: str, time_unit: str | None) -> str | None:
        if not time_unit:
            return raw_x
        return _truncate(raw_x, time_unit)

    def _transform_labeled(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """Output one point per unique label — no cross-row aggregation."""
        result = []
        for row in rows:
            raw_x = row.get(mapping.x_column, "").strip()
            y_str = row.get(mapping.y_column, "").strip()
            label = row.get(mapping.label_column, "").strip()
            if not _in_range(raw_x, mapping.x_min, mapping.x_max):
                continue
            x = self._x_key(raw_x, mapping.time_unit)
            if not x or not label:
                continue
            try:
                x_val = float(x)
            except (ValueError, TypeError):
                x_val = x
            point: dict = {"x": x_val, "y": float(y_str) if y_str else None, "label": label}
            if mapping.z_column:
                z_str = row.get(mapping.z_column, "").strip()
                point["z"] = float(z_str) if z_str else None
            result.append(point)
        return result

    def _transform_flat(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        allowed = set(mapping.group_filter) if mapping.group_filter else None
        buckets: dict[str, list[float | None]] = {}
        z_buckets: dict[str, list[float | None]] = {}
        order: list[str] = []

        for row in rows:
            raw_x = row.get(mapping.x_column, "").strip()
            y = row.get(mapping.y_column, "").strip()
            if not _in_range(raw_x, mapping.x_min, mapping.x_max):
                continue
            x = self._x_key(raw_x, mapping.time_unit)
            if x and (allowed is None or x in allowed):
                if x not in buckets:
                    buckets[x] = []
                    z_buckets[x] = []
                    order.append(x)
                buckets[x].append(float(y) if y else None)
                if mapping.z_column:
                    z = row.get(mapping.z_column, "").strip()
                    z_buckets[x].append(float(z) if z else None)

        result = [{"x": x, "y": self._agg(buckets[x], mapping.aggregation)} for x in order]
        if mapping.z_column:
            for i, x in enumerate(order):
                result[i]["z"] = self._agg(z_buckets[x], mapping.aggregation)
        if mapping.top_n:
            result = sorted(result, key=lambda d: (d["y"] is None, d["y"] or 0), reverse=True)[: mapping.top_n]
        return self._sort(result, mapping.sort_order)

    def _transform_grouped(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        allowed = set(mapping.group_filter) if mapping.group_filter else None
        # buckets[group][x] = list of y values
        buckets: dict[str, dict[str, list[float | None]]] = {}
        x_order: dict[str, list[str]] = {}

        z_buckets: dict[str, dict[str, list[float | None]]] = {}

        for row in rows:
            raw_x = row.get(mapping.x_column,    "").strip()
            y     = row.get(mapping.y_column,     "").strip()
            group = row.get(mapping.group_column, "").strip()
            if not _in_range(raw_x, mapping.x_min, mapping.x_max):
                continue
            x = self._x_key(raw_x, mapping.time_unit)
            if x and group and (allowed is None or group in allowed):
                if group not in buckets:
                    buckets[group] = {}
                    z_buckets[group] = {}
                    x_order[group] = []
                if x not in buckets[group]:
                    buckets[group][x] = []
                    z_buckets[group][x] = []
                    x_order[group].append(x)
                buckets[group][x].append(float(y) if y else None)
                if mapping.z_column:
                    z = row.get(mapping.z_column, "").strip()
                    z_buckets[group][x].append(float(z) if z else None)

        # Aggregate y (and optional z) values per (group, x)
        result = []
        for group in sorted(buckets):
            values = [
                {"x": x, "y": self._agg(buckets[group][x], mapping.aggregation)}
                for x in x_order[group]
            ]
            if mapping.z_column:
                for i, x in enumerate(x_order[group]):
                    values[i]["z"] = self._agg(z_buckets[group][x], mapping.aggregation)
            result.append({"group": group, "values": values})

        # top_n: rank groups by sum of their aggregated y, keep the N highest
        if mapping.top_n and len(result) > mapping.top_n:
            def _total(g: dict) -> float:
                return sum(v["y"] for v in g["values"] if v["y"] is not None)
            result = sorted(result, key=_total, reverse=True)[: mapping.top_n]

        # Sort x categories by their total y across all groups
        if mapping.sort_order in ("asc", "desc"):
            cat_totals: dict[str, float] = {}
            for grp in result:
                for pt in grp["values"]:
                    cat_totals[pt["x"]] = cat_totals.get(pt["x"], 0) + (pt["y"] or 0)
            reverse = mapping.sort_order == "desc"
            sorted_cats = sorted(cat_totals, key=lambda x: cat_totals[x], reverse=reverse)
            rank = {x: i for i, x in enumerate(sorted_cats)}
            for grp in result:
                grp["values"].sort(key=lambda pt: rank.get(pt["x"], 0))

        return result
