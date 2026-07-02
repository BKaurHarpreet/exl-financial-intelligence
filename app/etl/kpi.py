from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Connection

YEAR_RE = re.compile(r"^(20\d\d)(\.0)?(\(\d+\))?$")

METRIC_DISPLAY = {
    "revenue": "Revenue",
    "operating_income": "Operating income",
    "operating_margin_pct": "Operating margin",
    "diluted_eps": "Diluted EPS",
}


def _parse_number(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    s = raw.strip().replace(",", "")
    if s in {"—", "-", ""}:
        return Decimal("0")
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        val = Decimal(s)
    except Exception:
        return None
    return -val if negative else val


def _extract_income_sheet_kpis(connection: Connection, run_id: str) -> list[dict]:
    workbooks = connection.execute(
        text("""
            SELECT workbook_id, source_file, fiscal_year AS filing_year
            FROM bronze_workbooks
            WHERE run_id = :run_id
        """),
        {"run_id": run_id},
    ).mappings().all()

    facts: list[dict] = []

    for wb in workbooks:
        rows = connection.execute(
            text("""
                SELECT row_number, column_number, normalized_text
                FROM bronze_cells
                WHERE workbook_id = :workbook_id AND sheet_name = 'income'
                ORDER BY row_number, column_number
            """),
            {"workbook_id": wb["workbook_id"]},
        ).mappings().all()
        if not rows:
            continue

        by_row: dict[int, dict[int, str | None]] = {}
        for r in rows:
            by_row.setdefault(r["row_number"], {})[r["column_number"]] = r["normalized_text"]

        # Locate the year-header row: the first row with >=2 cells matching 20xx
        year_columns: dict[int, int] = {}
        for row_num in sorted(by_row):
            cols = by_row[row_num]
            matches = {
                col: int(YEAR_RE.match(val.strip()).group(1))
                for col, val in cols.items()
                if val and YEAR_RE.match(val.strip())
            }
            if len(matches) >= 2:
                year_columns = matches
                break
        if not year_columns:
            continue

        revenue_row = operating_income_row = diluted_eps_row = weighted_avg_row = None
        for row_num in sorted(by_row):
            label = (by_row[row_num].get(1) or "").strip().lower()
            if not label:
                continue
            if revenue_row is None and "revenues, net" in label:
                revenue_row = row_num
            elif operating_income_row is None and "income from operations" in label:
                operating_income_row = row_num
            elif weighted_avg_row is None and "weighted-average" in label:
                weighted_avg_row = row_num
            elif diluted_eps_row is None and label == "diluted":
                diluted_eps_row = row_num

        # "Diluted" appears twice per filing (EPS section, then share-count section).
        # The EPS row always precedes the weighted-average-shares row.
        if diluted_eps_row is not None and weighted_avg_row is not None and diluted_eps_row > weighted_avg_row:
            diluted_eps_row = None

        for metric_name, row_num in (
            ("revenue", revenue_row),
            ("operating_income", operating_income_row),
            ("diluted_eps", diluted_eps_row),
        ):
            if row_num is None:
                continue
            row_cells = by_row.get(row_num, {})
            for col, fiscal_year in year_columns.items():
                value = _parse_number(row_cells.get(col))
                if value is None:
                    continue
                facts.append({
                    "run_id": run_id,
                    "fiscal_year": fiscal_year,
                    "metric_name": metric_name,
                    "value": value,
                    "source_file": wb["source_file"],
                    "filing_year": wb["filing_year"],
                })

    return facts


def _dedupe_prefer_earliest_filing(facts: list[dict]) -> list[dict]:
    """Each fiscal year appears in ~3 filings (as current + 2 comparative years).
    Keep the value from the earliest filing that reported it — i.e. as originally
    filed, not a later restatement (e.g. after a stock split)."""
    best: dict[tuple[int, str], dict] = {}
    for f in facts:
        key = (f["fiscal_year"], f["metric_name"])
        if key not in best or f["filing_year"] < best[key]["filing_year"]:
            best[key] = f
    return list(best.values())


def _insight_text(metric_name: str, fiscal_year: int, yoy: float | None, prior_yoy: float | None) -> tuple[str, str]:
    display = METRIC_DISPLAY[metric_name]
    if yoy is None:
        return "insufficient_data", f"Not enough history to compute a {display} trend for FY{fiscal_year}."
    if yoy > 0 and prior_yoy is not None and yoy > prior_yoy:
        return "accelerating_growth", f"{display} grew {yoy:.1f}% YoY in FY{fiscal_year}, an acceleration from the prior year."
    if yoy > 0:
        return "growth", f"{display} grew {yoy:.1f}% YoY in FY{fiscal_year}."
    if yoy == 0:
        return "flat", f"{display} was flat YoY in FY{fiscal_year}."
    if prior_yoy is not None and yoy < prior_yoy:
        return "accelerating_decline", f"{display} declined {abs(yoy):.1f}% YoY in FY{fiscal_year}, a steeper drop than the prior year."
    return "decline", f"{display} declined {abs(yoy):.1f}% YoY in FY{fiscal_year}."


def _classify_and_insight(rows: list[dict]) -> list[dict]:
    by_metric: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_metric[r["metric_name"]].append(r)

    out = []
    for metric_name, metric_rows in by_metric.items():
        metric_rows.sort(key=lambda r: r["fiscal_year"])
        for i, r in enumerate(metric_rows):
            prior = metric_rows[i - 1] if i >= 1 else None
            prior2 = metric_rows[i - 3] if i >= 3 else None
            yoy = None
            if prior and prior["value"]:
                yoy = float((r["value"] - prior["value"]) / abs(prior["value"]) * 100)
            cagr = None
            if prior2 and prior2["value"] > 0 and r["value"] > 0:
                cagr = float((r["value"] / prior2["value"]) ** (Decimal(1) / Decimal(3)) - 1) * 100
            prior_yoy = None
            if i >= 2 and metric_rows[i - 1]["value"] and metric_rows[i - 2]["value"]:
                prior_yoy = float(
                    (metric_rows[i - 1]["value"] - metric_rows[i - 2]["value"])
                    / abs(metric_rows[i - 2]["value"]) * 100
                )
            trend_label, insight = _insight_text(metric_name, r["fiscal_year"], yoy, prior_yoy)
            out.append({**r, "yoy_change_pct": yoy, "cagr_3yr_pct": cagr,
                        "trend_label": trend_label, "insight_text": insight})
    return out


def _add_operating_margin(deduped: list[dict]) -> list[dict]:
    revenue_by_year = {r["fiscal_year"]: r for r in deduped if r["metric_name"] == "revenue"}
    opinc_by_year = {r["fiscal_year"]: r for r in deduped if r["metric_name"] == "operating_income"}
    margin_rows = []
    for fy, opinc_row in opinc_by_year.items():
        rev_row = revenue_by_year.get(fy)
        if rev_row and rev_row["value"]:
            margin_rows.append({
                "run_id": opinc_row["run_id"],
                "fiscal_year": fy,
                "metric_name": "operating_margin_pct",
                "value": (opinc_row["value"] / rev_row["value"]) * 100,
                "source_file": opinc_row["source_file"],
                "filing_year": opinc_row["filing_year"],
            })
    return deduped + margin_rows


def build_kpi_trends(connection: Connection, run_id: str) -> int:
    raw_facts = _extract_income_sheet_kpis(connection, run_id)
    deduped = _dedupe_prefer_earliest_filing(raw_facts)
    deduped = _add_operating_margin(deduped)
    enriched = _classify_and_insight(deduped)

    if not enriched:
        return 0

    connection.execute(
        text("""
            INSERT INTO gold_kpi_trends
                (run_id, fiscal_year, metric_name, value, source_file,
                 yoy_change_pct, cagr_3yr_pct, trend_label, insight_text)
            VALUES
                (:run_id, :fiscal_year, :metric_name, :value, :source_file,
                 :yoy_change_pct, :cagr_3yr_pct, :trend_label, :insight_text)
        """),
        enriched,
    )
    return len(enriched)