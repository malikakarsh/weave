from models import AxisMapping


class Transformer:
    def transform(self, rows: list[dict], mapping: AxisMapping) -> list[dict] | list[dict]:
        if mapping.group_column:
            return self._transform_grouped(rows, mapping)
        return self._transform_flat(rows, mapping)

    def _transform_flat(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        result = []
        for row in rows:
            x = row.get(mapping.x_column, "").strip()
            y = row.get(mapping.y_column, "").strip()
            if x:
                result.append({"x": x, "y": float(y) if y else None})
        return result

    def _transform_grouped(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        allowed = set(mapping.group_filter) if mapping.group_filter else None
        groups: dict[str, list[dict]] = {}
        for row in rows:
            x     = row.get(mapping.x_column,    "").strip()
            y     = row.get(mapping.y_column,     "").strip()
            group = row.get(mapping.group_column, "").strip()
            if x and group and (allowed is None or group in allowed):
                groups.setdefault(group, []).append({"x": x, "y": float(y) if y else None})
        return [{"group": g, "values": v} for g, v in sorted(groups.items())]
