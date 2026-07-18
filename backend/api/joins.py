"""Multi-CSV join endpoints.

Two steps so the user stays in control:
  POST /joins/detect  — upload several CSVs, get the tables + auto-detected join
                        candidates (by value overlap) to confirm.
  POST /joins/execute — upload the same CSVs + a confirmed join plan, get back a
                        single flat CSV that feeds the normal dashboard flow.

Login required (so it's tied to a user), but no LLM call and no quota charge —
those happen when the flat CSV is actually turned into charts.
"""

import json
import os
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from api.auth import current_user_required
from pipeline.csv_validator import validate_csv
from pipeline.multi_csv import (
    JoinPlan, JoinError, detect_all_joins, execute_join, load_tables, suggest_plan, to_csv,
)

router = APIRouter(prefix="/joins", tags=["joins"])

MAX_FILES = 8


async def _to_temp_files(files: list[UploadFile]) -> list[tuple[str, str]]:
    if not files or len(files) < 2:
        raise HTTPException(status_code=400, detail="Upload at least two CSV files to join.")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"At most {MAX_FILES} files can be joined at once.")
    out: list[tuple[str, str]] = []
    for f in files:
        if not f.filename or not f.filename.endswith(".csv"):
            raise HTTPException(status_code=400, detail=f"{f.filename or 'File'} must be a .csv")
        data = await f.read()
        try:
            validate_csv(data)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"{f.filename}: {e}")
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(data)
        out.append((f.filename, path))
    return out


def _cleanup(paths: list[tuple[str, str]]) -> None:
    for _, p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


@router.post("/detect")
async def detect(
    files: list[UploadFile] = File(...),
    user: dict = Depends(current_user_required),
):
    """Load the CSVs and return their tables plus auto-detected join candidates."""
    paths = await _to_temp_files(files)
    try:
        conn, tables = load_tables(paths)
        candidates = detect_all_joins(conn, tables)
        plan, unjoined = suggest_plan(tables, candidates)
        conn.close()
        return {
            "tables": [
                {
                    "name": t.name,
                    "source": t.source,
                    "columns": t.columns,
                    "row_count": t.row_count,
                    "sample": t.sample,
                }
                for t in tables.values()
            ],
            "candidates": [
                {
                    "left_table": c.left_table, "left_col": c.left_col,
                    "right_table": c.right_table, "right_col": c.right_col,
                    "overlap": c.overlap, "confidence": c.confidence,
                    "extra_pairs": [list(p) for p in c.extra_pairs],  # composite keys
                }
                for c in candidates
            ],
            "plan": plan.model_dump(),          # auto-built spanning join
            "unjoined": unjoined,               # tables with no join path
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        _cleanup(paths)


@router.post("/execute")
async def execute(
    files: list[UploadFile] = File(...),
    plan: str = Form(..., description="JoinPlan as JSON"),
    user: dict = Depends(current_user_required),
):
    """Run the confirmed join plan and return one flat CSV."""
    paths = await _to_temp_files(files)
    try:
        conn, tables = load_tables(paths)
        try:
            join_plan = JoinPlan(**json.loads(plan))
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"Invalid join plan: {e}")
        try:
            columns, rows = execute_join(conn, join_plan, tables)
        except JoinError as e:
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            conn.close()
        if not rows:
            raise HTTPException(status_code=400, detail="The join produced no rows.")
        name = f"joined_{len(tables)}_tables.csv"
        return {"name": name, "columns": columns, "row_count": len(rows), "csv": to_csv(columns, rows)}
    finally:
        _cleanup(paths)
