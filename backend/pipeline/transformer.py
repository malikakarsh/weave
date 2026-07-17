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


def _to_float(s: str) -> float | None:
    """Parse a row value as float; return None if it can't be converted."""
    try:
        return float(s)
    except (ValueError, TypeError):
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
    def transform(self, rows: list[dict], mapping: AxisMapping) -> list[dict] | dict:
        rows = self._prefilter(rows, mapping)
        if mapping.chart_type == "network":
            return self._transform_network(rows, mapping)
        if mapping.chart_type == "heatmap":
            return self._transform_heatmap(rows, mapping)
        if mapping.chart_type == "symbol_map":
            return self._transform_map(rows, mapping)
        if mapping.chart_type in ("box_plot", "box"):
            return self._transform_box(rows, mapping)
        if mapping.label_column:
            return self._transform_labeled(rows, mapping)
        if mapping.group_column:
            return self._transform_grouped(rows, mapping)
        return self._transform_flat(rows, mapping)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prefilter(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """Apply column-referenced filters and a top-N limit at the row level.

        These target a dimension by naming its column, so 'top 3 colors' vs
        'top 3 cuts' is unambiguous regardless of which is the x-axis vs the
        grouping. Unknown columns are ignored (no-op) rather than dropping rows.
        """
        cols = set(rows[0].keys()) if rows else set()

        # Row filters: keep rows whose column value is one of the allowed values.
        for f in (mapping.filters or []):
            if f.column not in cols:
                continue
            allowed = {v.strip() for v in f.values}
            rows = [r for r in rows if r.get(f.column, "").strip() in allowed]

        # Top-N limit on a chosen column, ranked by the same aggregation as the chart.
        lim = mapping.limit
        if lim and lim.column in cols and lim.n > 0:
            agg = mapping.aggregation
            buckets: dict[str, list[float | None]] = {}
            for r in rows:
                key = r.get(lim.column, "").strip()
                if not key:
                    continue
                y = r.get(mapping.y_column, "").strip()
                buckets.setdefault(key, []).append(
                    1.0 if agg == "count" else (_to_float(y) if y else None)
                )
            ranked = sorted(buckets, key=lambda k: (self._agg(buckets[k], agg) or 0), reverse=True)
            keep = set(ranked[: lim.n])
            rows = [r for r in rows if r.get(lim.column, "").strip() in keep]

        return rows

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

    @staticmethod
    def _quantile(sorted_vals: list[float], p: float) -> float:
        """Linear-interpolation quantile, matching d3.quantile."""
        n = len(sorted_vals)
        if n == 1 or p <= 0:
            return sorted_vals[0]
        if p >= 1:
            return sorted_vals[-1]
        h = (n - 1) * p
        lo = int(h)
        frac = h - lo
        if lo + 1 < n:
            return sorted_vals[lo] + (sorted_vals[lo + 1] - sorted_vals[lo]) * frac
        return sorted_vals[lo]

    def _box_stats(self, values: list[float]) -> dict | None:
        """Five-number summary + Tukey outliers for a list of numeric values."""
        ys = sorted(values)
        if not ys:
            return None
        q1 = self._quantile(ys, 0.25)
        median = self._quantile(ys, 0.5)
        q3 = self._quantile(ys, 0.75)
        iqr = q3 - q1
        lo_fence = q1 - 1.5 * iqr
        hi_fence = q3 + 1.5 * iqr
        inliers = [v for v in ys if lo_fence <= v <= hi_fence]
        outliers = [v for v in ys if v < lo_fence or v > hi_fence]
        return {
            "q1": q1,
            "median": median,
            "q3": q3,
            "whisker_low": inliers[0] if inliers else ys[0],
            "whisker_high": inliers[-1] if inliers else ys[-1],
            "outliers": outliers,
            "mean": sum(ys) / len(ys),
            "count": len(ys),
        }

    def _transform_box(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """One box (five-number summary) per x category, optionally per group.

        Unlike the aggregating modes, this keeps the full distribution so the
        template can draw quartiles, whiskers, and outliers.
        """
        grouped = bool(mapping.group_column)
        buckets: dict[tuple[str, str | None], list[float]] = {}
        x_order: list[str] = []
        group_order: list[str] = []

        for row in rows:
            raw_x = row.get(mapping.x_column, "").strip()
            if not raw_x or not _in_range(raw_x, mapping.x_min, mapping.x_max):
                continue
            x = self._x_key(raw_x, mapping.time_unit) or raw_x
            g = row.get(mapping.group_column, "").strip() if grouped else None
            if grouped and not g:
                continue
            y = _to_float(row.get(mapping.y_column, "").strip())
            if y is None:
                continue
            key = (x, g)
            if key not in buckets:
                buckets[key] = []
                if x not in x_order:
                    x_order.append(x)
                if g and g not in group_order:
                    group_order.append(g)
            buckets[key].append(y)

        result = []
        for (x, g), values in buckets.items():
            stats = self._box_stats(values)
            if stats is None:
                continue
            entry = {"x": x, **stats}
            if grouped:
                entry["group"] = g
            result.append(entry)

        # Preserve first-seen x order, then group order within each x.
        result.sort(key=lambda e: (
            x_order.index(e["x"]),
            group_order.index(e["group"]) if grouped else 0,
        ))
        return result

    def _transform_network(self, rows: list[dict], mapping: AxisMapping) -> dict:
        """Aggregate edges by (source, target) and return {nodes, links}."""
        buckets: dict[tuple[str, str], list[float | None]] = {}
        node_seen: list[str] = []

        for row in rows:
            src = row.get(mapping.x_column, "").strip()
            tgt = row.get(mapping.y_column, "").strip()
            if not src or not tgt:
                continue
            for n in (src, tgt):
                if n not in node_seen:
                    node_seen.append(n)
            key = (src, tgt)
            if key not in buckets:
                buckets[key] = []
            if mapping.z_column:
                w = row.get(mapping.z_column, "").strip()
                buckets[key].append(_to_float(w) if w else None)
            else:
                buckets[key].append(1.0)

        agg = mapping.aggregation if mapping.z_column else "sum"
        links = [
            {"source": src, "target": tgt, "weight": self._agg(vals, agg)}
            for (src, tgt), vals in buckets.items()
        ]

        # Aggregate edge weights per node so the template can size by total weight
        if mapping.z_column:
            node_weight: dict[str, float] = {}
            for (src, tgt), vals in buckets.items():
                w = self._agg(vals, agg) or 0
                node_weight[src] = node_weight.get(src, 0) + w
                node_weight[tgt] = node_weight.get(tgt, 0) + w
            node_list = [{"id": n, "size": node_weight.get(n, 0)} for n in node_seen]
        else:
            node_list = [{"id": n} for n in node_seen]

        return {"nodes": node_list, "links": links}

    def _transform_heatmap(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """Output one {x, y, z} cell per unique (x_column, y_column) pair."""
        buckets: dict[tuple[str, str], list[float | None]] = {}
        x_seen: list[str] = []
        y_seen: list[str] = []

        for row in rows:
            raw_x = row.get(mapping.x_column, "").strip()
            y_cat = row.get(mapping.y_column, "").strip()
            if not raw_x or not y_cat:
                continue
            if not _in_range(raw_x, mapping.x_min, mapping.x_max):
                continue
            x = self._x_key(raw_x, mapping.time_unit) or raw_x
            key = (x, y_cat)
            if key not in buckets:
                buckets[key] = []
                if x not in x_seen:
                    x_seen.append(x)
                if y_cat not in y_seen:
                    y_seen.append(y_cat)
            if mapping.z_column:
                z_str = row.get(mapping.z_column, "").strip()
                buckets[key].append(_to_float(z_str) if z_str else None)
            else:
                buckets[key].append(1.0)

        agg = mapping.aggregation if mapping.z_column else "sum"
        return [
            {"x": x, "y": y, "z": self._agg(buckets[(x, y)], agg)}
            for x in x_seen
            for y in y_seen
            if (x, y) in buckets
        ]

    def _transform_map(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """Output one point per row for symbol maps — no aggregation."""
        result = []
        for row in rows:
            lon_str = row.get(mapping.x_column, "").strip()
            lat_str = row.get(mapping.y_column, "").strip()
            if not lon_str or not lat_str:
                continue
            lon = _to_float(lon_str)
            lat = _to_float(lat_str)
            if lon is None or lat is None:
                continue
            point: dict = {"x": lon, "y": lat}
            if mapping.z_column:
                z_str = row.get(mapping.z_column, "").strip()
                point["z"] = _to_float(z_str) if z_str else None
            if mapping.label_column:
                point["label"] = row.get(mapping.label_column, "").strip()
            if mapping.group_column:
                point["group"] = row.get(mapping.group_column, "").strip()
            result.append(point)
        return result

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
            point: dict = {"x": x_val, "y": _to_float(y_str) if y_str else None, "label": label}
            if mapping.z_column:
                z_str = row.get(mapping.z_column, "").strip()
                point["z"] = _to_float(z_str) if z_str else None
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
                buckets[x].append(1.0 if mapping.aggregation == "count" else (_to_float(y) if y else None))
                if mapping.z_column:
                    z = row.get(mapping.z_column, "").strip()
                    z_buckets[x].append(_to_float(z) if z else None)

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
                buckets[group][x].append(1.0 if mapping.aggregation == "count" else (_to_float(y) if y else None))
                if mapping.z_column:
                    z = row.get(mapping.z_column, "").strip()
                    z_buckets[group][x].append(_to_float(z) if z else None)

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
