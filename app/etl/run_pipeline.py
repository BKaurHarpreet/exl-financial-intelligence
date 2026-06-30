from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine
from app.etl.bronze import load_bronze
from app.etl.gold import build_gold
from app.etl.silver import load_silver
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)


def run_pipeline() -> str:
    configure_logging()
    settings = get_settings()
    raw_data_dir = Path(settings.raw_data_dir)
    if not raw_data_dir.exists():
        raise FileNotFoundError(f"Raw data directory not found: {raw_data_dir}")

    run_id = uuid4()
    source_file_count = len(list(raw_data_dir.glob("*.xls")))
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO lineage.pipeline_runs
                    (run_id, status, raw_data_dir, source_file_count)
                VALUES
                    (:run_id, 'running', :raw_data_dir, :source_file_count)
            """),
            {"run_id": run_id, "raw_data_dir": str(raw_data_dir), "source_file_count": source_file_count},
        )
        try:
            bronze_count = load_bronze(connection, run_id, raw_data_dir)
            silver_count = load_silver(connection, run_id)
            gold_count = build_gold(connection, run_id)
            connection.execute(
                text("""
                    UPDATE lineage.pipeline_runs
                    SET status = 'succeeded', finished_at = now(),
                        bronze_cells_loaded = :bronze_count,
                        silver_facts_loaded = :silver_count,
                        gold_rows_loaded = :gold_count,
                        message = 'Pipeline completed'
                    WHERE run_id = :run_id
                """),
                {"run_id": run_id, "bronze_count": bronze_count, "silver_count": silver_count, "gold_count": gold_count},
            )
        except Exception as exc:
            logger.exception("Pipeline failed")
            connection.execute(
                text("""
                    UPDATE lineage.pipeline_runs
                    SET status = 'failed', finished_at = now(), message = :message
                    WHERE run_id = :run_id
                """),
                {"run_id": run_id, "message": str(exc)},
            )
            raise
    logger.info("Pipeline run %s completed", run_id)
    return str(run_id)


if __name__ == "__main__":
    print(run_pipeline())
