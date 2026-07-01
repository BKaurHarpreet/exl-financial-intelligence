from __future__ import annotations



from sqlalchemy import text
from sqlalchemy.engine import Connection


def build_gold(connection: Connection, run_id: str) -> int:
    connection.execute(
        text(
            """
            INSERT INTO gold_annual_metric_summary
                (run_id, fiscal_year, metric_name, observations, numeric_observations,
                 total_value, average_value, min_value, max_value, source_files)
            SELECT
                run_id,
                fiscal_year,
                metric_name,
                count(*) AS observations,
                count(value_numeric) AS numeric_observations,
                sum(value_numeric) AS total_value,
                avg(value_numeric) AS average_value,
                min(value_numeric) AS min_value,
                max(value_numeric) AS max_value,
                group_concat(DISTINCT source_file) AS source_files
            FROM silver_financial_facts
            WHERE run_id = :run_id
            GROUP BY run_id, fiscal_year, metric_name
            """
        ),
        {"run_id": run_id},
    )

    connection.execute(
        text(
            """
            INSERT INTO gold_data_quality_summary
                (run_id, workbook_count, bronze_cell_count, blank_cell_count,
                 silver_fact_count, numeric_fact_count)
            SELECT
                :run_id,
                (SELECT count(*) FROM bronze_workbooks WHERE run_id = :run_id),
                (SELECT count(*) FROM bronze_cells c JOIN bronze_workbooks w ON w.workbook_id = c.workbook_id WHERE w.run_id = :run_id),
                (SELECT count(*) FROM bronze_cells c JOIN bronze_workbooks w ON w.workbook_id = c.workbook_id WHERE w.run_id = :run_id AND c.is_blank),
                (SELECT count(*) FROM silver_financial_facts WHERE run_id = :run_id),
                (SELECT count(value_numeric) FROM silver_financial_facts WHERE run_id = :run_id)
            """
        ),
        {"run_id": run_id},
    )

    return connection.execute(
        text("SELECT count(*) FROM gold_annual_metric_summary WHERE run_id = :run_id"),
        {"run_id": run_id},
    ).scalar_one()
