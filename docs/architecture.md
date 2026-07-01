# Architecture

## Runtime

The local runtime uses Docker Compose:

- `api`: FastAPI application, ETL runner, static HTML frontend, and tests
- `db`: SQLite database at `data/exl_financial_intelligence.db`

## Data Flow

1. Source `.xls` filings are stored unchanged in `data/raw/EXL`.
2. Bronze reads every workbook sheet and stores every cell with source coordinates.
3. Silver derives numeric financial facts by pairing row labels with numeric cells.
4. Gold aggregates facts into annual metric summaries and data quality summaries.
5. FastAPI exposes health, pipeline, filings, metrics, and lineage endpoints.

## Lineage Contract

Every fact keeps:

- pipeline `run_id`
- source file
- fiscal year
- sheet name
- Excel-style cell address
- Bronze `cell_id`

This makes every API metric traceable to the original workbook cell.
