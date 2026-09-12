"""Deterministic Gate 3 aggregation over validated external pilot records.

Gate 3 is the decision the pilot track has to survive before the conditional
Evidence Graph, MCP and federation work may start. Until now it was evaluated
by hand against prose, which is the kind of measurement that drifts toward the
answer its author wanted. This module measures it from the records instead:
the input is a directory of canonical ``<date>-<anon>.md`` pilot records, the
output is a frozen report whose digest covers everything except itself, and the
same cohort renders the same bytes every time.

Two rules are worth stating out loud, because both make the verdict harsher
than a looser reading would:

- **A criterion nobody measured is never reported as passed.** Preflight
  detection and false blocking are properties of the engineering suite, not of
  a partner session, so this report calls them ``unmeasured`` and says where
  they *are* measured. That rule comes from
  ``archive/handoffs/pilot-acceptance.md`` and is why the first Gate 3 verdict
  was PIVOT rather than a softer word.
- **One partner is one cycle.** Two records from the same ``participant_ref``
  count once toward completed cycles; the second contributes only if it records
  reuse. The thresholds are about breadth of adoption, and counting one
  enthusiastic partner three times would answer a different question.

The counting rules differ by criterion on purpose. A threshold stated as an
absolute count ("at least three") can be measured as zero -- we looked, and
there were none -- so an empty cohort *fails* it. A threshold stated as a rate
("100% of displayed estimates") cannot be measured at all without a
denominator, so an empty cohort leaves it ``unmeasured``.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.backend.app.evidence._common import canonical_json_bytes, sha256_hex
from app.backend.app.evidence.pilot_records import (
    PilotMeasurements,
    PilotRatio,
    PilotRecordValidationError,
    PilotSessionRecord,
    load_pilot_record,
)

Gate3Decision = Literal["continue", "pivot", "stop"]
Gate3CriterionVerdict = Literal["pass", "fail", "unmeasured"]
Gate3CriterionKey = Literal[
    "completed_cycles",
    "repeat_use",
    "time_to_bundle",
    "preflight_detection",
    "estimate_lineage",
    "bundle_privacy",
]

MINIMUM_COMPLETED_CYCLES = 3
MINIMUM_REPEAT_PARTICIPANTS = 2
MEDIAN_SECONDS_THRESHOLD = 900

_RECORD_SUFFIX = ".md"
_SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"
# Placeholder for the one moment a report exists without its own digest. It is
# structurally valid so the model still validates every other field first, and
# it never leaves `build_gate3_report`.
_UNSET_DIGEST = "sha256:" + "0" * 64


class Gate3Error(ValueError):
    """Raised when a cohort cannot be aggregated into a Gate 3 report."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class Gate3Criterion(_FrozenModel):
    """One Gate 3 threshold, with the arithmetic that produced its verdict."""

    key: Gate3CriterionKey
    title: str
    threshold: str
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    observed: str
    verdict: Gate3CriterionVerdict


class Gate3Report(_FrozenModel):
    """The whole Gate 3 measurement for one cohort of pilot records."""

    schema_version: Literal["1"]
    records: tuple[str, ...]
    participants: int = Field(ge=0)
    completed_sessions: int = Field(ge=0)
    median_time_to_bundle_seconds: int | None
    criteria: tuple[Gate3Criterion, ...]
    verdict: Gate3Decision
    report_digest: str = Field(pattern=_SHA256_PATTERN)


def load_pilot_cohort(directory: Path | str) -> tuple[PilotSessionRecord, ...]:
    """Load every pilot record in ``directory``, in filename order.

    Every ``*.md`` file has to be a canonical record. A file that is not one is
    an error rather than a skip: silently ignoring an unparseable record would
    drop a partner out of the denominator, which is the one failure mode that
    makes the gate report better than the truth.
    """

    root = Path(directory)
    if not root.is_dir():
        raise Gate3Error(f"pilot record directory does not exist: {root}")

    records: list[PilotSessionRecord] = []
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        if path.is_dir() or path.suffix != _RECORD_SUFFIX:
            continue
        try:
            records.append(load_pilot_record(path))
        except PilotRecordValidationError as error:
            raise Gate3Error(f"{path.name} is not a pilot record: {error}") from error
    return tuple(records)


def _criterion(
    key: Gate3CriterionKey,
    title: str,
    threshold: str,
    numerator: int,
    denominator: int,
    observed: str,
    verdict: Gate3CriterionVerdict,
) -> Gate3Criterion:
    return Gate3Criterion(
        key=key,
        title=title,
        threshold=threshold,
        numerator=numerator,
        denominator=denominator,
        observed=observed,
        verdict=verdict,
    )


def _count_verdict(numerator: int, minimum: int) -> Gate3CriterionVerdict:
    """A threshold stated as an absolute count. Zero is a measurement, not a gap."""

    return "pass" if numerator >= minimum else "fail"


def _rate_verdict(numerator: int, denominator: int) -> Gate3CriterionVerdict:
    """A threshold stated as 100%. Without a denominator there is nothing to rate."""

    if denominator == 0:
        return "unmeasured"
    return "pass" if numerator == denominator else "fail"


def _sum_ratio(
    records: Sequence[PilotSessionRecord],
    select: Callable[[PilotMeasurements], PilotRatio],
) -> tuple[int, int]:
    """Add up one per-record ratio across the cohort.

    A selector rather than a field name, so mypy still sees which ratio is
    being summed.
    """

    numerator = 0
    denominator = 0
    for record in records:
        ratio = select(record.measurements)
        numerator += ratio.numerator
        denominator += ratio.denominator
    return numerator, denominator


def _median_seconds(durations: Sequence[int]) -> int | None:
    """Median rounded up to the whole second.

    Rounding up is the direction that cannot manufacture a pass: the threshold
    is ``median <= 900``, and an exact median above 900 already fails, so the
    ceiling only ever changes how the number reads, never the verdict.
    """

    if not durations:
        return None
    return math.ceil(statistics.median(durations))


def _participant_index(
    records: Sequence[PilotSessionRecord],
) -> dict[str, list[PilotSessionRecord]]:
    index: dict[str, list[PilotSessionRecord]] = {}
    for record in records:
        index.setdefault(record.participant_ref, []).append(record)
    return index


def build_gate3_report(records: Iterable[PilotSessionRecord]) -> Gate3Report:
    """Aggregate validated records into the frozen Gate 3 report."""

    cohort = tuple(records)
    by_participant = _participant_index(cohort)
    participants = len(by_participant)

    completed = tuple(record for record in cohort if record.outcome == "completed")
    completed_participants = sum(
        1
        for sessions in by_participant.values()
        if any(session.outcome == "completed" for session in sessions)
    )
    repeat_participants = sum(
        1
        for sessions in by_participant.values()
        if any(session.reuse.observed for session in sessions)
    )

    durations = tuple(
        record.time_to_bundle_seconds
        for record in completed
        if record.time_to_bundle_seconds is not None
    )
    median = _median_seconds(durations)
    within_threshold = sum(
        1 for value in durations if value <= MEDIAN_SECONDS_THRESHOLD
    )

    lineage_numerator, lineage_denominator = _sum_ratio(cohort, lambda m: m.estimate_lineage)
    privacy_numerator, privacy_denominator = _sum_ratio(cohort, lambda m: m.bundle_privacy)

    criteria = (
        _criterion(
            "completed_cycles",
            "Completed pilots",
            f"at least {MINIMUM_COMPLETED_CYCLES} partner cycles completed "
            "protocol -> preflight -> bundle",
            completed_participants,
            participants,
            f"{completed_participants} of {participants} participants completed "
            "a cycle",
            _count_verdict(completed_participants, MINIMUM_COMPLETED_CYCLES),
        ),
        _criterion(
            "repeat_use",
            "Repeated partner use",
            f"at least {MINIMUM_REPEAT_PARTICIPANTS} partners started a second "
            "experiment or reopened evidence",
            repeat_participants,
            participants,
            f"{repeat_participants} of {participants} participants recorded reuse",
            _count_verdict(repeat_participants, MINIMUM_REPEAT_PARTICIPANTS),
        ),
        _criterion(
            "time_to_bundle",
            "Time to first reviewable bundle",
            f"partner-session median at or under {MEDIAN_SECONDS_THRESHOLD} seconds",
            within_threshold,
            len(durations),
            "no completed session to time"
            if median is None
            else f"median {median} s over {len(durations)} completed sessions",
            "unmeasured" if median is None else (
                "pass" if median <= MEDIAN_SECONDS_THRESHOLD else "fail"
            ),
        ),
        _criterion(
            "preflight_detection",
            "Preflight detection / harm",
            "detection at or above 90% and false blocking below 5%",
            0,
            0,
            "not derivable from pilot records; measured by the preflight contract "
            "suite, not by a partner session",
            "unmeasured",
        ),
        _criterion(
            "estimate_lineage",
            "Displayed-estimate lineage",
            "100% of displayed estimates reference protocol, metric, query, "
            "source and runner",
            lineage_numerator,
            lineage_denominator,
            f"{lineage_numerator} of {lineage_denominator} displayed estimates "
            "carry complete lineage",
            _rate_verdict(lineage_numerator, lineage_denominator),
        ),
        _criterion(
            "bundle_privacy",
            "Bundle privacy",
            "no raw user-level pilot data enters a bundle",
            privacy_numerator,
            privacy_denominator,
            f"{privacy_numerator} of {privacy_denominator} bundles passed the "
            "privacy census",
            _rate_verdict(privacy_numerator, privacy_denominator),
        ),
    )

    draft = Gate3Report(
        schema_version="1",
        records=tuple(_record_name(record) for record in cohort),
        participants=participants,
        completed_sessions=len(completed),
        median_time_to_bundle_seconds=median,
        criteria=criteria,
        verdict=_decide(criteria),
        report_digest=_UNSET_DIGEST,
    )
    return draft.model_copy(update={"report_digest": gate3_report_digest(draft)})


def gate3_report_digest(report: Gate3Report) -> str:
    """Digest every field of the report except the digest itself.

    A reader recomputes it the same way, from the JSON block the Markdown
    carries, without needing this module.
    """

    content = report.model_dump(mode="json", exclude={"report_digest"})
    return sha256_hex(canonical_json_bytes(content))


def _record_name(record: PilotSessionRecord) -> str:
    """The canonical filename of a record, which is all the report needs to cite."""

    return f"{record.session_date}-{record.participant_ref}.md"


def _decide(criteria: Sequence[Gate3Criterion]) -> Gate3Decision:
    """Turn the criteria into the one word the gate exists to produce.

    ``preflight_detection`` is excluded because no cohort of pilot records can
    move it; leaving it in would pin every verdict below ``continue`` forever
    and hide whether the partner evidence itself arrived.
    """

    scored = {
        criterion.key: criterion
        for criterion in criteria
        if criterion.key != "preflight_detection"
    }
    if all(criterion.verdict == "pass" for criterion in scored.values()):
        return "continue"
    if scored["completed_cycles"].numerator == 0:
        # Nothing was obtained. The pilot-acceptance handoff is explicit that a
        # second gate with no cycles is STOP, not another round of PIVOT.
        return "stop"
    return "pivot"


_VERDICT_LABELS: Mapping[str, str] = {
    "pass": "PASS",
    "fail": "FAIL",
    "unmeasured": "UNMEASURED",
}

_DECISION_NOTES: Mapping[str, str] = {
    "continue": "Every criterion measurable from pilot records passed. The "
    "conditional Evidence Graph / MCP / federation track opens.",
    "pivot": "Partner evidence exists but does not meet the thresholds. The "
    "conditional track stays shut.",
    "stop": "No partner completed a cycle. Close the product track honestly; "
    "the repository remains a reference implementation.",
}


def render_gate3_report(report: Gate3Report) -> bytes:
    """Render the only accepted Markdown representation of a Gate 3 report.

    Nothing here reads the clock or the filesystem, so re-running the aggregator
    over an unchanged cohort produces identical bytes. The report date lives in
    the filename the caller chooses, not in the content.
    """

    rows = "\n".join(
        f"| {criterion.title} | {criterion.threshold} | {criterion.observed} "
        f"| **{_VERDICT_LABELS[criterion.verdict]}** |"
        for criterion in report.criteria
    )
    cited = (
        "\n".join(f"- `{name}`" for name in report.records)
        or "- none; no pilot record was present"
    )
    body = json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return (
        "# Gate 3 decision\n\n"
        f"**Verdict: {report.verdict.upper()}.** {_DECISION_NOTES[report.verdict]}\n\n"
        f"Aggregated from {len(report.records)} validated pilot "
        f"record(s) covering {report.participants} participant(s). One "
        "participant counts as one cycle however many sessions they recorded. "
        "A criterion nobody measured is never reported as passed.\n\n"
        "## Evidence matrix\n\n"
        "| Criterion | Threshold | Measured evidence | Status |\n"
        "| --- | --- | --- | --- |\n"
        f"{rows}\n\n"
        "## Records\n\n"
        f"{cited}\n\n"
        "## Machine-readable report\n\n"
        f"```json\n{body}\n```\n"
    ).encode()


def write_gate3_report(report: Gate3Report, destination: Path | str) -> Path:
    """Write the rendered report, replacing an earlier run of the same cohort."""

    path = Path(destination)
    if path.suffix != _RECORD_SUFFIX:
        raise Gate3Error("gate 3 report must be written to a .md path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_gate3_report(report))
    return path


def evaluate_gate3(directory: Path | str) -> Gate3Report:
    """Load a cohort and aggregate it in one step."""

    return build_gate3_report(load_pilot_cohort(directory))


def summarize_gate3_report(
    report: Gate3Report,
    destination: Path | str | None = None,
) -> dict[str, Any]:
    """Return the bounded CLI result for one aggregation.

    ``valid`` says the report could be produced, not what it decided: a `stop`
    is a successful measurement of a disappointing cohort, and a CI step that
    treated it as a crash would be reading the wrong field.
    """

    return {
        "valid": True,
        "verdict": report.verdict,
        "report_digest": report.report_digest,
        "records": len(report.records),
        "participants": report.participants,
        "criteria": {
            criterion.key: criterion.verdict for criterion in report.criteria
        },
        "report": None if destination is None else str(Path(destination).resolve()),
    }


__all__ = [
    "MEDIAN_SECONDS_THRESHOLD",
    "MINIMUM_COMPLETED_CYCLES",
    "MINIMUM_REPEAT_PARTICIPANTS",
    "Gate3Criterion",
    "Gate3Error",
    "Gate3Report",
    "build_gate3_report",
    "evaluate_gate3",
    "gate3_report_digest",
    "load_pilot_cohort",
    "render_gate3_report",
    "summarize_gate3_report",
    "write_gate3_report",
]
