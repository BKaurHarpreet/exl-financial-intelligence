from app.etl.transform import infer_unit


def test_infer_unit_for_rates() -> None:
    assert infer_unit("Operating margin", None) == "percent"
    assert infer_unit("Tax", "Rate %") == "percent"


def test_infer_unit_for_shares() -> None:
    assert infer_unit("Diluted shares", None) == "shares"
    assert infer_unit("EPS per share", None) == "currency_per_share"


def test_infer_unit_default() -> None:
    assert infer_unit("Revenue", "FY 2024") == "currency_or_count"
