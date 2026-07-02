CREATE TABLE IF NOT EXISTS gold_kpi_trends (
    kpi_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES lineage_pipeline_runs(run_id),
    fiscal_year INTEGER NOT NULL,
    metric_name TEXT NOT NULL,
    value NUMERIC NOT NULL,
    source_file TEXT NOT NULL,
    source_address TEXT,
    yoy_change_pct NUMERIC,
    cagr_3yr_pct NUMERIC,
    trend_label TEXT,
    insight_text TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, fiscal_year, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_gold_kpi_metric_year
    ON gold_kpi_trends(metric_name, fiscal_year);