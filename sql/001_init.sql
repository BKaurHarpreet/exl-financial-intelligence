CREATE TABLE IF NOT EXISTS lineage_pipeline_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    status TEXT NOT NULL,
    raw_data_dir TEXT NOT NULL,
    source_file_count INTEGER NOT NULL DEFAULT 0,
    bronze_cells_loaded INTEGER NOT NULL DEFAULT 0,
    silver_facts_loaded INTEGER NOT NULL DEFAULT 0,
    gold_rows_loaded INTEGER NOT NULL DEFAULT 0,
    message TEXT
);

CREATE TABLE IF NOT EXISTS bronze_workbooks (
    workbook_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES lineage_pipeline_runs(run_id),
    source_file TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    file_sha256 TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    loaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, source_file)
);

CREATE TABLE IF NOT EXISTS bronze_cells (
    cell_id INTEGER PRIMARY KEY AUTOINCREMENT,
    workbook_id INTEGER NOT NULL REFERENCES bronze_workbooks(workbook_id) ON DELETE CASCADE,
    sheet_name TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    column_number INTEGER NOT NULL,
    column_label TEXT NOT NULL,
    raw_value TEXT,
    normalized_text TEXT,
    inferred_type TEXT NOT NULL,
    is_blank INTEGER NOT NULL DEFAULT 0,
    source_address TEXT NOT NULL,
    UNIQUE (workbook_id, sheet_name, row_number, column_number)
);

CREATE TABLE IF NOT EXISTS silver_financial_facts (
    fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES lineage_pipeline_runs(run_id),
    cell_id INTEGER NOT NULL REFERENCES bronze_cells(cell_id),
    fiscal_year INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    sheet_name TEXT NOT NULL,
    statement_section TEXT,
    metric_name TEXT NOT NULL,
    period_label TEXT,
    value_numeric NUMERIC,
    value_text TEXT,
    unit TEXT,
    source_address TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, cell_id)
);

CREATE TABLE IF NOT EXISTS gold_annual_metric_summary (
    summary_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES lineage_pipeline_runs(run_id),
    fiscal_year INTEGER NOT NULL,
    metric_name TEXT NOT NULL,
    observations INTEGER NOT NULL,
    numeric_observations INTEGER NOT NULL,
    total_value NUMERIC,
    average_value NUMERIC,
    min_value NUMERIC,
    max_value NUMERIC,
    source_files TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, fiscal_year, metric_name)
);

CREATE TABLE IF NOT EXISTS gold_data_quality_summary (
    run_id TEXT PRIMARY KEY REFERENCES lineage_pipeline_runs(run_id),
    workbook_count INTEGER NOT NULL,
    bronze_cell_count INTEGER NOT NULL,
    blank_cell_count INTEGER NOT NULL,
    silver_fact_count INTEGER NOT NULL,
    numeric_fact_count INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_bronze_cells_workbook_sheet ON bronze_cells(workbook_id, sheet_name);
CREATE INDEX IF NOT EXISTS idx_silver_facts_metric_year ON silver_financial_facts(metric_name, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_gold_metric_year ON gold_annual_metric_summary(metric_name, fiscal_year);
