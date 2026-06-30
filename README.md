# EXL Financial Intelligence

Production-oriented open-source ETL and API project for preserving EXL Excel filings and transforming them into PostgreSQL Bronze, Silver, and Gold data layers.

## What This Repository Contains

- Original EXL `.xls` filings for 2017-2026 under `data/raw/EXL`
- PostgreSQL schema for Bronze, Silver, Gold, and lineage metadata
- Python ETL that preserves every source cell before normalization
- FastAPI service for health checks, filings, metrics, and lineage
- Simple HTML/CSS/JavaScript frontend
- Docker Compose runtime for local development
- Tests for schema inference, normalization, and SQL generation

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

Then open:

- API: http://localhost:8000/docs
- UI: http://localhost:8000

Run the ETL inside the API container:

```bash
docker compose run --rm api python -m app.etl.run_pipeline
```

Run tests:

```bash
docker compose run --rm api pytest
```

## Data Layers

Bronze preserves raw workbook, worksheet, row, column, cell value, inferred type, and source file metadata.

Silver converts Bronze cells into normalized financial facts with fiscal year, statement section, metric names, periods, numeric values, and source cell references.

Gold aggregates Silver facts into API-ready analytical tables, including annual metric summaries and data quality summaries.

## Lineage

Every Silver and Gold record keeps source workbook, sheet, row, column, and pipeline run identifiers so a reported metric can be traced back to the original Excel filing.

## Raw Data Note

The local commit in this workspace includes the original `.xls` filings. If this repository is populated through the GitHub connector, binary files may need to be pushed from a Git-authenticated shell because the connector only writes UTF-8 text files.
