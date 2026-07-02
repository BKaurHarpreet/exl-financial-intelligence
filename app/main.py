from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from app.db import fetch_all, initialize_database
from app.etl.run_pipeline import run_pipeline
from app.logging_config import configure_logging
import logging

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    # Ensure the dashboard has data the first time anyone opens it --
    # don't make "click Run ETL" a precondition for seeing the page.
    try:
        existing = fetch_all("SELECT COUNT(*) AS n FROM gold_kpi_trends")
        has_data = existing and existing[0]["n"] > 0
    except SQLAlchemyError:
        has_data = False
    if not has_data:
        logger.info("gold_kpi_trends is empty -- running pipeline once at startup")
        try:
            run_pipeline()
        except Exception:
            logger.exception("Startup pipeline run failed; dashboard will show empty state")
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


@app.get("/health/data")
def health_data() -> dict:
    try:
        rows = fetch_all("SELECT COUNT(*) AS n FROM gold_kpi_trends")
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"kpi_rows": rows[0]["n"] if rows else 0}


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
        SELECT 
            MAX(fiscal_year) AS fiscal_year,
            metric_name, 
            COUNT(DISTINCT fiscal_year) AS observations,
            SUM(numeric_observations) AS numeric_observations,
            SUM(total_value) AS total_value,
            CASE 
                WHEN SUM(numeric_observations) > 0 THEN SUM(total_value) / SUM(numeric_observations)
                ELSE 0 
            END AS average_value,
            MIN(min_value) AS min_value,
            MAX(max_value) AS max_value,
            '' AS source_files
        FROM gold_annual_metric_summary
        GROUP BY metric_name
        ORDER BY observations DESC, metric_name
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


@app.get("/kpis")
def kpis() -> list[dict]:
    return fetch_all("""
        SELECT fiscal_year, metric_name, value, yoy_change_pct, cagr_3yr_pct, insight_text
        FROM gold_kpi_trends
        WHERE metric_name IN ('revenue', 'operating_margin_pct', 'diluted_eps')
        ORDER BY metric_name, fiscal_year
    """)


@app.get("/kpis/latest")
def kpis_latest() -> list[dict]:
    return fetch_all("""
        SELECT g.fiscal_year, g.metric_name, g.value, g.yoy_change_pct, g.cagr_3yr_pct, g.insight_text
        FROM gold_kpi_trends g
        INNER JOIN (
            SELECT metric_name, MAX(fiscal_year) AS max_year
            FROM gold_kpi_trends
            WHERE metric_name IN ('revenue', 'operating_margin_pct', 'diluted_eps')
            GROUP BY metric_name
        ) latest ON g.metric_name = latest.metric_name AND g.fiscal_year = latest.max_year
        WHERE g.metric_name IN ('revenue', 'operating_margin_pct', 'diluted_eps')
    """)