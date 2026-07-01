from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re


NULL_VALUES = {"", "na", "n/a", "none", "null", "-", "--", "nan"}


@dataclass(frozen=True)
class RawCell:
    source_file: str
    fiscal_year: int
    sheet_name: str
    row_number: int
    column_number: int
    column_label: str
    raw_value: str | None
    normalized_text: str | None
    inferred_type: str
    is_blank: bool
    source_address: str


@dataclass(frozen=True)
class SilverFact:
    cell_id: int
    fiscal_year: int
    source_file: str
    sheet_name: str
    statement_section: str | None
    metric_name: str
    period_label: str | None
    value_numeric: Decimal | None
    value_text: str | None
    unit: str | None
    source_address: str


def fiscal_year_from_path(path: Path) -> int:
    match = re.search(r"(20\d{2})", path.name)
    if not match:
        raise ValueError(f"Cannot infer fiscal year from {path}")
    return int(match.group(1))


def normalize_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text.lower() not in NULL_VALUES else None


def parse_decimal(value: object) -> Decimal | None:
    text = normalize_text(value)
    if text is None:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = text.replace("$", "").replace(",", "").replace("%", "").strip()
    if negative:
        text = f"-{text}"
    try:
        val = Decimal(text)
        return None if val.is_nan() else val
    except (InvalidOperation, ValueError):
        return None


def infer_type(value: object) -> str:
    text = normalize_text(value)
    if text is None:
        return "blank"
    if parse_decimal(text) is not None:
        return "number"
    return "text"


def clean_metric_name(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    text = re.sub(r"[^0-9A-Za-z%&/(). -]+", "", text).strip()
    return text or "Unlabeled metric"
