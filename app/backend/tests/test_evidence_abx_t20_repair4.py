from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from app.backend.tests.test_evidence_abx_t09_deferred import _section

_REPO_ROOT = Path(__file__).resolve().parents[3]
# The whole package, because which submodule holds a comment is a refactoring
# detail and this file is about what the comments say, not where they live.
_ABX = "\n".join(
    source.read_text(encoding="utf-8")
    for source in sorted(
        (_REPO_ROOT / "app" / "backend" / "app" / "evidence" / "abx").glob("*.py")
    )
)
_ARCHITECTURE = (
    _REPO_ROOT / "docs" / "architecture" / "TRIALMARK_ARCHITECTURE.md"
).read_text(encoding="utf-8")
_ADR = (_REPO_ROOT / "docs" / "adr" / "0004-abx-container-and-integrity.md").read_text(
    encoding="utf-8"
)

_FLAT_SCAN_ARCHITECTURE = (
    "The stored central-directory offset is authenticated by the physical-layout "
    "scan (`_stored_offsets_match_physical_layout`)."
)
_FLAT_SCAN_ADR = (
    "The stored CD offset is authenticated by the physical-layout scan; see "
    "TRIALMARK_ARCHITECTURE.md §7.4."
)
_SECURITY_VALUE_ASYMMETRY = (
    "un-gating it would buy nothing and cost the same redundant diagnostic. "
    "The asymmetry is deliberate."
)
_WRONG_NONE_MECHANISM = (
    "When the scan locates none (_stored_central_directory_offset returns None) "
    "it returns True vacuously; the EOCD is malformed and the archive is "
    "rejected by the bounds checks below."
)
_DUPLICATE_SCAN_MESSAGE = (
    "un-gating them would only duplicate the message the layout scan already "
    "emits about that same field"
)


def _fold(text: str) -> str:
    cleaned = (
        text.replace("\u2013", "-").replace("\u2014", "-").replace("#", " ")
    )
    return " ".join(cleaned.split())


def _preceding_comment(source: str, needle: str) -> str:
    lines = source.splitlines()
    for index, line in enumerate(lines):
        if needle not in line or line.lstrip().startswith("#"):
            continue
        start = index
        while start > 0 and lines[start - 1].lstrip().startswith("#"):
            start -= 1
        assert start < index, f"no comment immediately before {needle!r}"
        return "\n".join(lines[start:index])
    raise AssertionError(f"missing code needle {needle!r}")


def _comment_block_containing(source: str, unique: str) -> str:
    lines = source.splitlines()
    for index, line in enumerate(lines):
        if unique not in line or not line.lstrip().startswith("#"):
            continue
        start = index
        while start > 0 and lines[start - 1].lstrip().startswith("#"):
            start -= 1
        end = index
        while end + 1 < len(lines) and lines[end + 1].lstrip().startswith("#"):
            end += 1
        return "\n".join(lines[start : end + 1])
    raise AssertionError(f"missing comment containing {unique!r}")


_SECTION_74 = _section(
    _ARCHITECTURE,
    "### 7.4 Archive safety",
    "### 7.5",
    "architecture §7.4",
)
_ADR_STORED_CD = _section(
    _ADR,
    "An empty `unbound_bindings` list does not mean every definition is bound.",
    "Embedded schema snapshots",
    "ADR 0004 stored CD offset",
)
_LOCATOR_COMMENT = _preceding_comment(_ABX, "zip64_locator[8:16]")
_DELETION_COMMENT = _comment_block_containing(
    _ABX, "zip64_record[36:44] is the stored CD offset"
)
_CLASSIC_COMMENT = _comment_block_containing(_ABX, "Classic EOCD CD offset")


def _assert_scan_qualification(text: str) -> None:
    folded = _fold(text)
    assert "when it can locate one" in folded
    assert "well-formed Zip64 trailer" in folded
    assert "classic EOCD bytes 16-20" in folded
    assert "vacuously true" in folded
    assert "surrounding EOCD/trailing-byte checks" in folded
    assert _FLAT_SCAN_ARCHITECTURE not in folded
    assert _FLAT_SCAN_ADR not in folded


def _assert_adr_stored_cd_is_pointer(text: str) -> None:
    folded = _fold(text)
    assert "TRIALMARK_ARCHITECTURE.md" in folded
    assert "§7.4" in folded
    assert "not restated here" in folded
    assert _FLAT_SCAN_ADR not in folded
    assert "when it can locate one" not in folded
    assert "vacuously true" not in folded


def _assert_locator_is_verdict_neutral(text: str) -> None:
    folded = _fold(text)
    assert "never the verdict" in folded
    assert "diagnostics only" in folded or "diagnostic coverage" in folded
    assert "_stored_offsets_match_physical_layout" in folded
    assert "reported by no other check" in folded
    assert "never suppresses the only check" in folded
    assert "test_forged_classic_eocd_cd_offset_on_zip64_archive_is_rejected" in folded
    assert "_layout_trusted" in folded
    assert "does not by itself distinguish" in folded
    assert _SECURITY_VALUE_ASYMMETRY not in folded
    assert _DUPLICATE_SCAN_MESSAGE not in folded
    assert "would only duplicate" not in folded
    assert "buy nothing and cost the same" not in folded
    assert "no other authenticator" not in folded


def _assert_none_case_names_eocd_search(text: str) -> None:
    folded = _fold(text)
    assert "_find_eocd_offset" in folded
    assert "well-formed classic EOCD" in folded
    assert "trailing window" in folded
    assert "vacuously" in folded
    assert "surrounding EOCD/trailing-byte checks" in folded
    assert _WRONG_NONE_MECHANISM not in folded
    assert "bounds checks below" not in folded


def test_architecture_74_qualifies_layout_scan_and_locator_diagnostics() -> None:
    _assert_scan_qualification(_SECTION_74)
    _assert_locator_is_verdict_neutral(_SECTION_74)


def test_adr_qualifies_stored_cd_offset_authentication() -> None:
    _assert_adr_stored_cd_is_pointer(_ADR_STORED_CD)


def test_abx_comments_state_verdict_neutral_locator_and_vacuous_none() -> None:
    _assert_locator_is_verdict_neutral(_LOCATOR_COMMENT)
    _assert_none_case_names_eocd_search(_DELETION_COMMENT)
    folded_classic = _fold(_CLASSIC_COMMENT)
    assert "never suppresses the only check" in folded_classic
    assert "test_forged_classic_eocd_cd_offset_on_zip64_archive_is_rejected" in folded_classic
    assert "_layout_trusted" in folded_classic
    assert "would only duplicate" not in folded_classic
    assert "no other authenticator" not in folded_classic
    assert "buy nothing and cost the same" not in folded_classic


@pytest.mark.parametrize(
    ("helper", "live_text", "inverted"),
    [
        pytest.param(
            _assert_scan_qualification,
            _SECTION_74,
            _FLAT_SCAN_ARCHITECTURE,
            id="flat-scan-architecture",
        ),
        pytest.param(
            _assert_adr_stored_cd_is_pointer,
            _ADR_STORED_CD,
            _FLAT_SCAN_ADR,
            id="flat-scan-adr",
        ),
        pytest.param(
            _assert_locator_is_verdict_neutral,
            _LOCATOR_COMMENT,
            _SECURITY_VALUE_ASYMMETRY,
            id="security-value-asymmetry",
        ),
        pytest.param(
            _assert_none_case_names_eocd_search,
            _DELETION_COMMENT,
            _WRONG_NONE_MECHANISM,
            id="wrong-none-mechanism",
        ),
        pytest.param(
            _assert_locator_is_verdict_neutral,
            _SECTION_74,
            _DUPLICATE_SCAN_MESSAGE,
            id="duplicate-scan-message-architecture",
        ),
        pytest.param(
            _assert_locator_is_verdict_neutral,
            _LOCATOR_COMMENT,
            _DUPLICATE_SCAN_MESSAGE,
            id="duplicate-scan-message-locator",
        ),
    ],
)
def test_docs_guard_rejects_overstated_offset_claims(
    helper: Callable[[str], None], live_text: str, inverted: str
) -> None:
    with pytest.raises(AssertionError):
        helper(live_text + "\n\n" + inverted)
