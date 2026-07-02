-- =====================================================================
-- GOLD LAYER: KPI Trends & Insights
-- Assumes a Silver-layer fact table shaped like:
--   silver_financial_facts(fiscal_year INT, metric_name TEXT, value NUMERIC)
-- Adjust table/column names to match your actual Silver schema.
--
-- Covers 3 KPIs: Revenue, Operating Margin %, Diluted EPS
-- Swap metric_name filters below to match how they're labeled in your data.
-- =====================================================================

-- ---------------------------------------------------------------------
-- STEP 1: Pull the 3 target KPIs into a clean, year-indexed view
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS gold_kpi_base; CREATE VIEW gold_kpi_base AS
SELECT
    fiscal_year,
    metric_name,
    value
FROM silver_financial_facts_dedup
WHERE metric_name IN ('revenue', 'operating_margin_pct', 'diluted_eps');


-- ---------------------------------------------------------------------
-- STEP 2: Compute YoY % change and rolling 3-yr CAGR per metric
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS gold_kpi_trends; CREATE VIEW gold_kpi_trends AS
WITH ordered AS (
    SELECT
        metric_name,
        fiscal_year,
        value,
        LAG(value) OVER (PARTITION BY metric_name ORDER BY fiscal_year) AS prior_year_value,
        LAG(value, 3) OVER (PARTITION BY metric_name ORDER BY fiscal_year) AS value_3yr_ago
    FROM gold_kpi_base
)
SELECT
    metric_name,
    fiscal_year,
    value,
    prior_year_value,
    ROUND(
        CASE
            WHEN prior_year_value IS NULL OR prior_year_value = 0 THEN NULL
            ELSE ((value - prior_year_value) / ABS(prior_year_value)) * 100
        END, 2
    ) AS yoy_change_pct,
    ROUND(
        CASE
            WHEN value_3yr_ago IS NULL OR value_3yr_ago <= 0 OR value <= 0 THEN NULL
            ELSE (POWER(value / value_3yr_ago, 1.0 / 3) - 1) * 100
        END, 2
    ) AS cagr_3yr_pct
FROM ordered
ORDER BY metric_name, fiscal_year;


-- ---------------------------------------------------------------------
-- STEP 3: Rule-based insight text generation (no LLM needed)
-- Compares current YoY vs. prior YoY to classify trend direction,
-- then renders a human-readable sentence.
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS gold_kpi_insights; CREATE VIEW gold_kpi_insights AS
WITH trend_with_prior_yoy AS (
    SELECT
        *,
        LAG(yoy_change_pct) OVER (PARTITION BY metric_name ORDER BY fiscal_year) AS prior_yoy_change_pct
    FROM gold_kpi_trends
),
classified AS (
    SELECT
        *,
        CASE
            WHEN yoy_change_pct IS NULL THEN 'insufficient_data'
            WHEN yoy_change_pct > 0 AND prior_yoy_change_pct IS NOT NULL
                 AND yoy_change_pct > prior_yoy_change_pct THEN 'accelerating_growth'
            WHEN yoy_change_pct > 0 THEN 'growth'
            WHEN yoy_change_pct = 0 THEN 'flat'
            WHEN yoy_change_pct < 0 AND prior_yoy_change_pct IS NOT NULL
                 AND yoy_change_pct < prior_yoy_change_pct THEN 'accelerating_decline'
            ELSE 'decline'
        END AS trend_label
    FROM trend_with_prior_yoy
)
SELECT
    metric_name,
    fiscal_year,
    value,
    yoy_change_pct,
    cagr_3yr_pct,
    trend_label,
    CASE trend_label
        WHEN 'accelerating_growth' THEN
            metric_name || ' grew ' || yoy_change_pct || '% YoY in FY' || fiscal_year ||
            ', the fastest pace in recent years.'
        WHEN 'growth' THEN
            metric_name || ' grew ' || yoy_change_pct || '% YoY in FY' || fiscal_year || '.'
        WHEN 'flat' THEN
            metric_name || ' was flat YoY in FY' || fiscal_year || '.'
        WHEN 'accelerating_decline' THEN
            metric_name || ' declined ' || ABS(yoy_change_pct) || '% YoY in FY' || fiscal_year ||
            ', a steeper drop than the prior year.'
        WHEN 'decline' THEN
            metric_name || ' declined ' || ABS(yoy_change_pct) || '% YoY in FY' || fiscal_year || '.'
        ELSE
            'Not enough historical data to compute a trend for ' || metric_name || ' in FY' || fiscal_year || '.'
    END AS insight_text
FROM classified
ORDER BY metric_name, fiscal_year;


-- ---------------------------------------------------------------------
-- STEP 4 (SQLite-safe): latest year per metric
DROP VIEW IF EXISTS gold_kpi_latest_summary;
CREATE VIEW gold_kpi_latest_summary AS
SELECT g.*
FROM gold_kpi_insights g
INNER JOIN (
    SELECT metric_name, MAX(fiscal_year) AS max_year
    FROM gold_kpi_insights
    GROUP BY metric_name
) latest
ON g.metric_name = latest.metric_name AND g.fiscal_year = latest.max_year;
