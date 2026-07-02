CREATE TABLE IF NOT EXISTS gold_segment_trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES lineage_pipeline_runs(run_id),
    fiscal_year INTEGER NOT NULL,
    segment_name TEXT NOT NULL,
    revenue NUMERIC NOT NULL,
    yoy_change_pct NUMERIC,
    source_file TEXT NOT NULL,
    sheet_name TEXT,
    source_address TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, fiscal_year, segment_name)
);
CREATE INDEX IF NOT EXISTS idx_gold_segment_year ON gold_segment_trends(fiscal_year);

CREATE TABLE IF NOT EXISTS gold_geography_trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES lineage_pipeline_runs(run_id),
    fiscal_year INTEGER NOT NULL,
    country TEXT NOT NULL,
    revenue NUMERIC NOT NULL,
    yoy_change_pct NUMERIC,
    source_file TEXT NOT NULL,
    sheet_name TEXT,
    source_address TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, fiscal_year, country)
);
CREATE INDEX IF NOT EXISTS idx_gold_geo_year ON gold_geography_trends(fiscal_year);

CREATE TABLE IF NOT EXISTS gold_cash_flow_trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES lineage_pipeline_runs(run_id),
    fiscal_year INTEGER NOT NULL,
    operating NUMERIC,
    investing NUMERIC,
    financing NUMERIC,
    source_file TEXT NOT NULL,
    source_address TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, fiscal_year)
);
CREATE INDEX IF NOT EXISTS idx_gold_cashflow_year ON gold_cash_flow_trends(fiscal_year);

CREATE TABLE IF NOT EXISTS gold_cash_position (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES lineage_pipeline_runs(run_id),
    fiscal_year INTEGER NOT NULL,
    cash_and_equivalents NUMERIC,
    short_term_investments NUMERIC,
    source_file TEXT NOT NULL,
    source_address TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, fiscal_year)
);

CREATE TABLE IF NOT EXISTS gold_dashboard_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES lineage_pipeline_runs(run_id),
    category TEXT NOT NULL CHECK (category IN ('insight', 'data_quality')),
    fiscal_year INTEGER,
    note_text TEXT NOT NULL,
    source_tag TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_gold_notes_category ON gold_dashboard_notes(category);
