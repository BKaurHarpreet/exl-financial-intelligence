# EXL Financial Intelligence

Production-oriented open-source ETL and API project that turns EXL's SEC filings into a Bronze/Silver/Gold data warehouse, with a financial dashboard and a cell-level lineage explorer on top.

## What This Repository Contains

- Original EXL `.xls` filings for FY2017–FY2026 filing years under `data/raw/EXL`
- SQLite schema for Bronze, Silver, Gold, and lineage metadata (`sql/`)
- Python ETL that preserves every source cell before normalization, then derives KPIs, business-segment revenue, geographic revenue, cash flow, and auto-generated dashboard commentary
- FastAPI service exposing health checks, filings, metrics, dashboard data, and lineage lookups
- A financial dashboard (`/`) and a source-lineage explorer (`/lineage`)
- Docker Compose runtime for local development
- Tests for schema inference, normalization, and SQL generation

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

Then open:

- Dashboard: http://localhost:8000
- Lineage explorer: http://localhost:8000/lineage
- API docs: http://localhost:8000/docs

The ETL pipeline runs automatically on first startup — there's no need to trigger it manually before the dashboard shows data. If you update the code or add new filings, either restart the app (it detects incomplete Gold tables and re-runs automatically) or trigger it directly:

```bash
docker compose run --rm api python -m app.etl.run_pipeline
```

Run tests:

```bash
docker compose run --rm api pytest
```

## Data Layers

**Bronze** preserves raw workbook, worksheet, row, column, cell value, inferred type, and source file metadata in SQL tables. Nothing is discarded or transformed at this stage.

**Silver** converts Bronze cells into normalized financial facts with fiscal year, statement section, metric names, periods, numeric values, and source cell references.

**Gold** aggregates Silver (and in some cases reads Bronze directly, for structural extraction — see below) into API-ready analytical tables:

| Table | Contents |
|---|---|
| `gold_annual_metric_summary` | Original generic per-metric rollups (count/sum/avg/min/max) |
| `gold_data_quality_summary` | Pipeline-level data quality stats |
| `gold_kpi_trends` | Revenue, gross profit, operating income, operating margin %, net income, diluted EPS — with YoY %, 3-year CAGR, trend classification, and auto-generated insight text |
| `gold_segment_trends` | Business-segment revenue by fiscal year, taxonomy-agnostic (detects whichever segment names a filing uses that year, rather than a fixed list — EXL has renamed its segments three times since FY2017) |
| `gold_geography_trends` | Country-level revenue by fiscal year (only disclosed FY2021–FY2024 in the source filings — see Known Data Limitations) |
| `gold_cash_flow_trends` | Operating / investing / financing cash flow by fiscal year |
| `gold_cash_position` | Cash & cash equivalents + short-term investments, latest balance sheet date per filing |
| `gold_dashboard_notes` | Rule-based "Key Insights" and "Data Quality Gap" commentary, regenerated from the current data on every pipeline run — not hand-written text |

Segment, geography, and cash flow extraction (`app/etl/segments.py`) reads directly from Bronze cells rather than Silver, since it needs to detect structural boundaries (e.g., where a segment-revenue table starts and ends) that Silver's generic label-based extraction doesn't preserve.

## Frontend

- **`/`** — the financial dashboard: revenue/cash flow/profitability trends (Part 1), a latest-fiscal-year snapshot with fresh/stale disclosure badges (Part 2), auto-generated Key Insights and Data Quality Gap sections, and a collapsed debug panel with pipeline run history and a manual re-run button.
- **`/lineage`** — pick any metric, business segment, or country from a dropdown (populated live from whatever's actually in the database) to see the exact filing, sheet, and cell address behind that number.

Both pages call the API directly via `fetch()` and only work when served by the running app (not when opened as standalone files), since they have no data of their own.

## API

| Endpoint | Purpose |
|---|---|
| `GET /health`, `GET /health/data` | Liveness and Gold-table readiness checks |
| `POST /pipeline/run` | Manually trigger a full pipeline run |
| `GET /pipeline/runs` | Pipeline run history |
| `GET /filings` | Bronze workbook metadata |
| `GET /metrics` | Legacy generic metric rollup |
| `GET /kpis`, `GET /kpis/latest` | Core KPI trend data (superseded by `/dashboard/*` for the UI, kept for API compatibility) |
| `GET /dashboard/trends` | Revenue, operating margin, and cash flow series for the trend charts |
| `GET /dashboard/latest` | Latest-fiscal-year KPI snapshot, top-growing segment, top-growing country candidates |
| `GET /dashboard/other-figures` | Gross margin, net income, operating cash flow, cash & investments for the latest year |
| `GET /dashboard/notes?category=insight\|data_quality` | Auto-generated dashboard commentary |
| `GET /lineage/options` | Distinct metric/segment/country/cash-flow-line names currently in the Gold tables, for the lineage page's dropdown |
| `GET /lineage/{name}` | Source file, sheet, and cell address for every fiscal year a given metric/segment/country was reported |

## Lineage

Every Gold-layer fact carries a `source_address` (e.g. `income!J6`, `revenues net!D7`) pointing back to the exact Bronze cell it came from, plus the source filing and sheet name. `GET /lineage/{name}` and the `/lineage` page surface this directly — any number on the dashboard can be traced back to its original Excel cell.

## Database

The default runtime uses SQLite at `data/exl_financial_intelligence.db`. `app/db.py`'s `initialize_database()` runs every file in `sql/` on startup (each using `CREATE TABLE IF NOT EXISTS`) and then applies a small explicit column migration list for columns added after a table's first release — `CREATE TABLE IF NOT EXISTS` is a no-op against a table that already exists, so a plain schema-file change alone won't add a new column to an existing deployment's database without that migration step.

If you're rebuilding from scratch or hit a schema-related error after pulling changes, it's always safe to delete `data/exl_financial_intelligence.db` — everything in it is derived from the Excel filings in `data/raw/EXL` and will be rebuilt automatically on next startup.

## Known Data Limitations

These are properties of what EXL discloses in its 10-K filings, not gaps in the ETL:

- **No FY2026 data exists.** A 10-K reports the *prior* completed fiscal year — the `2026.xls` filing's most recent column is FY2025. FY2026 won't exist until EXL files its next 10-K in 2027.
- **Segment names have changed three times since FY2017** (6 verticals → 4 verticals → the current 4-segment structure introduced in FY2025). Segment-level comparisons across these boundaries use different category definitions.
- **Geographic revenue disclosure was discontinued after FY2024.** FY2025 onward has no U.S./U.K./Rest-of-World breakdown in the filing.
- **No qualitative risk-factor or MD&A narrative text is in this data source.** The Excel filings contain only Part II Item 8 (Financial Statements and Notes); EXL's actual Item 1A Risk Factors and Item 7 MD&A prose would require a separate ingestion path (e.g. SEC EDGAR full-text search) not currently built.
- **Diluted EPS has a large discontinuity around FY2022–FY2023** from a 3-for-1 stock split, not an operating decline — the dashboard flags this in Data Quality Gap rather than reporting it as a raw YoY change.

## Housekeeping

- `app/static/index.html` and `app/parse.py` are earlier/unused artifacts no longer wired into the app (the dashboard now lives at `app/static/dashboard.html`, served at `/`). Safe to remove once you've confirmed you don't need them for reference.
- `scratch/` contains ad-hoc inspection scripts, not part of the pipeline.

## Raw Data Note

The local commit in this workspace includes the original `.xls` filings. If this repository is populated through the GitHub connector, binary files may need to be pushed from a Git-authenticated shell because the connector only writes UTF-8 text files.
