CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS lineage;

CREATE TABLE IF NOT EXISTS lineage.pipeline_runs (
    run_id UUID PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    raw_data_dir TEXT NOT NULL,
    source_file_count INTEGER NOT NULL DEFAULT 0,
    bronze_cells_loaded INTEGER NOT NULL DEFAULT 0,
    silver_facts_loaded INTEGER NOT NULL DEFAULT 0,
    gold_rows_loaded INTEGER NOT NULL DEFAULT 0,
    message TEXT
);

CREATE TABLE IF NOT EXISTS bronze.workbooks (
    workbook_id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES lineage.pipeline_runs(run_id),
    source_file TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    file_sha256 TEXT NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, source_file)
);

CREATE TABLE IF NOT EXISTS bronze.cells (
    cell_id BIGSERIAL PRIMARY KEY,
    workbook_id BIGINT NOT NULL REFERENCES bronze.workbooks(workbook_id) ON DELETE CASCADE,
    sheet_name TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    column_number INTEGER NOT NULL,
    column_label TEXT NOT NULL,
    raw_value TEXT,
    normalized_text TEXT,
    inferred_type TEXT NOT NULL,
    is_blank BOOLEAN NOT NULL DEFAULT false,
    source_address TEXT NOT NULL,
    UNIQUE (workbook_id, sheet_name, row_number, column_number)
);

CREATE TABLE IF NOT EXISTS silver.financial_facts (
    fact_id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES lineage.pipeline_runs(run_id),
    cell_id BIGINT NOT NULL REFERENCES bronze.cells(cell_id),
    fiscal_year INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    sheet_name TEXT NOT NULL,
    statement_section TEXT,
    metric_name TEXT NOT NULL,
    period_label TEXT,
    value_numeric NUMERIC(22, 6),
    value_text TEXT,
    unit TEXT,
    source_address TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, cell_id)
);

CREATE TABLE IF NOT EXISTS gold.annual_metric_summary (
    summary_id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES lineage.pipeline_runs(run_id),
    fiscal_year INTEGER NOT NULL,
    metric_name TEXT NOT NULL,
    observations INTEGER NOT NULL,
    numeric_observations INTEGER NOT NULL,
    total_value NUMERIC(28, 6),
    average_value NUMERIC(28, 6),
    min_value NUMERIC(28, 6),
    max_value NUMERIC(28, 6),
    source_files TEXT[] NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, fiscal_year, metric_name)
);

CREATE TABLE IF NOT EXISTS gold.data_quality_summary (
    run_id UUID PRIMARY KEY REFERENCES lineage.pipeline_runs(run_id),
    workbook_count INTEGER NOT NULL,
    bronze_cell_count INTEGER NOT NULL,
    blank_cell_count INTEGER NOT NULL,
    silver_fact_count INTEGER NOT NULL,
    numeric_fact_count INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bronze_cells_workbook_sheet ON bronze.cells(workbook_id, sheet_name);
CREATE INDEX IF NOT EXISTS idx_silver_facts_metric_year ON silver.financial_facts(metric_name, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_gold_metric_year ON gold.annual_metric_summary(metric_name, fiscal_year);
