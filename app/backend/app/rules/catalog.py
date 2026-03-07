WARNING_CATALOG = {
    "LONG_DURATION": {
        "severity": "high",
        "message": "Estimated duration exceeds 56 days. Consider increasing traffic or relaxing MDE.",
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
    "LONG_TEST_NOT_POSSIBLE": {
        "severity": "high",
        "message": "Expected duration is long, but the project cannot support a long-running test.",
    },
}
