from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection


def _latest_fiscal_year(connection: Connection) -> int | None:
    row = connection.execute(text("SELECT MAX(fiscal_year) AS fy FROM gold_kpi_trends")).mappings().first()
    return row["fy"] if row and row["fy"] is not None else None


def _cash_flow_notes(connection: Connection, run_id: str, latest_fy: int) -> list[dict]:
    rows = connection.execute(
        text("""
            SELECT fiscal_year, operating, financing
            FROM gold_cash_flow_trends
            WHERE fiscal_year IN (:fy, :prior_fy)
            ORDER BY fiscal_year
        """),
        {"fy": latest_fy, "prior_fy": latest_fy - 1},
    ).mappings().all()
    by_year = {r["fiscal_year"]: r for r in rows}
    cur, prior = by_year.get(latest_fy), by_year.get(latest_fy - 1)
    if not cur or not prior or not prior["financing"] or not prior["operating"]:
        return []

    fin_yoy = abs(cur["financing"] - prior["financing"]) / abs(prior["financing"]) * 100
    op_yoy = (cur["operating"] - prior["operating"]) / abs(prior["operating"]) * 100

    if fin_yoy < 50:
        return []

    fin_cur_m = abs(cur["financing"]) / 1000
    fin_prior_m = abs(prior["financing"]) / 1000

    return [{
        "run_id": run_id, "category": "insight", "fiscal_year": latest_fy,
        "note_text": (
            f"Financing cash outflow changed {fin_yoy:.0f}% YoY to ${fin_cur_m:,.1f}M in "
            f"FY{latest_fy} (from ${fin_prior_m:,.1f}M in FY{latest_fy - 1}), while operating "
            f"cash flow grew {op_yoy:.1f}% — worth understanding whether this reflects capital return "
            f"funded by stronger core cash generation, or a response to reduced reinvestment opportunity, "
            f"since the filing doesn't break out the driver."
        ),
        "source_tag": f"derived from cash flow statement, FY{latest_fy - 1} vs FY{latest_fy}",
    }]


def _segment_growth_notes(connection: Connection, run_id: str, latest_fy: int) -> list[dict]:
    rows = connection.execute(
        text("""
            SELECT segment_name, revenue, yoy_change_pct
            FROM gold_segment_trends
            WHERE fiscal_year = :fy AND yoy_change_pct IS NOT NULL
            ORDER BY yoy_change_pct DESC
        """),
        {"fy": latest_fy},
    ).mappings().all()
    if len(rows) < 2:
        return []

    fastest = rows[0]
    largest = max(rows, key=lambda r: r["revenue"])
    if fastest["segment_name"] == largest["segment_name"]:
        return []  # not a meaningful "shifting growth center" story if the same segment leads both

    return [{
        "run_id": run_id, "category": "insight", "fiscal_year": latest_fy,
        "note_text": (
            f"{fastest['segment_name']} is the segment to watch: its FY{latest_fy} growth rate "
            f"({fastest['yoy_change_pct']:.1f}% YoY) is well ahead of {largest['segment_name']}'s "
            f"({largest['yoy_change_pct']:.1f}% YoY), the largest segment by revenue — a sign the growth "
            f"center of the business may be shifting."
        ),
        "source_tag": f"segment revenue growth, FY{latest_fy}",
    }]


def _concentration_notes(connection: Connection, run_id: str, latest_fy: int) -> list[dict]:
    row = connection.execute(
        text("SELECT MAX(fiscal_year) AS fy FROM gold_geography_trends WHERE fiscal_year <= :latest_fy"),
        {"latest_fy": latest_fy},
    ).mappings().first()
    geo_fy = row["fy"] if row else None
    if geo_fy is None:
        return []

    rows = connection.execute(
        text("SELECT country, revenue FROM gold_geography_trends WHERE fiscal_year = :fy"),
        {"fy": geo_fy},
    ).mappings().all()
    if not rows:
        return []
    total = sum(r["revenue"] for r in rows)
    if not total:
        return []
    top = max(rows, key=lambda r: r["revenue"])
    share = top["revenue"] / total * 100

    return [{
        "run_id": run_id, "category": "insight", "fiscal_year": geo_fy,
        "note_text": (
            f"Revenue remains concentrated in a single country: as of the last disclosed breakdown "
            f"(FY{geo_fy}), {top['country'].replace('The ', '')} represented {share:.1f}% of total revenue."
        ),
        "source_tag": f"concentration risk, last known figures FY{geo_fy}",
    }]


def _segment_taxonomy_change_notes(connection: Connection, run_id: str, latest_fy: int) -> list[dict]:
    rows = connection.execute(
        text("""
            SELECT DISTINCT fiscal_year, segment_name FROM gold_segment_trends
            WHERE fiscal_year IN (:fy, :prior_fy)
        """),
        {"fy": latest_fy, "prior_fy": latest_fy - 1},
    ).mappings().all()
    cur_set = {r["segment_name"] for r in rows if r["fiscal_year"] == latest_fy}
    prior_set = {r["segment_name"] for r in rows if r["fiscal_year"] == latest_fy - 1}
    if not cur_set or not prior_set or cur_set == prior_set:
        return []

    new_names = cur_set - prior_set
    dropped_names = prior_set - cur_set
    return [{
        "run_id": run_id, "category": "data_quality", "fiscal_year": latest_fy,
        "note_text": (
            f"Segment names changed between FY{latest_fy - 1} and FY{latest_fy}. "
            f"New: {', '.join(sorted(new_names)) or 'none'}. Dropped: {', '.join(sorted(dropped_names)) or 'none'}. "
            f"Segment-level comparisons across this boundary use different category definitions and "
            f"aren't strictly apples-to-apples."
        ),
        "source_tag": f"filing structure change, FY{latest_fy - 1}→FY{latest_fy}",
    }]


def _geography_disclosure_gap_notes(connection: Connection, run_id: str, latest_fy: int) -> list[dict]:
    cur = connection.execute(
        text("SELECT COUNT(*) AS n FROM gold_geography_trends WHERE fiscal_year = :fy"),
        {"fy": latest_fy},
    ).mappings().first()
    prior = connection.execute(
        text("SELECT COUNT(*) AS n FROM gold_geography_trends WHERE fiscal_year = :fy"),
        {"fy": latest_fy - 1},
    ).mappings().first()
    if cur["n"] > 0 or prior["n"] == 0:
        return []  # either still disclosed, or never was -- nothing new to flag

    return [{
        "run_id": run_id, "category": "data_quality", "fiscal_year": latest_fy,
        "note_text": (
            f"Geographic revenue disclosure was discontinued after FY{latest_fy - 1} — the FY{latest_fy} "
            f"filing contains no country-level revenue split, so geographic concentration can no longer be "
            f"directly verified from current filings."
        ),
        "source_tag": f"data-coverage gap, confirmed against FY{latest_fy} filing",
    }]


def _eps_swing_notes(connection: Connection, run_id: str) -> list[dict]:
    rows = connection.execute(
        text("""
            SELECT fiscal_year, yoy_change_pct FROM gold_kpi_trends
            WHERE metric_name = 'diluted_eps' AND yoy_change_pct IS NOT NULL
            ORDER BY fiscal_year
        """)
    ).mappings().all()
    notes = []
    for r in rows:
        if r["yoy_change_pct"] is not None and r["yoy_change_pct"] <= -50:
            notes.append({
                "run_id": run_id, "category": "data_quality", "fiscal_year": r["fiscal_year"],
                "note_text": (
                    f"Diluted EPS shows an unusually large decline in FY{r['fiscal_year']} "
                    f"({r['yoy_change_pct']:.1f}% YoY). This scale of drop often reflects a stock split "
                    f"rather than an operating decline -- verify against the filing before treating it as "
                    f"a real earnings deterioration, and split-adjust prior-year EPS before comparing "
                    f"across this boundary."
                ),
                "source_tag": f"data-quality flag, FY{r['fiscal_year']} filing",
            })
    return notes


def build_dashboard_notes(connection: Connection, run_id: str) -> int:
    latest_fy = _latest_fiscal_year(connection)
    if latest_fy is None:
        return 0

    notes: list[dict] = []
    notes += _cash_flow_notes(connection, run_id, latest_fy)
    notes += _segment_growth_notes(connection, run_id, latest_fy)
    notes += _concentration_notes(connection, run_id, latest_fy)
    notes += _segment_taxonomy_change_notes(connection, run_id, latest_fy)
    notes += _geography_disclosure_gap_notes(connection, run_id, latest_fy)
    notes += _eps_swing_notes(connection, run_id)

    if notes:
        connection.execute(text("DELETE FROM gold_dashboard_notes"))
        connection.execute(
            text("""
                INSERT INTO gold_dashboard_notes (run_id, category, fiscal_year, note_text, source_tag)
                VALUES (:run_id, :category, :fiscal_year, :note_text, :source_tag)
            """),
            notes,
        )
    return len(notes)
