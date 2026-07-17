import math
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
        if mapping.chart_type == "violin":
            return self._transform_violin(rows, mapping)
        if mapping.chart_type == "histogram":
            return self._transform_histogram(rows, mapping)
        if mapping.chart_type in ("radar", "spider"):
            return self._transform_radar(rows, mapping)
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

    @staticmethod
    def _kde(values: list[float], sample_points: list[float], q1: float, q3: float) -> list[float]:
        """Gaussian kernel density estimate evaluated at each sample point.

        Bandwidth uses Silverman's rule of thumb, robust to spread via the IQR.
        """
        n = len(values)
        if n == 0:
            return [0.0] * len(sample_points)
        mean = sum(values) / n
        std = (sum((v - mean) ** 2 for v in values) / n) ** 0.5
        iqr = q3 - q1
        sigma = min(std, iqr / 1.34) if iqr > 0 else std
        if sigma <= 0:
            sigma = std if std > 0 else 1.0
        h = 0.9 * sigma * n ** (-0.2)
        if h <= 0:
            h = 1.0
        norm = 1.0 / (n * h * (2 * math.pi) ** 0.5)
        out = []
        for sp in sample_points:
            total = 0.0
            for v in values:
                u = (sp - v) / h
                total += math.exp(-0.5 * u * u)
            out.append(norm * total)
        return out

    def _transform_radar(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """Radar/spider: one polygon per entity across several metric axes.

        Wide format (metric_columns set): each listed numeric column is an axis;
        values are aggregated per group. Long format (no metric_columns): reuse
        the grouped/flat transform where x_column is the axis label.
        Output shape matches grouped charts: [{group, values:[{x, y}]}].
        """
        metrics = mapping.metric_columns
        grouped = bool(mapping.group_column)

        if not metrics:
            # Long format — x_column is the axis, group_column the series.
            return self._transform_grouped(rows, mapping) if grouped \
                else self._transform_flat(rows, mapping)

        # Wide format — melt the metric columns into axes and aggregate per group.
        buckets: dict[tuple[str | None, str], list[float | None]] = {}
        group_order: list[str] = []
        for row in rows:
            g = row.get(mapping.group_column, "").strip() if grouped else None
            if grouped and not g:
                continue
            if grouped and g not in group_order:
                group_order.append(g)
            for m in metrics:
                v = _to_float(row.get(m, "").strip())
                buckets.setdefault((g, m), []).append(
                    1.0 if mapping.aggregation == "count" else v
                )

        def axis_values(g: str | None) -> list[dict]:
            return [{"x": m, "y": self._agg(buckets.get((g, m), []), mapping.aggregation)}
                    for m in metrics]

        if grouped:
            return [{"group": g, "values": axis_values(g)} for g in group_order]
        return axis_values(None)

    def _bin_edges(self, values: list[float]) -> list[float]:
        """Equal-width bin edges. Bin count is the larger of Freedman-Diaconis and
        Sturges (FD under-bins multimodal data; Sturges keeps a sensible floor),
        clamped to [5, 60]."""
        n = len(values)
        vmin, vmax = min(values), max(values)
        if vmax <= vmin:
            return [vmin, vmin + 1]
        sorted_v = sorted(values)
        iqr = self._quantile(sorted_v, 0.75) - self._quantile(sorted_v, 0.25)
        if iqr > 0:
            width = 2 * iqr / (n ** (1 / 3))
            fd = math.ceil((vmax - vmin) / width) if width > 0 else 0
        else:
            fd = math.ceil(math.sqrt(n))
        sturges = math.ceil(math.log2(n) + 1) if n > 1 else 1
        nbins = max(fd, sturges) or 10
        nbins = max(5, min(60, nbins))
        return [vmin + (vmax - vmin) * i / nbins for i in range(nbins + 1)]

    def _transform_histogram(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """Bin the numeric x_column and count rows per bin. y_column/aggregation are
        ignored — the value is always the frequency. Optional group_column produces
        one series per group over shared bin edges (overlaid in the template)."""
        grouped = bool(mapping.group_column)
        entries: list[tuple[float, str | None]] = []
        group_order: list[str] = []
        for row in rows:
            raw_x = row.get(mapping.x_column, "").strip()
            if not raw_x or not _in_range(raw_x, mapping.x_min, mapping.x_max):
                continue
            v = _to_float(raw_x)
            if v is None:
                continue
            g = row.get(mapping.group_column, "").strip() if grouped else None
            if grouped and not g:
                continue
            if grouped and g not in group_order:
                group_order.append(g)
            entries.append((v, g))

        if not entries:
            return []

        edges = self._bin_edges([v for v, _ in entries])
        nb = len(edges) - 1
        binw = (edges[-1] - edges[0]) / nb
        def idx(v: float) -> int:
            i = int((v - edges[0]) / binw) if binw > 0 else 0
            return max(0, min(nb - 1, i))

        def bins_for(counts: list[int]) -> list[dict]:
            return [{"x0": edges[i], "x1": edges[i + 1], "count": counts[i]} for i in range(nb)]

        if grouped:
            counts: dict[str, list[int]] = {g: [0] * nb for g in group_order}
            for v, g in entries:
                counts[g][idx(v)] += 1
            return [{"group": g, "values": bins_for(counts[g])} for g in group_order]

        flat = [0] * nb
        for v, _ in entries:
            flat[idx(v)] += 1
        return bins_for(flat)

    def _transform_violin(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """One violin per x category (optionally per group): a KDE curve plus the
        five-number summary so the template can draw the density and an inner box.

        Density is sampled over a shared y-range so violins align on the y-axis.
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

        all_vals = [v for vals in buckets.values() for v in vals]
        if not all_vals:
            return []
        y_lo, y_hi = min(all_vals), max(all_vals)
        span = y_hi - y_lo or 1.0
        # Pad the sampled range slightly so the density tails aren't clipped.
        y_lo -= span * 0.05
        y_hi += span * 0.05
        N = 48
        sample_ys = [y_lo + (y_hi - y_lo) * i / (N - 1) for i in range(N)]

        result = []
        for (x, g), values in buckets.items():
            stats = self._box_stats(values)
            if stats is None:
                continue
            density = self._kde(values, sample_ys, stats["q1"], stats["q3"])
            entry = {
                "x": x,
                "density": [[sy, d] for sy, d in zip(sample_ys, density)],
                **stats,
            }
            if grouped:
                entry["group"] = g
            result.append(entry)

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

    @staticmethod
    def _column_is_numeric(rows: list[dict], col: str, sample: int = 50) -> bool:
        """True if a sample of the column's non-empty values all parse as floats."""
        seen = 0
        for row in rows:
            v = row.get(col, "").strip()
            if not v:
                continue
            if _to_float(v) is None:
                return False
            seen += 1
            if seen >= sample:
                break
        return seen > 0

    def _transform_heatmap_density(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """2D histogram: bin two numeric axes into a grid and count/aggregate per
        cell. Output cells as {x0, x1, y0, y1, z}."""
        xs: list[float] = []
        ys: list[float] = []
        zs: list[float | None] = []
        for row in rows:
            rx = row.get(mapping.x_column, "").strip()
            ry = row.get(mapping.y_column, "").strip()
            if not _in_range(rx, mapping.x_min, mapping.x_max):
                continue
            vx, vy = _to_float(rx), _to_float(ry)
            if vx is None or vy is None:
                continue
            z = _to_float(row.get(mapping.z_column, "").strip()) if mapping.z_column else None
            xs.append(vx)
            ys.append(vy)
            zs.append(z)

        if not xs:
            return []

        xe = self._bin_edges(xs)
        ye = self._bin_edges(ys)
        nbx, nby = len(xe) - 1, len(ye) - 1
        bwx = (xe[-1] - xe[0]) / nbx
        bwy = (ye[-1] - ye[0]) / nby

        def idx(v: float, e0: float, bw: float, nb: int) -> int:
            i = int((v - e0) / bw) if bw > 0 else 0
            return max(0, min(nb - 1, i))

        buckets: dict[tuple[int, int], list[float | None]] = {}
        for vx, vy, z in zip(xs, ys, zs):
            key = (idx(vx, xe[0], bwx, nbx), idx(vy, ye[0], bwy, nby))
            buckets.setdefault(key, []).append(1.0 if not mapping.z_column else z)

        agg = mapping.aggregation if mapping.z_column else "sum"
        return [
            {"x0": xe[ix], "x1": xe[ix + 1], "y0": ye[iy], "y1": ye[iy + 1],
             "z": self._agg(vals, agg)}
            for (ix, iy), vals in buckets.items()
        ]

    def _transform_heatmap(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """Matrix heatmap: one {x, y, z} cell per unique (x_column, y_column) pair.
        When both axes are numeric, produce a binned density heatmap instead."""
        if (self._column_is_numeric(rows, mapping.x_column)
                and self._column_is_numeric(rows, mapping.y_column)):
            return self._transform_heatmap_density(rows, mapping)

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
