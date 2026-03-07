from html import escape


def _list_to_markdown(items: list[str]) -> str:
    if not items:
        return "- None"
    return "\n".join(f"- {item}" for item in items)


def _as_html(value: object) -> str:
    return escape(str(value))


def export_report_to_markdown(report: dict) -> str:
    recommendations = report["recommendations"]
    risks = report["risks"]

    return f"""# Experiment Report

## Executive Summary

{report["executive_summary"]}

## Calculations

- Sample size per variant: {report["calculations"]["sample_size_per_variant"]}
- Total sample size: {report["calculations"]["total_sample_size"]}
- Estimated duration days: {report["calculations"]["estimated_duration_days"]}

### Assumptions

{_list_to_markdown(report["calculations"]["assumptions"])}

## Experiment Design

- Randomization unit: {report["experiment_design"]["randomization_unit"]}
- Traffic split: {report["experiment_design"]["traffic_split"]}
- Target audience: {report["experiment_design"]["target_audience"]}
- Inclusion criteria: {report["experiment_design"]["inclusion_criteria"]}
- Exclusion criteria: {report["experiment_design"]["exclusion_criteria"]}

## Metrics Plan

### Primary
{_list_to_markdown(report["metrics_plan"]["primary"])}

### Secondary
{_list_to_markdown(report["metrics_plan"]["secondary"])}

### Guardrail
{_list_to_markdown(report["metrics_plan"]["guardrail"])}

### Diagnostic
{_list_to_markdown(report["metrics_plan"]["diagnostic"])}

## Risks

### Statistical
{_list_to_markdown(risks["statistical"])}

### Product
{_list_to_markdown(risks["product"])}

### Technical
{_list_to_markdown(risks["technical"])}

### Operational
{_list_to_markdown(risks["operational"])}

## Recommendations

### Before Launch
{_list_to_markdown(recommendations["before_launch"])}

### During Test
{_list_to_markdown(recommendations["during_test"])}

### After Test
{_list_to_markdown(recommendations["after_test"])}

## Open Questions

{_list_to_markdown(report["open_questions"])}
"""


def export_report_to_html(report: dict) -> str:
    def as_list(items: list[str]) -> str:
        if not items:
            return "<li>None</li>"
        return "".join(f"<li>{_as_html(item)}</li>" for item in items)

    recommendations = report["recommendations"]
    risks = report["risks"]

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Experiment Report</title>
    <style>
      body {{ font-family: 'Segoe UI', sans-serif; margin: 40px auto; max-width: 920px; color: #17312a; }}
      h1, h2, h3 {{ color: #0f766e; }}
      section {{ margin-bottom: 28px; }}
      .panel {{ border: 1px solid #d7e6df; border-radius: 16px; padding: 18px; background: #f8fbf9; }}
    </style>
  </head>
  <body>
    <h1>Experiment Report</h1>
    <section class="panel">
      <h2>Executive Summary</h2>
      <p>{_as_html(report["executive_summary"])}</p>
    </section>
    <section class="panel">
      <h2>Calculations</h2>
      <ul>
        <li>Sample size per variant: {_as_html(report["calculations"]["sample_size_per_variant"])}</li>
        <li>Total sample size: {_as_html(report["calculations"]["total_sample_size"])}</li>
        <li>Estimated duration days: {_as_html(report["calculations"]["estimated_duration_days"])}</li>
      </ul>
      <h3>Assumptions</h3>
      <ul>{as_list(report["calculations"]["assumptions"])}</ul>
    </section>
    <section class="panel">
      <h2>Metrics Plan</h2>
      <h3>Primary</h3>
      <ul>{as_list(report["metrics_plan"]["primary"])}</ul>
      <h3>Secondary</h3>
      <ul>{as_list(report["metrics_plan"]["secondary"])}</ul>
      <h3>Guardrail</h3>
      <ul>{as_list(report["metrics_plan"]["guardrail"])}</ul>
      <h3>Diagnostic</h3>
      <ul>{as_list(report["metrics_plan"]["diagnostic"])}</ul>
    </section>
    <section class="panel">
      <h2>Risks</h2>
      <h3>Statistical</h3>
      <ul>{as_list(risks["statistical"])}</ul>
      <h3>Product</h3>
      <ul>{as_list(risks["product"])}</ul>
      <h3>Technical</h3>
      <ul>{as_list(risks["technical"])}</ul>
      <h3>Operational</h3>
      <ul>{as_list(risks["operational"])}</ul>
    </section>
    <section class="panel">
      <h2>Recommendations</h2>
      <h3>Before Launch</h3>
      <ul>{as_list(recommendations["before_launch"])}</ul>
      <h3>During Test</h3>
      <ul>{as_list(recommendations["during_test"])}</ul>
      <h3>After Test</h3>
      <ul>{as_list(recommendations["after_test"])}</ul>
    </section>
    <section class="panel">
      <h2>Open Questions</h2>
      <ul>{as_list(report["open_questions"])}</ul>
    </section>
  </body>
</html>
"""
