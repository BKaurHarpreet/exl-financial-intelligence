from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Iterable
from uuid import UUID

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.etl.types import RawCell, fiscal_year_from_path, infer_type, normalize_text

logger = logging.getLogger(__name__)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def excel_column_label(column_number: int) -> str:
    label = ""
    number = column_number
    while number:
        number, remainder = divmod(number - 1, 26)
        label = chr(65 + remainder) + label
    return label


def iter_workbook_cells(path: Path) -> Iterable[RawCell]:
    fiscal_year = fiscal_year_from_path(path)
    workbook = pd.ExcelFile(path, engine="xlrd")
    for sheet_name in workbook.sheet_names:
        frame = pd.read_excel(path, sheet_name=sheet_name, header=None, dtype=object, engine="xlrd")
        for row_index, row in frame.iterrows():
            for col_index, value in enumerate(row.tolist()):
                column_number = col_index + 1
                row_number = row_index + 1
                normalized = normalize_text(value)
                yield RawCell(
                    source_file=path.name,
                    fiscal_year=fiscal_year,
                    sheet_name=sheet_name,
                    row_number=row_number,
                    column_number=column_number,
                    column_label=excel_column_label(column_number),
                    raw_value=None if normalized is None else str(value),
                    normalized_text=normalized,
                    inferred_type=infer_type(value),
                    is_blank=normalized is None,
                    source_address=f"{sheet_name}!{excel_column_label(column_number)}{row_number}",
                )


def load_bronze(connection: Connection, run_id: UUID, raw_data_dir: Path) -> int:
    total_cells = 0
    for path in sorted(raw_data_dir.glob("*.xls")):
        logger.info("Loading bronze workbook %s", path.name)
        workbook_id = connection.execute(
            text(
                """
                INSERT INTO bronze.workbooks
                    (run_id, source_file, fiscal_year, file_sha256, file_size_bytes)
                VALUES
                    (:run_id, :source_file, :fiscal_year, :file_sha256, :file_size_bytes)
                RETURNING workbook_id
                """
            ),
            {
                "run_id": run_id,
                "source_file": path.name,
                "fiscal_year": fiscal_year_from_path(path),
                "file_sha256": file_sha256(path),
                "file_size_bytes": path.stat().st_size,
            },
        ).scalar_one()

        batch = []
        for cell in iter_workbook_cells(path):
            batch.append(
                {
                    "workbook_id": workbook_id,
                    "sheet_name": cell.sheet_name,
                    "row_number": cell.row_number,
                    "column_number": cell.column_number,
                    "column_label": cell.column_label,
                    "raw_value": cell.raw_value,
                    "normalized_text": cell.normalized_text,
                    "inferred_type": cell.inferred_type,
                    "is_blank": cell.is_blank,
                    "source_address": cell.source_address,
                }
            )
            if len(batch) >= 5000:
                connection.execute(_insert_cells_sql(), batch)
                total_cells += len(batch)
                batch.clear()
        if batch:
            connection.execute(_insert_cells_sql(), batch)
            total_cells += len(batch)
    return total_cells


def _insert_cells_sql():
    return text(
        """
        INSERT INTO bronze.cells
            (workbook_id, sheet_name, row_number, column_number, column_label,
             raw_value, normalized_text, inferred_type, is_blank, source_address)
        VALUES
            (:workbook_id, :sheet_name, :row_number, :column_number, :column_label,
             :raw_value, :normalized_text, :inferred_type, :is_blank, :source_address)
        """
    )
