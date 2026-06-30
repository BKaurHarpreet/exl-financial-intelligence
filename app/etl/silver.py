from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.etl.transform import infer_unit
from app.etl.types import clean_metric_name, parse_decimal


def load_silver(connection: Connection, run_id: UUID) -> int:
    rows = connection.execute(
        text(
            """
            SELECT c.cell_id, w.fiscal_year, w.source_file, c.sheet_name,
                   c.row_number, c.column_number, c.normalized_text, c.source_address,
                   label.normalized_text AS metric_label,
                   header.normalized_text AS period_label
            FROM bronze.cells c
            JOIN bronze.workbooks w ON w.workbook_id = c.workbook_id
            LEFT JOIN bronze.cells label
                ON label.workbook_id = c.workbook_id
               AND label.sheet_name = c.sheet_name
               AND label.row_number = c.row_number
               AND label.column_number = 1
            LEFT JOIN bronze.cells header
                ON header.workbook_id = c.workbook_id
               AND header.sheet_name = c.sheet_name
               AND header.row_number = 1
               AND header.column_number = c.column_number
            WHERE w.run_id = :run_id
              AND c.inferred_type = 'number'
              AND c.column_number > 1
              AND label.normalized_text IS NOT NULL
            ORDER BY w.fiscal_year, c.sheet_name, c.row_number, c.column_number
            """
        ),
        {"run_id": run_id},
    ).mappings()

    payload = []
    for row in rows:
        numeric_value = parse_decimal(row["normalized_text"])
        if numeric_value is None:
            continue
        payload.append(
            {
                "run_id": run_id,
                "cell_id": row["cell_id"],
                "fiscal_year": row["fiscal_year"],
                "source_file": row["source_file"],
                "sheet_name": row["sheet_name"],
                "statement_section": row["sheet_name"],
                "metric_name": clean_metric_name(row["metric_label"]),
                "period_label": row["period_label"],
                "value_numeric": Decimal(numeric_value),
                "value_text": row["normalized_text"],
                "unit": infer_unit(row["metric_label"], row["period_label"]),
                "source_address": row["source_address"],
            }
        )

    if payload:
        connection.execute(
            text(
                """
                INSERT INTO silver.financial_facts
                    (run_id, cell_id, fiscal_year, source_file, sheet_name,
                     statement_section, metric_name, period_label, value_numeric,
                     value_text, unit, source_address)
                VALUES
                    (:run_id, :cell_id, :fiscal_year, :source_file, :sheet_name,
                     :statement_section, :metric_name, :period_label, :value_numeric,
                     :value_text, :unit, :source_address)
                """
            ),
            payload,
        )
    return len(payload)
