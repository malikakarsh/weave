from models import AxisMapping


class Transformer:
    def transform(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        if mapping.group_column:
            return self._transform_grouped(rows, mapping)
        return self._transform_flat(rows, mapping)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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

    def _transform_flat(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        allowed = set(mapping.group_filter) if mapping.group_filter else None
        buckets: dict[str, list[float | None]] = {}
        order: list[str] = []

        for row in rows:
            x = row.get(mapping.x_column, "").strip()
            y = row.get(mapping.y_column, "").strip()
            if x and (allowed is None or x in allowed):
                if x not in buckets:
                    buckets[x] = []
                    order.append(x)
                buckets[x].append(float(y) if y else None)

        return [{"x": x, "y": self._agg(buckets[x], mapping.aggregation)} for x in order]

    def _transform_grouped(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        allowed = set(mapping.group_filter) if mapping.group_filter else None
        # buckets[group][x] = list of y values
        buckets: dict[str, dict[str, list[float | None]]] = {}
        x_order: dict[str, list[str]] = {}

        for row in rows:
            x     = row.get(mapping.x_column,    "").strip()
            y     = row.get(mapping.y_column,     "").strip()
            group = row.get(mapping.group_column, "").strip()
            if x and group and (allowed is None or group in allowed):
                if group not in buckets:
                    buckets[group] = {}
                    x_order[group] = []
                if x not in buckets[group]:
                    buckets[group][x] = []
                    x_order[group].append(x)
                buckets[group][x].append(float(y) if y else None)

        # Aggregate y values per (group, x)
        result = []
        for group in sorted(buckets):
            values = [
                {"x": x, "y": self._agg(buckets[group][x], mapping.aggregation)}
                for x in x_order[group]
            ]
            result.append({"group": group, "values": values})

        # top_n: rank groups by sum of their aggregated y, keep the N highest
        if mapping.top_n and len(result) > mapping.top_n:
            def _total(g: dict) -> float:
                return sum(v["y"] for v in g["values"] if v["y"] is not None)
            result = sorted(result, key=_total, reverse=True)[: mapping.top_n]

        return result
