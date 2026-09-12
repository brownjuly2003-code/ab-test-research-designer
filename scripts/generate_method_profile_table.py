from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.backend.app.evidence.stats_kernel import AnalysisPlan, StatsKernelBuild
from app.backend.app.evidence.stats_kernel_abx import (
    METHOD_PROFILE_LAST_VERIFIED_COMMIT,
    MethodGuaranteeProfile,
    materialize_method_guarantee_profile,
)

README_PATH = REPO_ROOT / "README.md"
START_MARKER = "<!-- method-profile-table:start -->"
END_MARKER = "<!-- method-profile-table:end -->"
SECTION_ANCHOR = "## Statistical repertoire\n"


def _documentation_profile() -> MethodGuaranteeProfile:
    build = StatsKernelBuild(
        git_commit=METHOD_PROFILE_LAST_VERIFIED_COMMIT,
        build_digest="sha256:" + "b" * 64,
        dependency_lock_digest="sha256:" + "c" * 64,
    )
    return materialize_method_guarantee_profile(build, AnalysisPlan(alpha=0.05))


def render_method_profile_table() -> str:
    profile = _documentation_profile()
    error_control = profile.error_control
    asymptotics = profile.asymptotics
    reference = profile.numeric_contract.reference_implementation
    deviations = profile.numeric_contract.observed_max_deviation
    verification = profile.verification_evidence
    headers = (
        "| Supported method | Estimands (test / interval) | Error control | "
        "Asymptotic floor | Numeric reference | Determinism / allocation | "
        "Oracle evidence |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    )
    row = (
        f"| `{profile.method_id}` (`{profile.method_version}`) | "
        f"`{profile.test_estimand}` / `{profile.interval_estimand}` | "
        f"fixed horizon; {error_control.sidedness}; "
        f"α={error_control.nominal_alpha:g} (bundle-specific) | "
        f"n≥{asymptotics.min_n_per_arm}/arm; expected count≥"
        f"{asymptotics.min_expected_count} | "
        f"{reference.package} {reference.version}; max Δ(z/p/CI)="
        f"{deviations.test_statistic:.3e} / {deviations.p_value:.3e} / "
        f"{deviations.confidence_interval:.3e} | "
        f"closed form={str(profile.determinism.closed_form).lower()}; "
        f"equal allocation required={str(profile.assumptions.equal_allocation).lower()} | "
        f"`{verification.oracle_case_ids[0]}` @ "
        f"`{verification.last_verified_commit[:8]}` |"
    )
    return "\n".join((START_MARKER, *headers, row, END_MARKER))


def update_readme(readme: str) -> str:
    block = render_method_profile_table()
    has_start = START_MARKER in readme
    has_end = END_MARKER in readme
    if has_start != has_end:
        raise ValueError("README method-profile markers are incomplete")
    if has_start:
        before, remainder = readme.split(START_MARKER, 1)
        _, after = remainder.split(END_MARKER, 1)
        return before + block + after
    if readme.count(SECTION_ANCHOR) != 1:
        raise ValueError("README Statistical repertoire heading is missing or ambiguous")
    return readme.replace(SECTION_ANCHOR, SECTION_ANCHOR + "\n" + block + "\n", 1)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the README method guarantee table from the typed profile."
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    current = README_PATH.read_text(encoding="utf-8")
    updated = update_readme(current)
    if args.check:
        if updated != current:
            print("README method profile table is stale", file=sys.stderr)
            return 1
        return 0
    README_PATH.write_text(updated, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
