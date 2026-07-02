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
    with open("app/static/dashboard.html", "r", encoding="utf-8") as handle:
        return handle.read()


@app.get("/lineage", response_class=HTMLResponse)
def lineage_page() -> str:
    with open("app/static/lineage.html", "r", encoding="utf-8") as handle:
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
    key = metric_name.strip().lower()

    kpi_rows = fetch_all("""
        SELECT fiscal_year, metric_name, value, source_file, source_address
        FROM gold_kpi_trends
        WHERE LOWER(metric_name) = LOWER(:key)
          AND (:fiscal_year IS NULL OR fiscal_year = :fiscal_year)
        ORDER BY fiscal_year DESC
    """, {"key": key, "fiscal_year": fiscal_year})
    if kpi_rows:
        return [{"fiscal_year": r["fiscal_year"], "metric_name": r["metric_name"], "value": r["value"],
                  "source_file": r["source_file"], "sheet_name": "income", "source_address": r["source_address"],
                  "cell_id": r["source_address"]} for r in kpi_rows]

    segment_rows = fetch_all("""
        SELECT fiscal_year, segment_name, revenue, source_file, sheet_name, source_address
        FROM gold_segment_trends
        WHERE LOWER(segment_name) = LOWER(:key)
          AND (:fiscal_year IS NULL OR fiscal_year = :fiscal_year)
        ORDER BY fiscal_year DESC
    """, {"key": key, "fiscal_year": fiscal_year})
    if segment_rows:
        return [{"fiscal_year": r["fiscal_year"], "metric_name": r["segment_name"], "value": r["revenue"],
                  "source_file": r["source_file"], "sheet_name": r["sheet_name"], "source_address": r["source_address"],
                  "cell_id": r["source_address"]} for r in segment_rows]

    geo_rows = fetch_all("""
        SELECT fiscal_year, country, revenue, source_file, sheet_name, source_address
        FROM gold_geography_trends
        WHERE LOWER(country) = LOWER(:key) OR LOWER(REPLACE(country, 'The ', '')) = LOWER(:key)
          AND (:fiscal_year IS NULL OR fiscal_year = :fiscal_year)
        ORDER BY fiscal_year DESC
    """, {"key": key, "fiscal_year": fiscal_year})
    if geo_rows:
        return [{"fiscal_year": r["fiscal_year"], "metric_name": r["country"], "value": r["revenue"],
                  "source_file": r["source_file"], "sheet_name": r["sheet_name"], "source_address": r["source_address"],
                  "cell_id": r["source_address"]} for r in geo_rows]

    if key in {"operating", "investing", "financing", "operating_cash_flow", "investing_cash_flow", "financing_cash_flow"}:
        col = key.replace("_cash_flow", "")
        cash_rows = fetch_all(f"""
            SELECT fiscal_year, {col} AS value, source_file, source_address
            FROM gold_cash_flow_trends
            WHERE (:fiscal_year IS NULL OR fiscal_year = :fiscal_year)
            ORDER BY fiscal_year DESC
        """, {"fiscal_year": fiscal_year})
        return [{"fiscal_year": r["fiscal_year"], "metric_name": f"{col}_cash_flow", "value": r["value"],
                  "source_file": r["source_file"], "sheet_name": "cash flows", "source_address": r["source_address"],
                  "cell_id": r["source_address"]} for r in cash_rows]

    return []


@app.get("/dashboard/trends")
def dashboard_trends() -> dict:
    kpi = fetch_all("""
        SELECT fiscal_year, metric_name, value FROM gold_kpi_trends
        WHERE metric_name IN ('revenue', 'operating_margin_pct') ORDER BY metric_name, fiscal_year
    """)
    cash_flow = fetch_all("SELECT fiscal_year, operating, investing, financing FROM gold_cash_flow_trends ORDER BY fiscal_year")
    return {"kpi": kpi, "cash_flow": cash_flow}


@app.get("/dashboard/latest")
def dashboard_latest() -> dict:
    kpi_latest = fetch_all("""
        SELECT g.fiscal_year, g.metric_name, g.value, g.yoy_change_pct, g.insight_text
        FROM gold_kpi_trends g
        INNER JOIN (
            SELECT metric_name, MAX(fiscal_year) AS max_year FROM gold_kpi_trends
            WHERE metric_name IN ('revenue', 'operating_margin_pct', 'diluted_eps')
            GROUP BY metric_name
        ) latest ON g.metric_name = latest.metric_name AND g.fiscal_year = latest.max_year
        WHERE g.metric_name IN ('revenue', 'operating_margin_pct', 'diluted_eps')
    """)
    top_segment = fetch_all("""
        SELECT segment_name, revenue, yoy_change_pct, fiscal_year FROM gold_segment_trends
        WHERE fiscal_year = (SELECT MAX(fiscal_year) FROM gold_segment_trends)
        ORDER BY yoy_change_pct DESC LIMIT 1
    """)
    top_country = fetch_all("""
        SELECT country, revenue, yoy_change_pct, fiscal_year FROM gold_geography_trends
        WHERE fiscal_year = (SELECT MAX(fiscal_year) FROM gold_geography_trends)
          AND yoy_change_pct IS NOT NULL
        ORDER BY yoy_change_pct DESC LIMIT 5
    """)
    latest_fy_row = fetch_all("SELECT MAX(fiscal_year) AS fy FROM gold_kpi_trends")
    geo_fy_row = fetch_all("SELECT MAX(fiscal_year) AS fy FROM gold_geography_trends")
    return {
        "kpi": kpi_latest,
        "top_segment": top_segment[0] if top_segment else None,
        "top_country_candidates": top_country,
        "current_fiscal_year": latest_fy_row[0]["fy"] if latest_fy_row else None,
        "geography_data_year": geo_fy_row[0]["fy"] if geo_fy_row else None,
    }


@app.get("/dashboard/other-figures")
def dashboard_other_figures() -> dict:
    fy_row = fetch_all("SELECT MAX(fiscal_year) AS fy FROM gold_kpi_trends")
    fy = fy_row[0]["fy"] if fy_row else None
    kpi = {r["metric_name"]: r["value"] for r in fetch_all(
        "SELECT metric_name, value FROM gold_kpi_trends WHERE fiscal_year = :fy", {"fy": fy}
    )}
    cash = fetch_all("SELECT operating FROM gold_cash_flow_trends WHERE fiscal_year = :fy", {"fy": fy})
    cash_position = fetch_all(
        "SELECT cash_and_equivalents, short_term_investments FROM gold_cash_position WHERE fiscal_year = :fy", {"fy": fy}
    )
    gross_margin_pct = None
    if kpi.get("revenue") and kpi.get("gross_profit"):
        gross_margin_pct = kpi["gross_profit"] / kpi["revenue"] * 100
    cash_and_investments = None
    if cash_position:
        cash_and_investments = (cash_position[0]["cash_and_equivalents"] or 0) + (cash_position[0]["short_term_investments"] or 0)
    return {
        "fiscal_year": fy,
        "revenue": kpi.get("revenue"),
        "gross_margin_pct": gross_margin_pct,
        "net_income": kpi.get("net_income"),
        "operating_cash_flow": cash[0]["operating"] if cash else None,
        "cash_and_investments": cash_and_investments,
    }


@app.get("/dashboard/notes")
def dashboard_notes(category: str | None = None) -> list[dict]:
    if category:
        return fetch_all(
            "SELECT category, fiscal_year, note_text, source_tag FROM gold_dashboard_notes WHERE category = :category ORDER BY fiscal_year DESC",
            {"category": category},
        )
    return fetch_all("SELECT category, fiscal_year, note_text, source_tag FROM gold_dashboard_notes ORDER BY category, fiscal_year DESC")


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
