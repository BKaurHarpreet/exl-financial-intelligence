def infer_unit(metric_label: str | None, period_label: str | None) -> str | None:
    text = f"{metric_label or ''} {period_label or ''}".lower()
    if "%" in text or "rate" in text or "margin" in text:
        return "percent"
    if "per share" in text:
        return "currency_per_share"
    if "shares" in text:
        return "shares"
    return "currency_or_count"
