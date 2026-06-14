"""Attribute-based targeting / eligibility for the execution layer.

A stored experiment may carry a list of simple ``{attribute, operator, value}`` rules.
A user is eligible only if **all** rules pass against the assignment request's
``attributes`` (AND semantics). Deliberately a small, pure rule set — equals / not_equals
/ in / numeric comparisons — not a full boolean rule engine (an explicit MVP non-goal).
A missing attribute fails membership/equality/comparison rules (and passes ``not_equals``),
matching the intuitive "the user doesn't qualify" reading.
"""

from __future__ import annotations

from typing import Any

NUMERIC_OPERATORS = {"gt", "lt", "gte", "lte"}
SUPPORTED_OPERATORS = {"equals", "not_equals", "in"} | NUMERIC_OPERATORS


def _matches_rule(rule: dict[str, Any], attributes: dict[str, Any]) -> bool:
    attribute = rule.get("attribute")
    operator = rule.get("operator")
    expected = rule.get("value")
    actual = attributes.get(attribute)

    if operator == "equals":
        return actual == expected
    if operator == "not_equals":
        return actual != expected
    if operator == "in":
        return isinstance(expected, list) and actual in expected
    if operator in NUMERIC_OPERATORS:
        if actual is None:
            return False
        try:
            actual_number = float(actual)
            expected_number = float(expected)
        except (TypeError, ValueError):
            return False
        if operator == "gt":
            return actual_number > expected_number
        if operator == "lt":
            return actual_number < expected_number
        if operator == "gte":
            return actual_number >= expected_number
        return actual_number <= expected_number  # lte
    return False  # unknown operator never matches


def evaluate_targeting(
    rules: list[dict[str, Any]] | None,
    attributes: dict[str, Any] | None,
) -> bool:
    """Whether the user satisfies every targeting rule (AND). No rules -> eligible."""
    if not rules:
        return True
    resolved_attributes = attributes or {}
    return all(_matches_rule(rule, resolved_attributes) for rule in rules)
