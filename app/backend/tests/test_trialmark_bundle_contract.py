from pathlib import Path

import pytest

from app.backend.app.evidence.abx import BUNDLE_MEDIA_TYPE, BUNDLE_SUFFIX
from app.backend.app.evidence.cli import _parser, main


def test_trialmark_bundle_contract_replaces_abx_cli_surface(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = _parser()

    assert BUNDLE_SUFFIX == ".tmk"
    assert BUNDLE_MEDIA_TYPE == "application/vnd.trialmark.bundle+zip"
    assert parser.prog == "trialmark"
    assert parser.description == "Run protocols and manage verifiable Trialmark bundles."

    with pytest.raises(SystemExit) as raised:
        main(["pack", str(tmp_path), "--out", str(tmp_path / "bundle.abx")])
    assert raised.value.code == 2
    assert "bundle path must use the .tmk suffix" in capsys.readouterr().err


def test_pack_accepts_uppercase_tmk_suffix(tmp_path: Path) -> None:
    assert main(["pack", str(tmp_path), "--out", str(tmp_path / "bundle.TMK")]) == 1


def test_verify_and_inspect_are_filename_agnostic(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = Path(__file__).parent / "fixtures" / "evidence" / "asos" / "bundles" / "d53f0e.tmk"
    for filename in ("partner-bundle.zip", "partner-bundle.TMK"):
        archive = tmp_path / filename
        archive.write_bytes(fixture.read_bytes())

        assert main(["verify", str(archive)]) == 0
        assert main(["inspect", str(archive)]) == 0

    assert "bundle path must use the .tmk suffix" not in capsys.readouterr().err
