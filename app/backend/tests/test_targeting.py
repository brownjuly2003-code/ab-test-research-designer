from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.execution.targeting import evaluate_targeting


def test_no_rules_means_eligible() -> None:
    assert evaluate_targeting([], {"any": "thing"}) is True
    assert evaluate_targeting(None, None) is True


def test_equals_and_not_equals() -> None:
    rules = [{"attribute": "country", "operator": "equals", "value": "US"}]
    assert evaluate_targeting(rules, {"country": "US"}) is True
    assert evaluate_targeting(rules, {"country": "CA"}) is False

    not_rules = [{"attribute": "country", "operator": "not_equals", "value": "US"}]
    assert evaluate_targeting(not_rules, {"country": "CA"}) is True
    assert evaluate_targeting(not_rules, {"country": "US"}) is False


def test_in_operator() -> None:
    rules = [{"attribute": "plan", "operator": "in", "value": ["pro", "enterprise"]}]
    assert evaluate_targeting(rules, {"plan": "pro"}) is True
    assert evaluate_targeting(rules, {"plan": "free"}) is False


def test_numeric_comparisons() -> None:
    assert evaluate_targeting([{"attribute": "age", "operator": "gte", "value": 18}], {"age": 18}) is True
    assert evaluate_targeting([{"attribute": "age", "operator": "gte", "value": 18}], {"age": 17}) is False
    assert evaluate_targeting([{"attribute": "age", "operator": "lt", "value": 30}], {"age": 25}) is True
    assert evaluate_targeting([{"attribute": "age", "operator": "gt", "value": 30}], {"age": 25}) is False


def test_numeric_comparison_with_string_number() -> None:
    # Attributes can arrive as strings; numeric operators coerce.
    assert evaluate_targeting([{"attribute": "age", "operator": "gte", "value": 18}], {"age": "21"}) is True


def test_missing_attribute_fails_membership_but_passes_not_equals() -> None:
    assert evaluate_targeting([{"attribute": "country", "operator": "equals", "value": "US"}], {}) is False
    assert evaluate_targeting([{"attribute": "country", "operator": "in", "value": ["US"]}], {}) is False
    assert evaluate_targeting([{"attribute": "age", "operator": "gt", "value": 5}], {}) is False
    assert evaluate_targeting([{"attribute": "country", "operator": "not_equals", "value": "US"}], {}) is True


def test_rules_are_anded() -> None:
    rules = [
        {"attribute": "country", "operator": "equals", "value": "US"},
        {"attribute": "age", "operator": "gte", "value": 18},
    ]
    assert evaluate_targeting(rules, {"country": "US", "age": 20}) is True
    assert evaluate_targeting(rules, {"country": "US", "age": 16}) is False
    assert evaluate_targeting(rules, {"country": "CA", "age": 20}) is False


def test_unknown_operator_never_matches() -> None:
    assert evaluate_targeting([{"attribute": "x", "operator": "regex", "value": ".*"}], {"x": "y"}) is False
