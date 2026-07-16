import asyncio
import json
import logging
import os
import tempfile

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from models import AxisMapping, ChartConfig
from pipeline.csv_validator import validate_csv
from pipeline.data_loader import DataLoader
from pipeline.decomposer import Decomposer
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


_SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "samples")

PLAYGROUND_DATASETS = [
    {
        "id": "stocks",
        "name": "Stock Prices",
        "description": "Daily closing prices for AAPL, AMZN, GOOG, IBM, and MSFT from 2000–2010.",
        "emoji": "📈",
        "csv": "stocks.csv",
        "prompt": "show stock price trend over time for each company as a multi-series line chart, and show average stock price per company as a bar chart",
    },
    {
        "id": "revenue",
        "name": "Company Revenue",
        "description": "Monthly revenue figures across multiple companies over several years.",
        "emoji": "💰",
        "csv": "sample.csv",
        "prompt": "show total revenue per company as a bar chart sorted descending, and revenue trend over time for each company as a line chart",
    },
    {
        "id": "world_cities",
        "name": "World Cities",
        "description": "55 major world cities with coordinates, population, and continent.",
        "emoji": "🌍",
        "csv": "world_cities.csv",
        "prompt": "plot world cities on a map sized by population and colored by continent, and show total population by continent as a bar chart",
    },
    {
        "id": "diamonds",
        "name": "Diamonds",
        "description": "Diamond prices and attributes including cut, color, clarity, and carat.",
        "emoji": "💎",
        "csv": "diamonds.csv",
        "prompt": "show average diamond price by cut as a bar chart, and show a heatmap of average diamond price by cut and color",
    },
    {
        "id": "restaurants",
        "name": "NYC Restaurants",
        "description": "NYC restaurant inspection records with grades, violations, and borough.",
        "emoji": "🍕",
        "csv": "nyc_restaurants.csv",
        "prompt": "show inspection count by borough as a bar chart, and show a pie chart of inspections by critical flag",
    },
    {
        "id": "iris",
        "name": "Iris Flowers",
        "description": "Classic iris dataset with sepal/petal measurements for three species.",
        "emoji": "🌸",
        "csv": "iris.csv",
        "prompt": "show sepal length vs sepal width as a scatter plot colored by species, and show average petal length by species as a bar chart",
    },
]

_DATASET_MAP = {d["id"]: d for d in PLAYGROUND_DATASETS}


class ChartResponse(BaseModel):
    html: str
    mapping: dict


class InsightsResponse(BaseModel):
    insights: list[str]


_INSIGHTS_PROMPT = (
    "You are a data analyst. Given the chart type, axis mapping, and a sample of the data, "
    "write 3-5 concise, specific insights about what the data shows. "
    "Focus on trends, outliers, comparisons, and notable patterns. "
    "Each insight should be one sentence. Be specific — mention actual values, names, or dates where relevant. "
    "Respond with a JSON array of strings, no other text. Example: [\"insight one\", \"insight two\"]"
)


def _inject(html: str) -> str:
    """Inject iframe helpers: width reset, ResizeObserver, theme handler, SVG export."""
    injected = (
        "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap'>"
        "<style>"
        "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');"
        "html,body{display:block!important;margin:0!important;padding:0!important;"
        "min-height:0!important;height:auto!important;overflow:hidden!important;"
        "font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif!important;}"
        "#chart{width:100%!important;padding:20px 24px!important;margin:0!important;"
        "border-radius:0!important;box-shadow:none!important;"
        "box-sizing:border-box!important;font-family:'Inter',-apple-system,sans-serif!important;}"
        "svg{display:block!important;width:100%!important;height:auto!important;}"
        "text{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif!important;}"
        "</style>"
        "<script>"
        "(function(){"
        "var ch=document.getElementById('chart');"
        "if(ch){ch.style.width='';}"
        "var sv=document.querySelector('svg');"
        "if(sv){sv.style.width='';sv.style.height='';}"
        "})();"
        "window.addEventListener('load',function(){"
        "document.querySelectorAll('button').forEach(function(b){"
        "if(/Copy SVG|Download SVG/.test(b.textContent))b.style.display='none';});"
        "document.querySelectorAll('.edit-label').forEach(function(el){"
        "if(el.textContent.trim()==='Chart Size'){"
        "var row=el.closest('.edit-row');if(row){"
        "var sib=row.nextElementSibling;"
        "row.style.display='none';"
        "if(sib&&sib.classList.contains('edit-divider'))sib.style.display='none';"
        "}}});"
        "function observe(){"
        "var sv=document.querySelector('svg');"
        "var target=sv||document.getElementById('chart')||document.body;"
        "var ro=new ResizeObserver(function(){"
        "var h=target.getBoundingClientRect().height||target.offsetHeight;"
        "if(h>10)window.parent.postMessage({type:'weave-height',height:Math.ceil(h)},'*');"
        "});ro.observe(target);"
        "}"
        "observe();"
        "var _mo=new MutationObserver(function(ms,obs){"
        "if(document.querySelector('svg')){obs.disconnect();observe();}"
        "});_mo.observe(document.body,{childList:true,subtree:true});"
        "});"
        "window.addEventListener('message',function(e){"
        "if(e.data&&e.data.type==='weave-theme'){"
        "var sid='weave-light';var ex=document.getElementById(sid);if(ex)ex.remove();"
        "var dksid='weave-dark';var dkex2=document.getElementById(dksid);if(dkex2)dkex2.remove();"
        "var bgRect=document.querySelector('rect.background');"
        "if(window._weaveBgObs){window._weaveBgObs.disconnect();window._weaveBgObs=null;}"
        "if(!e.data.dark){"
        "var s=document.createElement('style');s.id=sid;"
        "s.textContent="
        "'html,body{background:#f8f9fb!important}'"
        "+'text{fill:#1f2937!important;paint-order:stroke fill;stroke:rgba(255,255,255,0.85);stroke-width:3px;stroke-linejoin:round}'"
        "+'path.land{fill:#d6dde5!important}'"
        "+'path.graticule,.graticule{stroke:#c4cdd6!important}'"
        "+'path.sphere,.sphere{fill:#dbe9f4!important;stroke:#b8d0e8!important}'"
        "+'line.grid-line,.grid line{stroke:#e2e8f0!important}'"
        "+'path.axis-line,.axis .domain,.axis line{stroke:#cbd5e1!important}'"
        "+'path.bar{opacity:0.9}'"
        "+'#edit-panel,.edit-panel{background:#ffffff!important;border-color:#e2e8f0!important;color:#1f2937!important}'"
        "+'#edit-panel input,.edit-panel input{background:#f1f5f9!important;border-color:#cbd5e1!important;color:#1f2937!important}'"
        "+'#edit-panel input::placeholder,.edit-panel input::placeholder{color:#94a3b8!important}'"
        "+'#edit-panel label,.edit-label,.edit-hint{color:#475569!important}'"
        "+'#btn-save,button#btn-save,#btn-edit,button#btn-edit,.chart-actions button{background:#e2e8f0!important;color:#1e293b!important;border-color:#cbd5e1!important}'"
        "+'#edit-panel .edit-divider{border-color:#e2e8f0!important}';"
        "document.head.appendChild(s);"
        "var ch=document.getElementById('chart');"
        "if(ch)ch.style.background='#f8f9fb';"
        "if(bgRect){bgRect.style.fill='#f0f2f5';"
        "window._weaveBgObs=new MutationObserver(function(ms){"
        "ms.forEach(function(m){if(m.attributeName==='fill')"
        "m.target.style.fill=m.target.getAttribute('fill');});});"
        "window._weaveBgObs.observe(bgRect,{attributes:true,attributeFilter:['fill']});}"
        "}else{"
        "var dkid='weave-dark';var dkex=document.getElementById(dkid);if(dkex)dkex.remove();"
        "var ds=document.createElement('style');ds.id=dkid;"
        "ds.textContent="
        "'path.land{fill:#1e2535!important}'"
        "+'path.graticule,.graticule{stroke:#2a3550!important}'"
        "+'path.sphere,.sphere{fill:#141c2e!important;stroke:#1e2a42!important}'"
        "+'line.grid-line,.grid line{stroke:#1e2a40!important}'"
        "+'text{fill:#e2e8f0!important;paint-order:stroke fill;stroke:rgba(0,0,0,0.75);stroke-width:3px;stroke-linejoin:round}';"
        "document.head.appendChild(ds);"
        "var ch=document.getElementById('chart');"
        "if(ch)ch.style.background='';"
        "if(bgRect)bgRect.style.fill='';"
        "}"
        "return;}"
        "if(!e.data||e.data.type!=='weave-export')return;"
        "var sv=document.querySelector('svg');if(!sv)return;"
        "var cl=sv.cloneNode(true);"
        "cl.setAttribute('width',e.data.width);"
        "cl.setAttribute('height',e.data.height);"
        "var css='';"
        "try{for(var i=0;i<document.styleSheets.length;i++){"
        "try{var r=document.styleSheets[i].cssRules||[];"
        "for(var j=0;j<r.length;j++)css+=r[j].cssText+'\\n';"
        "}catch(x){}}}catch(x){};"
        "if(css){var st=document.createElementNS('http://www.w3.org/2000/svg','style');"
        "st.textContent=css;cl.insertBefore(st,cl.firstChild);};"
        "var bg=cl.querySelector('rect.background,rect[class=\"background\"],.sphere');"
        "var chartEl=document.getElementById('chart');"
        "var liveBg=(chartEl&&window.getComputedStyle(chartEl).backgroundColor)||window.getComputedStyle(document.body).backgroundColor||'#1a1d27';"
        "if(bg){bg.setAttribute('fill',liveBg);}else{"
        "var bgr=document.createElementNS('http://www.w3.org/2000/svg','rect');"
        "bgr.setAttribute('width','100%');bgr.setAttribute('height','100%');"
        "bgr.setAttribute('fill',liveBg);"
        "cl.insertBefore(bgr,cl.firstChild);};"
        "var s=new XMLSerializer().serializeToString(cl);"
        "window.parent.postMessage({type:'weave-svg',content:s,w:e.data.width,h:e.data.height},'*');"
        "});"
        "</script>"
    )
    return html.replace("</body>", injected + "</body>")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chart", response_model=ChartResponse)
async def generate_chart(
    file: UploadFile = File(..., description="CSV file to visualize"),
    prompt: str = Form(..., description="Plain-English description of the chart"),
    provider: str | None = Form(default=None),
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

    try:
        validate_csv(csv_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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

        html = _inject(html)

        logger.info("chart_type=%s x=%s y=%s", mapping.chart_type, mapping.x_column, mapping.y_column)
        return ChartResponse(html=html, mapping=mapping.model_dump())

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Pipeline error")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)


@app.post("/refine", response_model=ChartResponse)
async def refine_chart(
    file: UploadFile = File(..., description="Same CSV used for the original chart"),
    mapping: str = Form(..., description="Current AxisMapping as JSON"),
    history: str = Form(default="[]", description="Conversation history as JSON array of {role, content}"),
    instruction: str = Form(..., description="User's refinement instruction"),
    provider: str | None = Form(default=None),
    model: str | None = Form(default=None),
):
    csv_bytes = await file.read()

    try:
        validate_csv(csv_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(csv_bytes)
        tmp_path = tmp.name

    try:
        current_mapping = AxisMapping(**json.loads(mapping))
        history_list: list[dict] = json.loads(history)

        llm_provider = get_provider(provider, model)
        pipeline = Pipeline(llm_provider)

        config = ChartConfig(
            title=current_mapping.title or "",
            x_label=current_mapping.x_label or "",
            y_label=current_mapping.y_label or "",
        )

        html, updated_mapping = pipeline.refine(
            tmp_path, current_mapping, history_list, instruction, config
        )
        html = _inject(html)

        logger.info("refine chart_type=%s instruction=%r", updated_mapping.chart_type, instruction)
        return ChartResponse(html=html, mapping=updated_mapping.model_dump())

    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Refine error")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)


@app.post("/insights", response_model=InsightsResponse)
async def generate_insights(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    prompt: str = Form(default=""),
    provider: str | None = Form(default=None),
    model: str | None = Form(default=None),
):
    csv_bytes = await file.read()

    try:
        validate_csv(csv_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(csv_bytes)
        tmp_path = tmp.name

    try:
        schema, rows = DataLoader().load(tmp_path)
        sample = rows[:30]  # send a sample, not the full dataset

        user_msg = (
            f"User prompt: {prompt}\n\n"
            f"Chart mapping: {mapping}\n\n"
            f"Data sample ({len(sample)} of {len(rows)} rows):\n"
            f"{json.dumps(sample, indent=2)}"
        )

        llm_provider = get_provider(provider, model)
        raw = llm_provider.complete(_INSIGHTS_PROMPT, user_msg)

        # strip markdown fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        # extract just the JSON array in case the model adds surrounding text
        start, end = raw.find("["), raw.rfind("]")
        if start == -1 or end == -1:
            raise ValueError("No JSON array found in response")
        raw = raw[start:end + 1]

        insights = json.loads(raw)
        if not isinstance(insights, list):
            raise ValueError("Expected a JSON array")

        return InsightsResponse(insights=[str(i) for i in insights])

    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=f"Could not parse insights: {e}")
    except Exception as e:
        logger.exception("Insights error")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)


@app.post("/dashboard")
async def generate_dashboard(
    file: UploadFile = File(..., description="CSV file to visualise"),
    prompt: str = Form(..., description="Plain-English description — single chart or multi-chart intent"),
    provider: str | None = Form(default=None),
    model: str | None = Form(default=None),
):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    csv_bytes = await file.read()

    try:
        validate_csv(csv_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(csv_bytes)
        tmp_path = tmp.name

    try:
        llm_provider = get_provider(provider, model)
        schema, _ = DataLoader().load(tmp_path)
        sub_prompts = Decomposer(llm_provider).decompose(prompt, schema)
        pipeline = Pipeline(llm_provider)
        config = ChartConfig()
    except Exception as e:
        os.unlink(tmp_path)
        logger.exception("Dashboard setup error")
        raise HTTPException(status_code=500, detail=str(e))

    async def stream():
        loop = asyncio.get_event_loop()

        async def run_one(index: int, sub_prompt: str) -> dict:
            try:
                html, mapping = await loop.run_in_executor(
                    None, pipeline.run, tmp_path, sub_prompt, config
                )
                return {
                    "ok": True,
                    "index": index,
                    "sub_prompt": sub_prompt,
                    "html": _inject(html),
                    "mapping": mapping.model_dump(),
                }
            except Exception as e:
                logger.exception("Chart %d failed: %s", index, sub_prompt)
                return {"ok": False, "index": index, "sub_prompt": sub_prompt, "detail": str(e)}

        try:
            # tell the client how many charts to expect and their sub-prompts up front
            yield {
                "event": "start",
                "data": json.dumps({"count": len(sub_prompts), "sub_prompts": sub_prompts}),
            }

            tasks = [run_one(i, sp) for i, sp in enumerate(sub_prompts)]
            for coro in asyncio.as_completed(tasks):
                result = await coro
                event = "chart" if result["ok"] else "error"
                yield {"event": event, "data": json.dumps(result)}

            yield {"event": "done", "data": "{}"}
        finally:
            os.unlink(tmp_path)

    return EventSourceResponse(stream())


@app.get("/playground/datasets")
def list_playground_datasets():
    return [
        {k: v for k, v in d.items() if k != "csv"} for d in PLAYGROUND_DATASETS
    ]


@app.get("/playground/csv/{dataset_id}")
def get_playground_csv(dataset_id: str):
    dataset = _DATASET_MAP.get(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    csv_path = os.path.join(_SAMPLES_DIR, dataset["csv"])
    if not os.path.isfile(csv_path):
        raise HTTPException(status_code=404, detail="CSV file not found on server")
    return FileResponse(csv_path, media_type="text/csv", filename=dataset["csv"])


