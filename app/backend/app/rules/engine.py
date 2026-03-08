from app.backend.app.constants import MAX_RECOMMENDED_DURATION_DAYS
from app.backend.app.rules.catalog import WARNING_CATALOG


def _warning(code: str) -> dict:
    entry = WARNING_CATALOG[code]
    return {
        "code": code,
        "severity": entry["severity"],
        "message": entry["message"],
        "source": "rules_engine",
    }


def evaluate_warnings(payload: dict, results: dict | None = None) -> list[dict]:
    warnings: list[dict] = []
    results = results or {}

    if payload.get("metric_type") == "continuous" and payload.get("std_dev") is None:
        warnings.append(_warning("MISSING_VARIANCE"))

    estimated_duration_days = results.get("estimated_duration_days")
    if estimated_duration_days and estimated_duration_days > MAX_RECOMMENDED_DURATION_DAYS:
        warnings.append(_warning("LONG_DURATION"))

    effective_daily_traffic = results.get("effective_daily_traffic")
    if effective_daily_traffic and effective_daily_traffic < 1000:
        warnings.append(_warning("LOW_TRAFFIC"))

    variants_count = payload.get("variants_count", len(payload.get("traffic_split", [])) or 2)
    if variants_count > 2:
        warnings.append(_warning("CONSERVATIVE_MULTIVARIANT_ALPHA"))

    if effective_daily_traffic and variants_count > 2 and effective_daily_traffic < variants_count * 2000:
        warnings.append(_warning("MANY_VARIANTS_LOW_TRAFFIC"))

    if payload.get("seasonality_present") is True:
        warnings.append(_warning("SEASONALITY_PRESENT"))

    if payload.get("active_campaigns_present") is True:
        warnings.append(_warning("CAMPAIGN_CONTAMINATION"))

    power = payload.get("power")
    if power is not None and power < 0.8:
        warnings.append(_warning("UNDERPOWERED_DESIGN"))

    if payload.get("long_test_possible") is False and estimated_duration_days and estimated_duration_days > 14:
        warnings.append(_warning("LONG_TEST_NOT_POSSIBLE"))

    return warnings
