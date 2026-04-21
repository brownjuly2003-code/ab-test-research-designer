from app.backend.app.constants import MAX_RECOMMENDED_DURATION_DAYS


WARNING_CATALOG = {
    "LONG_DURATION": {
        "severity": "high",
        "message_key": "warnings.long_duration",
        "message_params": {"max_days": MAX_RECOMMENDED_DURATION_DAYS},
    },
    "LOW_TRAFFIC": {
        "severity": "medium",
        "message_key": "warnings.low_traffic",
    },
    "MISSING_VARIANCE": {
        "severity": "high",
        "message_key": "warnings.missing_variance",
    },
    "MANY_VARIANTS_LOW_TRAFFIC": {
        "severity": "high",
        "message_key": "warnings.many_variants_low_traffic",
    },
    "SEASONALITY_PRESENT": {
        "severity": "medium",
        "message_key": "warnings.seasonality_present",
    },
    "CAMPAIGN_CONTAMINATION": {
        "severity": "medium",
        "message_key": "warnings.campaign_contamination",
    },
    "UNDERPOWERED_DESIGN": {
        "severity": "medium",
        "message_key": "warnings.underpowered_design",
    },
    "CONSERVATIVE_MULTIVARIANT_ALPHA": {
        "severity": "medium",
        "message_key": "warnings.conservative_multivariant_alpha",
    },
    "LONG_TEST_NOT_POSSIBLE": {
        "severity": "high",
        "message_key": "warnings.long_test_not_possible",
    },
    "INTERIM_LOOKS_INCREASE_SAMPLE": {
        "severity": "medium",
        "message_key": "warnings.interim_looks_increase_sample",
    },
    "SRM_DETECTED": {
        "severity": "high",
        "message_key": "warnings.srm_detected",
    },
}
