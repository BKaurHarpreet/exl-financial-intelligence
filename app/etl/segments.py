from __future__ import annotations

import re
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Connection

YEAR_RE = re.compile(r"^(20\d\d)(\.0)?(\(\d+\))?$")
GEO_LABELS = {"the united states", "the united kingdom", "rest of world"}
BALANCE_DATE_RE = re.compile(r"december\s*31,?\s*(20\d\d)", re.IGNORECASE)


def _parse_number(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    s = raw.strip().replace(",", "")
    if s in {"\u2014", "-", ""}:
        return Decimal("0")
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        val = Decimal(s)
    except Exception:
        return None
    return -val if negative else val


class SheetGrid:
    """Holds both cell text and cell source_address, keyed [row][col]."""
    def __init__(self, connection: Connection, workbook_id: str, sheet_name: str):
        rows = connection.execute(
            text("""
                SELECT row_number, column_number, normalized_text, source_address
                FROM bronze_cells
                WHERE workbook_id = :workbook_id AND sheet_name = :sheet_name
                ORDER BY row_number, column_number
            """),
            {"workbook_id": workbook_id, "sheet_name": sheet_name},
        ).mappings().all()
        self.text: dict[int, dict[int, str | None]] = {}
        self.addr: dict[int, dict[int, str | None]] = {}
        for r in rows:
            self.text.setdefault(r["row_number"], {})[r["column_number"]] = r["normalized_text"]
            self.addr.setdefault(r["row_number"], {})[r["column_number"]] = r["source_address"]

    def __bool__(self):
        return bool(self.text)

    def __iter__(self):
        return iter(self.text)

    def label(self, row_num: int) -> str:
        return (self.text.get(row_num, {}).get(1) or "").strip()

    def value_text(self, row_num: int, col: int) -> str | None:
        return self.text.get(row_num, {}).get(col)

    def address(self, row_num: int, col: int) -> str | None:
        return self.addr.get(row_num, {}).get(col)


def _find_year_columns(grid: SheetGrid) -> tuple[int | None, dict[int, int]]:
    for row_num in sorted(grid.text):
        cols = grid.text[row_num]
        matches = {
            col: int(YEAR_RE.match(val.strip()).group(1))
            for col, val in cols.items()
            if val and YEAR_RE.match(val.strip())
        }
        if len(matches) >= 2:
            return row_num, matches
    return None, {}


def _find_balance_sheet_year_columns(grid: SheetGrid) -> dict[int, int]:
    for row_num in sorted(grid.text):
        cols = grid.text[row_num]
        matches = {}
        for col, val in cols.items():
            if not val:
                continue
            m = BALANCE_DATE_RE.search(val)
            if m:
                matches[col] = int(m.group(1))
        if len(matches) >= 2:
            return matches
    return {}


def _sheet_names_for_workbook(connection: Connection, workbook_id: str) -> list[str]:
    rows = connection.execute(
        text("SELECT DISTINCT sheet_name FROM bronze_cells WHERE workbook_id = :workbook_id"),
        {"workbook_id": workbook_id},
    ).all()
    return [r[0] for r in rows]


def _workbooks(connection: Connection, run_id: str):
    return connection.execute(
        text("SELECT workbook_id, source_file, fiscal_year AS filing_year FROM bronze_workbooks WHERE run_id = :run_id"),
        {"run_id": run_id},
    ).mappings().all()


def _extract_segment_revenue(connection: Connection, run_id: str) -> list[dict]:
    """Taxonomy-agnostic: detect whichever segment names sit between a
    'Revenues, net:' header and the 'Revenues, net' total row in the MD&A
    revenue note. Does not use a fixed segment-name list, since EXL has
    renamed its segments three times since FY2017."""
    facts: list[dict] = []
    for wb in _workbooks(connection, run_id):
        candidate_sheets = [s for s in _sheet_names_for_workbook(connection, wb["workbook_id"]) if "revenue" in s.lower()]
        for sheet_name in candidate_sheets:
            grid = SheetGrid(connection, wb["workbook_id"], sheet_name)
            header_row, year_columns = _find_year_columns(grid)
            if header_row is None:
                continue

            # The section title ("Revenues.", "Revenues, net:") can appear either
            # before or after the year-header row depending on filing year -- find
            # it independently first, then only look for segment rows and the total
            # after BOTH the title and the year header (that's where real data starts).
            title_row = None
            for row_num in sorted(grid.text):
                label = grid.label(row_num)
                if label and "revenue" in label.lower():
                    title_row = row_num
                    break
            if title_row is None:
                continue
            start_row = max(title_row, header_row)

            total_row = None
            segment_rows: list[tuple[int, str]] = []
            for row_num in sorted(grid.text):
                if row_num <= start_row:
                    continue
                label = grid.label(row_num)
                if not label:
                    continue
                if "revenue" in label.lower():
                    total_row = row_num
                    break
                segment_rows.append((row_num, label))
            header_seen = True

            if not header_seen or total_row is None or not segment_rows:
                continue

            for row_num, segment_name in segment_rows:
                for col, fiscal_year in year_columns.items():
                    value = _parse_number(grid.value_text(row_num, col))
                    if value is None:
                        continue
                    facts.append({
                        "run_id": run_id,
                        "fiscal_year": fiscal_year,
                        "dimension": segment_name,
                        "value": value,
                        "source_file": wb["source_file"],
                        "filing_year": wb["filing_year"],
                        "sheet_name": sheet_name,
                        "source_address": grid.address(row_num, col),
                    })
            break  # first matching sheet with a real segment table is enough
    return facts


def _extract_geography_revenue(connection: Connection, run_id: str) -> list[dict]:
    facts: list[dict] = []
    for wb in _workbooks(connection, run_id):
        for sheet_name in _sheet_names_for_workbook(connection, wb["workbook_id"]):
            grid = SheetGrid(connection, wb["workbook_id"], sheet_name)
            has_us_revenue_row = any(grid.label(r).lower() == "the united states" for r in grid.text)
            if not has_us_revenue_row:
                continue  # 'Rest of World' alone is reused by unrelated tables (e.g. long-lived assets by country)
            header_row, year_columns = _find_year_columns(grid)
            if header_row is None:
                continue
            for row_num in sorted(grid.text):
                label = grid.label(row_num)
                if label.lower() not in GEO_LABELS:
                    continue
                for col, fiscal_year in year_columns.items():
                    value = _parse_number(grid.value_text(row_num, col))
                    if value is None:
                        continue
                    facts.append({
                        "run_id": run_id,
                        "fiscal_year": fiscal_year,
                        "dimension": label,
                        "value": value,
                        "source_file": wb["source_file"],
                        "filing_year": wb["filing_year"],
                        "sheet_name": sheet_name,
                        "source_address": grid.address(row_num, col),
                    })
            break  # first matching sheet is enough
    return facts


def _extract_cash_flow(connection: Connection, run_id: str) -> list[dict]:
    facts: list[dict] = []
    for wb in _workbooks(connection, run_id):
        grid = SheetGrid(connection, wb["workbook_id"], "cash flows")
        if not grid:
            continue
        header_row, year_columns = _find_year_columns(grid)
        if header_row is None:
            continue

        op_row = inv_row = fin_row = None
        for row_num in sorted(grid.text):
            label = grid.label(row_num).lower()
            if not label:
                continue
            if op_row is None and label == "net cash provided by operating activities":
                op_row = row_num
            elif inv_row is None and label == "net cash used for investing activities":
                inv_row = row_num
            elif fin_row is None and label.startswith("net cash") and "financing activities" in label and "reconcile" not in label:
                fin_row = row_num

        for dimension, row_num in (("operating", op_row), ("investing", inv_row), ("financing", fin_row)):
            if row_num is None:
                continue
            for col, fiscal_year in year_columns.items():
                value = _parse_number(grid.value_text(row_num, col))
                if value is None:
                    continue
                facts.append({
                    "run_id": run_id,
                    "fiscal_year": fiscal_year,
                    "dimension": dimension,
                    "value": value,
                    "source_file": wb["source_file"],
                    "filing_year": wb["filing_year"],
                    "sheet_name": "cash flows",
                    "source_address": grid.address(row_num, col),
                })
    return facts


def _dedupe_prefer_earliest_filing(facts: list[dict]) -> list[dict]:
    best: dict[tuple[int, str], dict] = {}
    for f in facts:
        key = (f["fiscal_year"], f["dimension"])
        if key not in best or f["filing_year"] < best[key]["filing_year"]:
            best[key] = f
    return list(best.values())


def _with_yoy(rows: list[dict]) -> list[dict]:
    by_dim: dict[str, list[dict]] = {}
    for r in rows:
        by_dim.setdefault(r["dimension"], []).append(r)
    out = []
    for dim, dim_rows in by_dim.items():
        dim_rows.sort(key=lambda r: r["fiscal_year"])
        for i, r in enumerate(dim_rows):
            prior = dim_rows[i - 1] if i >= 1 else None
            yoy = None
            if prior and prior["value"]:
                yoy = float((r["value"] - prior["value"]) / abs(prior["value"]) * 100)
            out.append({**r, "yoy_change_pct": yoy})
    return out


def _extract_cash_position(connection: Connection, run_id: str) -> list[dict]:
    facts: list[dict] = []
    for wb in _workbooks(connection, run_id):
        grid = SheetGrid(connection, wb["workbook_id"], "consolidated balance sheets")
        if not grid:
            continue
        year_columns = _find_balance_sheet_year_columns(grid)
        if not year_columns:
            continue

        cash_row = sti_row = None
        for row_num in sorted(grid.text):
            label = grid.label(row_num).lower()
            if not label:
                continue
            if cash_row is None and label == "cash and cash equivalents":
                cash_row = row_num
            elif sti_row is None and label == "short-term investments":
                sti_row = row_num

        if cash_row is None:
            continue
        # Balance sheets report "as of" dates -- take the most recent column only.
        latest_col, latest_fy = max(year_columns.items(), key=lambda kv: kv[1])
        cash = _parse_number(grid.value_text(cash_row, latest_col))
        sti = _parse_number(grid.value_text(sti_row, latest_col)) if sti_row else None
        if cash is None:
            continue
        facts.append({
            "run_id": run_id, "fiscal_year": latest_fy,
            "cash_and_equivalents": cash, "short_term_investments": sti or Decimal("0"),
            "source_file": wb["source_file"], "filing_year": wb["filing_year"],
            "source_address": grid.address(cash_row, latest_col),
        })
    return facts


def build_cash_position(connection: Connection, run_id: str) -> int:
    facts = _extract_cash_position(connection, run_id)
    best: dict[int, dict] = {}
    for f in facts:
        if f["fiscal_year"] not in best or f["filing_year"] < best[f["fiscal_year"]]["filing_year"]:
            best[f["fiscal_year"]] = f
    rows = list(best.values())
    if rows:
        connection.execute(text("DELETE FROM gold_cash_position"))
        connection.execute(
            text("""
                INSERT INTO gold_cash_position
                    (run_id, fiscal_year, cash_and_equivalents, short_term_investments, source_file, source_address)
                VALUES (:run_id, :fiscal_year, :cash_and_equivalents, :short_term_investments, :source_file, :source_address)
            """),
            rows,
        )
    return len(rows)


def build_segment_and_geo_trends(connection: Connection, run_id: str) -> tuple[int, int, int]:
    segment_facts = _with_yoy(_dedupe_prefer_earliest_filing(_extract_segment_revenue(connection, run_id)))
    geo_facts = _with_yoy(_dedupe_prefer_earliest_filing(_extract_geography_revenue(connection, run_id)))
    cash_facts = _dedupe_prefer_earliest_filing(_extract_cash_flow(connection, run_id))

    if segment_facts:
        connection.execute(text("DELETE FROM gold_segment_trends"))
        connection.execute(
            text("""
                INSERT INTO gold_segment_trends
                    (run_id, fiscal_year, segment_name, revenue, yoy_change_pct, source_file, sheet_name, source_address)
                VALUES (:run_id, :fiscal_year, :dimension, :value, :yoy_change_pct, :source_file, :sheet_name, :source_address)
            """),
            segment_facts,
        )
    if geo_facts:
        connection.execute(text("DELETE FROM gold_geography_trends"))
        connection.execute(
            text("""
                INSERT INTO gold_geography_trends
                    (run_id, fiscal_year, country, revenue, yoy_change_pct, source_file, sheet_name, source_address)
                VALUES (:run_id, :fiscal_year, :dimension, :value, :yoy_change_pct, :source_file, :sheet_name, :source_address)
            """),
            geo_facts,
        )
    if cash_facts:
        connection.execute(text("DELETE FROM gold_cash_flow_trends"))
        by_year: dict[int, dict] = {}
        for f in cash_facts:
            entry = by_year.setdefault(f["fiscal_year"], {
                "run_id": run_id, "fiscal_year": f["fiscal_year"], "source_file": f["source_file"],
                "op_address": None, "inv_address": None, "fin_address": None,
            })
            entry[f["dimension"]] = f["value"]
            entry[f["dimension"] + "_address"] = f["source_address"] if f["dimension"] != "operating" else f["source_address"]
            if f["dimension"] == "operating":
                entry["op_address"] = f["source_address"]
            elif f["dimension"] == "investing":
                entry["inv_address"] = f["source_address"]
            elif f["dimension"] == "financing":
                entry["fin_address"] = f["source_address"]
        cash_rows = [
            {
                "run_id": v["run_id"], "fiscal_year": v["fiscal_year"], "source_file": v["source_file"],
                "operating": v.get("operating"), "investing": v.get("investing"), "financing": v.get("financing"),
                "source_address": v.get("op_address"),
            }
            for v in by_year.values()
        ]
        connection.execute(
            text("""
                INSERT INTO gold_cash_flow_trends
                    (run_id, fiscal_year, operating, investing, financing, source_file, source_address)
                VALUES (:run_id, :fiscal_year, :operating, :investing, :financing, :source_file, :source_address)
            """),
            cash_rows,
        )
    return len(segment_facts), len(geo_facts), len(cash_facts)
