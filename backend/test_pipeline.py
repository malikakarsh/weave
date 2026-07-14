import sys
sys.path.insert(0, ".")

from models import ChartConfig
from pipeline.data_loader import DataLoader
from pipeline.llm_mapper import LLMMapper
from pipeline.transformer import Transformer
from pipeline.templater import Templater

CSV_PATH = "samples/sample.csv"
PROMPT = "Show me how revenue changed over time"
OUTPUT = "output.html"

schema, rows = DataLoader().load(CSV_PATH)
print("Schema loaded:")
for col in schema.columns:
    print(f"  {col.name} ({col.type.value}): {col.sample}")

print(f"\nSending to LLM with prompt: {PROMPT!r}")
mapping = LLMMapper().map(schema, PROMPT)
print(f"\nAxis mapping: x={mapping.x_column!r}  y={mapping.y_column!r}")

data = Transformer().transform(rows, mapping)
print(f"\nTransformed ({len(data)} rows)")

config = ChartConfig(
    color="#f59e0b",
    curve="natural",
    title="Monthly Revenue 2024",
    x_label="Month",
    y_label="Revenue (USD)",
    y_format="$,.0f",
)
html = Templater().render(data, config)
with open(OUTPUT, "w") as f:
    f.write(html)
print(f"\nChart written to {OUTPUT}")
