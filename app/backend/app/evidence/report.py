"""Deterministic self-contained HTML reports for persisted evidence runs."""

from __future__ import annotations

import html
from collections.abc import Callable, Mapping
from typing import Any, cast

from app.backend.app.evidence._common import load_ijson_object
from app.backend.app.evidence.decision_statement import parse_decision_artifact
from app.backend.app.evidence.runs import (
    CompletedEvidenceRun,
    EvidenceRunArtifact,
    create_evidence_run_artifact,
)

_REPORT_PATH = "rendered/report.html"
_STRUCTURED_REPORT_ROLES = {
    "decision",
    "estimate",
    "finding",
    "metric",
    "protocol",
    "run",
    "source",
}


def render_report_html(run: CompletedEvidenceRun) -> bytes:
    """Render one persisted run from its exact immutable artifact payloads."""

    documents: dict[str, dict[str, Any]] = {}
    for artifact in run.artifacts:
        if artifact.role not in _STRUCTURED_REPORT_ROLES:
            continue
        document = load_ijson_object(artifact.payload)
        if artifact.role == "decision":
            document, _, _ = parse_decision_artifact(
                document,
                schema_id=artifact.schema_id,
            )
        documents[artifact.path] = document
    run_document = _single_document(documents, "run/")
    queries = cast(list[dict[str, Any]], run_document["queries"])
    if not queries:
        raise ValueError("persisted run report requires a query reference")
    statement_path = cast(str, queries[0]["statement_path"])
    query_artifact = next(
        (artifact for artifact in run.artifacts if artifact.path == statement_path),
        None,
    )
    if query_artifact is None or query_artifact.role != "query":
        raise ValueError("persisted run report query artifact is missing")
    try:
        query_statement = query_artifact.payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("persisted run report query is not strict UTF-8") from error
    return _render_report_documents(documents, query_statement)


def create_report_artifact(run: CompletedEvidenceRun) -> EvidenceRunArtifact:
    """Bind a rendered persisted-run report to its canonical ABX member."""

    return create_evidence_run_artifact(
        path=_REPORT_PATH,
        role="report",
        media_type="text/html",
        payload=render_report_html(run),
    )


_ROLE_SOURCE_LABELS = {
    "credential": "role carried by the issued credential",
    "asserted": "role asserted by the caller, unverified",
    "policy_default": "no role declared; the policy's first approval role applied",
}


def _decided_by_html(
    decision: Mapping[str, Any],
    escaped: Callable[[object], str],
) -> str:
    """Render the decider with the provenance of the role they decided under.

    A decision record written before ``role_source`` existed simply has no such
    field, and the report says nothing rather than guessing a source for it.
    """

    decided_by = cast(dict[str, Any], decision["decided_by"])
    rendered = (
        f"<code>{escaped(decided_by['actor_ref'])}</code> "
        f"as {escaped(decided_by['role'])}"
    )
    role_source = decided_by.get("role_source")
    label = _ROLE_SOURCE_LABELS.get(cast(str, role_source)) if role_source else None
    if label is None:
        return rendered
    return f"{rendered} ({escaped(role_source)}: {escaped(label)})"


def _single_document(
    documents: Mapping[str, dict[str, Any]],
    prefix: str,
) -> dict[str, Any]:
    matches = [documents[path] for path in sorted(documents) if path.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"persisted run report requires exactly one {prefix} document")
    return matches[0]


def _optional_document(
    documents: Mapping[str, dict[str, Any]],
    prefix: str,
) -> dict[str, Any] | None:
    matches = _documents(documents, prefix)
    if len(matches) > 1:
        raise ValueError(f"persisted run report allows at most one {prefix} document")
    return matches[0] if matches else None


def _documents(
    documents: Mapping[str, dict[str, Any]],
    prefix: str,
) -> list[dict[str, Any]]:
    return [documents[path] for path in sorted(documents) if path.startswith(prefix)]


def _matching_metric(
    documents: Mapping[str, dict[str, Any]],
    estimate: dict[str, Any],
) -> dict[str, Any]:
    metrics = [
        documents[path]
        for path in sorted(documents)
        if path.startswith("metrics/")
    ]
    if not metrics:
        raise ValueError("persisted run report requires at least one metric document")
    lineage = cast(dict[str, Any], estimate["lineage"])
    metric_lineage = cast(dict[str, Any], lineage["metric"])
    metric_id = cast(str, metric_lineage["metric_id"])
    return next(
        (metric for metric in metrics if metric["metric_id"] == metric_id),
        metrics[0],
    )


def _render_report_documents(
    documents: Mapping[str, dict[str, Any]],
    query_statement: str,
) -> bytes:
    """Render validated logical documents; retained for the legacy demo fixture."""

    def escaped(value: object) -> str:
        return html.escape(str(value), quote=True)

    protocol = _single_document(documents, "protocol/")
    protocol_body = cast(dict[str, Any], protocol["protocol"])
    freeze = cast(dict[str, Any], protocol["freeze"])
    run = _single_document(documents, "run/")
    runner = cast(dict[str, Any], run["runner"])
    queries = cast(list[dict[str, Any]], run["queries"])
    if not queries:
        raise ValueError("persisted run report requires a query reference")
    query = queries[0]
    source = _single_document(documents, "sources/")
    source_fingerprint = cast(dict[str, Any], source["fingerprint"])
    source_engine = cast(dict[str, Any], source["engine"])
    estimates = _documents(documents, "estimates/")
    decision = _optional_document(documents, "decision/")

    finding_items: list[str] = []
    for path in sorted(path for path in documents if path.startswith("diagnostics/")):
        finding = documents[path]
        remediation = cast(dict[str, Any], finding["remediation"])
        override = cast(dict[str, Any] | None, finding.get("override"))
        override_html = "<p>Override: none.</p>"
        if override is not None:
            override_html = (
                "<dl>"
                f"<dt>Override actor</dt><dd><code>{escaped(override['actor_ref'])}</code></dd>"
                f"<dt>Override reason</dt><dd>{escaped(override['reason'])}</dd>"
                f"<dt>Override recorded</dt><dd>{escaped(override['recorded_at'])}</dd>"
                "</dl>"
            )
        finding_items.append(
            "<li>"
            f"<h3>{escaped(finding['code'])}</h3>"
            f"<p>{escaped(finding['summary'])}</p>"
            "<dl>"
            f"<dt>Finding ID</dt><dd><code>{escaped(finding['finding_id'])}</code></dd>"
            f"<dt>Category</dt><dd>{escaped(finding['category'])}</dd>"
            f"<dt>Severity</dt><dd>{escaped(finding['severity'])}</dd>"
            f"<dt>State</dt><dd>{escaped(finding['state'])}</dd>"
            f"<dt>Remediation</dt><dd><code>{escaped(remediation['code'])}</code>: "
            f"{escaped(remediation['guidance'])}</dd>"
            "</dl>"
            f"{override_html}"
            "</li>"
        )
    findings_html = (
        f"<ul>{''.join(finding_items)}</ul>"
        if finding_items
        else "<p>No findings were recorded for this run.</p>"
    )

    if not estimates:
        estimate_html = "<p>No estimate was produced for this run.</p>"
    else:
        estimate_items: list[str] = []
        for estimate in estimates:
            metric = _matching_metric(documents, estimate)
            uncertainty = cast(dict[str, Any], estimate["uncertainty"])
            sample_size = cast(dict[str, Any], estimate["sample_size"])
            sample_groups = cast(dict[str, Any], sample_size["groups"])
            group_items = "".join(
                f"<li><code>{escaped(group)}</code>: {escaped(value)}</li>"
                for group, value in sorted(sample_groups.items())
            )
            estimate_items.append(
                "<article>"
                f"<h3><code>{escaped(metric['metric_id'])}</code> "
                f"({escaped(metric['name'])})</h3>"
                "<dl>"
                f"<dt>Effect measure</dt><dd>{escaped(estimate['effect_measure'])}</dd>"
                f"<dt>Point estimate</dt><dd>{escaped(estimate['point_estimate'])}</dd>"
                f"<dt>Confidence level</dt><dd>{escaped(uncertainty['level'])}</dd>"
                f"<dt>Confidence interval</dt><dd>{escaped(uncertainty['lower'])} to "
                f"{escaped(uncertainty['upper'])}</dd>"
                f"<dt>Standard error</dt><dd>{escaped(uncertainty.get('standard_error', 'n/a'))}</dd>"
                f"<dt>p-value</dt><dd>{escaped(uncertainty.get('p_value', 'n/a'))}</dd>"
                f"<dt>Total sample size</dt><dd>{escaped(sample_size['total'])}</dd>"
                "</dl>"
                "<h4>Sample sizes by group</h4>"
                f"<ul>{group_items}</ul>"
                "</article>"
            )
        estimate_html = "".join(estimate_items)

    if decision is None:
        decision_html = "<p>No decision was recorded for this run.</p>"
    else:
        decision_html = (
            "<dl>"
            f"<dt>Decision ID</dt><dd><code>{escaped(decision['decision_id'])}</code></dd>"
            f"<dt>Proposed verdict</dt><dd>{escaped(decision['proposed_verdict'])}</dd>"
            f"<dt>Human verdict</dt><dd>human_verdict={escaped(decision['human_verdict'])}</dd>"
            f"<dt>State</dt><dd>{escaped(decision['state'])}</dd>"
            f"<dt>Decided by</dt><dd>{_decided_by_html(decision, escaped)}</dd>"
            f"<dt>Rationale</dt><dd>{escaped(decision['rationale'])}</dd>"
            "</dl>"
        )

    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trialmark Workbench report</title>
<style>
:root {{ color-scheme: light dark; font-family: system-ui, sans-serif; line-height: 1.5; }}
body {{ margin: 0; background: Canvas; color: CanvasText; }}
main {{ max-width: 72rem; margin: 0 auto; padding: 2rem; }}
section {{ border-block-start: 1px solid GrayText; margin-block-start: 2rem; padding-block-start: 1rem; }}
dl {{ display: grid; grid-template-columns: minmax(10rem, 16rem) 1fr; gap: .4rem 1rem; }}
dt {{ font-weight: 700; }}
dd {{ margin: 0; overflow-wrap: anywhere; }}
code, pre {{ font-family: ui-monospace, monospace; overflow-wrap: anywhere; }}
pre {{ white-space: pre-wrap; border: 1px solid GrayText; padding: 1rem; }}
.trust {{ border: 2px solid GrayText; padding: 1rem; font-weight: 650; }}
</style>
</head>
<body>
<main>
<h1>{escaped(protocol_body['title'])}</h1>
<p>Self-contained Trialmark Workbench report for offline human review.</p>

<section>
<h2>Frozen protocol</h2>
<dl>
<dt>Protocol ID</dt><dd><code>{escaped(protocol_body['protocol_id'])}</code></dd>
<dt>Protocol revision</dt><dd><code>{escaped(run['protocol_revision_id'])}</code></dd>
<dt>Freeze state</dt><dd>{escaped(freeze['state'])}</dd>
<dt>Frozen at</dt><dd>{escaped(freeze['frozen_at'])}</dd>
</dl>
</section>

<section>
<h2>Run, source, and query lineage</h2>
<dl>
<dt>Run ID</dt><dd><code>{escaped(run['run_id'])}</code></dd>
<dt>Run status</dt><dd>{escaped(run['status'])}</dd>
<dt>Runner</dt><dd>{escaped(runner['name'])} {escaped(runner['version'])}</dd>
<dt>Source snapshot</dt><dd><code>{escaped(source['source_snapshot_id'])}</code></dd>
<dt>Source kind</dt><dd>{escaped(source['kind'])}</dd>
<dt>Source fingerprint</dt><dd><code>{escaped(source_fingerprint['value'])}</code></dd>
<dt>Source engine</dt><dd>{escaped(source_engine['name'])} {escaped(source_engine['version'])}</dd>
<dt>Query ID</dt><dd><code>{escaped(query['query_id'])}</code></dd>
<dt>Query dialect</dt><dd>{escaped(query['dialect'])}</dd>
</dl>
<pre>{escaped(query_statement)}</pre>
</section>

<section>
<h2>Findings and formal override</h2>
{findings_html}
</section>

<section>
<h2>Estimate</h2>
{estimate_html}
</section>

<section>
<h2>Decision</h2>
{decision_html}
</section>

<section>
<h2>Trust boundary</h2>
<p class="trust">Integrity verification detects protected-byte changes. It does not establish truth, statistical validity, or actor identity.</p>
</section>
</main>
</body>
</html>
"""
    return document.encode("utf-8")


__all__ = ["create_report_artifact", "render_report_html"]
