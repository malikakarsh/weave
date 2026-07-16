import logging
import os
import tempfile

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from models import ChartConfig
from pipeline.pipeline import Pipeline
from pipeline.providers import get_provider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Weave", description="CSV + prompt → interactive D3 chart")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChartResponse(BaseModel):
    html: str
    mapping: dict


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chart", response_model=ChartResponse)
async def generate_chart(
    file: UploadFile = File(..., description="CSV file to visualize"),
    prompt: str = Form(..., description="Plain-English description of the chart"),
    provider: str = Form(default="anthropic"),
    model: str | None = Form(default=None),
    title: str = Form(default=""),
    x_label: str = Form(default=""),
    y_label: str = Form(default=""),
    width: int = Form(default=836),
    height: int = Form(default=420),
    color: str = Form(default="#6366f1"),
    y_format: str = Form(default=",.0f"),
    sort: str | None = Form(default=None),
):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    csv_bytes = await file.read()

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(csv_bytes)
        tmp_path = tmp.name

    try:
        config = ChartConfig(
            title=title,
            x_label=x_label,
            y_label=y_label,
            width=width,
            height=height,
            color=color,
            y_format=y_format,
        )

        llm_provider = get_provider(provider, model)
        logger.info("provider=%s model=%s prompt=%r", type(llm_provider).__name__, llm_provider.model, prompt)

        pipeline = Pipeline(llm_provider)
        html, mapping = pipeline.run(tmp_path, prompt, config, sort_override=sort)

        logger.info("chart_type=%s x=%s y=%s", mapping.chart_type, mapping.x_column, mapping.y_column)
        return ChartResponse(html=html, mapping=mapping.model_dump())

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Pipeline error")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)
