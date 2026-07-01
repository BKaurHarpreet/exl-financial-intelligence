from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from app.db import fetch_all, initialize_database
from app.etl.run_pipeline import run_pipeline
from app.logging_config import configure_logging

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="EXL Financial Intelligence",
    description="Bronze/Silver/Gold financial ETL and lineage API for EXL Excel filings.",
    version="0.1.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    with open("app/static/index.html", "r", encoding="utf-8") as handle:
        return handle.read()


@app.get("/health")
def health() -> dict:
    try:
        fetch_all("SELECT 1 AS ok")
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ok"}


@app.post("/pipeline/run")
def trigger_pipeline() -> dict:
    return {"run_id": run_pipeline(), "status": "succeeded"}


@app.get("/pipeline/runs")
def pipeline_runs() -> list[dict]:
    return fetch_all("""
        SELECT run_id, started_at, finished_at, status, source_file_count,
               bronze_cells_loaded, silver_facts_loaded, gold_rows_loaded, message
        FROM lineage_pipeline_runs
        ORDER BY started_at DESC
        LIMIT 25
    """)


@app.get("/filings")
def filings() -> list[dict]:
    return fetch_all("""
        SELECT fiscal_year, source_file, file_sha256, file_size_bytes, loaded_at
        FROM bronze_workbooks
        ORDER BY fiscal_year
    """)


@app.get("/metrics")
def metrics(limit: int = 100) -> list[dict]:
    return fetch_all("""
        SELECT fiscal_year, metric_name, observations, numeric_observations,
               total_value, average_value, min_value, max_value, source_files
        FROM gold_annual_metric_summary
        ORDER BY fiscal_year DESC, metric_name
        LIMIT :limit
    """, {"limit": min(limit, 500)})


@app.get("/lineage/{metric_name}")
def metric_lineage(metric_name: str, fiscal_year: int | None = None) -> list[dict]:
    return fetch_all("""
        SELECT fiscal_year, metric_name, value_numeric, value_text, source_file,
               sheet_name, source_address, cell_id
        FROM silver_financial_facts
        WHERE LOWER(metric_name) = LOWER(:metric_name)
          AND (:fiscal_year IS NULL OR fiscal_year = :fiscal_year)
        ORDER BY fiscal_year DESC, source_file, sheet_name, source_address
        LIMIT 250
    """, {"metric_name": metric_name, "fiscal_year": fiscal_year})
