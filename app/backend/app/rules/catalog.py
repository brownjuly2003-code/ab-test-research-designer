from app.backend.app.constants import MAX_RECOMMENDED_DURATION_DAYS


WARNING_CATALOG = {
    "LONG_DURATION": {
        "severity": "high",
        "message": (
            f"Estimated duration exceeds {MAX_RECOMMENDED_DURATION_DAYS} days. "
            "Consider increasing traffic or relaxing MDE."
        ),
    },
    "LOW_TRAFFIC": {
        "severity": "medium",
        "message": "Effective test traffic is low. Duration and variance risk may be high.",
    },
    "MISSING_VARIANCE": {
        "severity": "high",
        "message": "Continuous metric requires std_dev for deterministic sample size calculation.",
    },
    "MANY_VARIANTS_LOW_TRAFFIC": {
        "severity": "high",
        "message": "Too many variants for the available traffic. Consider reducing the number of variants.",
    },
    "SEASONALITY_PRESENT": {
        "severity": "medium",
        "message": "Seasonality is present. Cover at least one full weekly cycle.",
    },
    "CAMPAIGN_CONTAMINATION": {
        "severity": "medium",
        "message": "Active campaigns may contaminate the test and bias uplift estimates.",
    },
    "UNDERPOWERED_DESIGN": {
        "severity": "medium",
        "message": "Requested power is below the usual 0.8 threshold. Risk of false negatives is higher.",
    },
    "CONSERVATIVE_MULTIVARIANT_ALPHA": {
        "severity": "medium",
        "message": (
            "More than two variants trigger a Bonferroni alpha correction. "
            "This is conservative and may overstate the required sample size."
        ),
    },
    "LONG_TEST_NOT_POSSIBLE": {
        "severity": "high",
        "message": "Expected duration is long, but the project cannot support a long-running test.",
    },
    "INTERIM_LOOKS_INCREASE_SAMPLE": {
        "severity": "medium",
        "message": "Sequential design increases required sample size by ~{pct}%.",
    },
    "SRM_DETECTED": {
        "severity": "high",
        "message": "Sample ratio mismatch detected (p < 0.001). Check randomization and tracking.",
    },
}
