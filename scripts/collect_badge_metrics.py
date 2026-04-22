from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT_DIR / "badges" / "metrics.json"
DEFAULT_TEST_RESULTS = (
    ROOT_DIR / ".ci-artifacts" / "backend-junit.xml",
    ROOT_DIR / ".ci-artifacts" / "frontend-junit.xml",
    ROOT_DIR / "backend-junit.xml",
    ROOT_DIR / "frontend-junit.xml",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage", default="coverage-backend.json")
    parser.add_argument("--lighthouse", default=".lighthouseci/manifest.json")
    parser.add_argument("--test-results", action="append", default=[])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def resolve_path(raw_path: str | Path) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def badge(label: str, message: str, color: str) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "label": label,
        "message": message,
        "color": color,
    }


def placeholder_badge(label: str) -> dict[str, Any]:
    return badge(label, "n/a", "lightgrey")


def parse_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def junit_counts(element: ET.Element) -> tuple[int, int, int, int] | None:
    tests = parse_int(element.attrib.get("tests"))
    failures = parse_int(element.attrib.get("failures"))
    errors = parse_int(element.attrib.get("errors"))
    skipped = parse_int(element.attrib.get("skipped"))
    if None in (tests, failures, errors, skipped):
        return None
    return tests, failures, errors, skipped


def passed_from_junit(path: Path) -> int | None:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None

    counts = junit_counts(root)
    if counts is None and root.tag == "testsuites":
        totals = [junit_counts(child) for child in root.findall("./testsuite")]
        if totals:
            tests = sum(item[0] for item in totals if item is not None)
            failures = sum(item[1] for item in totals if item is not None)
            errors = sum(item[2] for item in totals if item is not None)
            skipped = sum(item[3] for item in totals if item is not None)
            counts = (tests, failures, errors, skipped)
    if counts is None:
        return None
    tests, failures, errors, skipped = counts
    return max(0, tests - failures - errors - skipped)


def passed_from_json(path: Path) -> int | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if isinstance(payload, dict):
        summary = payload.get("summary")
        if isinstance(summary, dict):
            for key in ("passed", "numPassedTests", "passedTests"):
                passed = parse_int(summary.get(key))
                if passed is not None:
                    return passed
        for key in ("passed", "numPassedTests", "passedTests"):
            passed = parse_int(payload.get(key))
            if passed is not None:
                return passed
    return None


def passed_from_text(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"(?P<passed>\d+)\s+passed", text)
    if not match:
        return None
    return int(match.group("passed"))


def passed_from_results(path: Path) -> int | None:
    if not path.exists():
        return None
    if path.suffix.lower() == ".xml":
        return passed_from_junit(path)
    if path.suffix.lower() == ".json":
        return passed_from_json(path)
    return passed_from_text(path)


def coverage_percent(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    totals = payload.get("totals") if isinstance(payload, dict) else None
    if not isinstance(totals, dict):
        return None
    display = totals.get("percent_covered_display")
    if display is not None:
        text = str(display).rstrip("%")
        if text.isdigit():
            return int(text)
    percent = parse_float(totals.get("percent_covered"))
    if percent is None:
        return None
    return round(percent)


def normalize_lighthouse_score(raw_score: Any) -> int | None:
    score = parse_float(raw_score)
    if score is None:
        return None
    if score <= 1:
        score *= 100
    return round(score)


def lighthouse_score(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, list):
        return None
    entries = [entry for entry in payload if isinstance(entry, dict)]
    if not entries:
        return None
    representative_entries = [entry for entry in entries if entry.get("isRepresentativeRun") is True]
    selected_entries = representative_entries or entries
    scores: list[int] = []
    for entry in selected_entries:
        summary = entry.get("summary")
        score = None
        if isinstance(summary, dict):
            score = normalize_lighthouse_score(summary.get("performance"))
        if score is None:
            json_path = entry.get("jsonPath")
            if json_path:
                report_path = Path(json_path)
                if not report_path.is_absolute():
                    report_path = path.parent / report_path
                try:
                    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    report_payload = None
                if isinstance(report_payload, dict):
                    categories = report_payload.get("categories")
                    if isinstance(categories, dict):
                        performance = categories.get("performance")
                        if isinstance(performance, dict):
                            score = normalize_lighthouse_score(performance.get("score"))
        if score is not None:
            scores.append(score)
    if not scores:
        return None
    return round(sum(scores) / len(scores))


def color_for_coverage(percent: int | None) -> str:
    if percent is None:
        return "lightgrey"
    if percent >= 80:
        return "green"
    if percent >= 60:
        return "yellow"
    return "red"


def color_for_lighthouse(score: int | None) -> str:
    if score is None:
        return "lightgrey"
    if score >= 90:
        return "green"
    if score >= 70:
        return "yellow"
    return "red"


def tests_badge(test_paths: list[Path]) -> dict[str, Any]:
    total_passed = 0
    found = False
    for path in test_paths:
        passed = passed_from_results(path)
        if passed is None:
            continue
        total_passed += passed
        found = True
    if not found:
        return placeholder_badge("tests")
    return badge("tests", f"{total_passed} passed", "green")


def main() -> int:
    args = parse_args()
    output_path = resolve_path(args.output)
    coverage_path = resolve_path(args.coverage)
    lighthouse_path = resolve_path(args.lighthouse)
    test_paths = [resolve_path(path) for path in args.test_results] if args.test_results else list(DEFAULT_TEST_RESULTS)

    metrics = {
        "tests": tests_badge(test_paths),
        "coverage": placeholder_badge("coverage"),
        "lighthouse": placeholder_badge("lighthouse"),
    }

    coverage = coverage_percent(coverage_path)
    if coverage is not None:
        metrics["coverage"] = badge("coverage", f"{coverage}%", color_for_coverage(coverage))

    lighthouse = lighthouse_score(lighthouse_path)
    if lighthouse is not None:
        metrics["lighthouse"] = badge("lighthouse", str(lighthouse), color_for_lighthouse(lighthouse))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    for label, payload in metrics.items():
        (output_path.parent / f"{label}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
