from models import AxisMapping


class Transformer:
    def transform(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        result = []
        for row in rows:
            x = row.get(mapping.x_column, "").strip()
            y = row.get(mapping.y_column, "").strip()
            if x:
                result.append({"x": x, "y": float(y) if y else None})
        return result
