from decimal import Decimal
from pathlib import Path

from app.etl.types import clean_metric_name, fiscal_year_from_path, infer_type, normalize_text, parse_decimal


def test_fiscal_year_from_path() -> None:
    assert fiscal_year_from_path(Path("2024.xls")) == 2024


def test_normalize_text_blank_values() -> None:
    assert normalize_text("  ") is None
    assert normalize_text("N/A") is None
    assert normalize_text(" Revenue ") == "Revenue"


def test_parse_decimal_financial_formats() -> None:
    assert parse_decimal("$1,250.50") == Decimal("1250.50")
    assert parse_decimal("(42.10)") == Decimal("-42.10")
    assert parse_decimal("21.5%") == Decimal("21.5")
    assert parse_decimal("Revenue") is None


def test_infer_type() -> None:
    assert infer_type("") == "blank"
    assert infer_type("123.45") == "number"
    assert infer_type("Operating income") == "text"


def test_clean_metric_name() -> None:
    assert clean_metric_name("  Net   income !!! ") == "Net income"
