from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.slack.signature import build_slack_signature, verify_slack_signature


def test_verify_slack_signature_accepts_valid_request() -> None:
    body = b"token=ignored&team_id=T123&text=projects"
    timestamp = "1700000000"
    signature = build_slack_signature("signing-secret", timestamp, body)

    assert verify_slack_signature(
        signing_secret="signing-secret",
        timestamp=timestamp,
        body=body,
        signature=signature,
        now=1700000020,
    ) is True


def test_verify_slack_signature_rejects_replay() -> None:
    body = b"token=ignored&team_id=T123&text=projects"
    timestamp = "1700000000"
    signature = build_slack_signature("signing-secret", timestamp, body)

    assert verify_slack_signature(
        signing_secret="signing-secret",
        timestamp=timestamp,
        body=body,
        signature=signature,
        now=1700000601,
    ) is False


def test_verify_slack_signature_rejects_wrong_secret() -> None:
    body = b"token=ignored&team_id=T123&text=projects"
    timestamp = "1700000000"
    signature = build_slack_signature("other-secret", timestamp, body)

    assert verify_slack_signature(
        signing_secret="signing-secret",
        timestamp=timestamp,
        body=body,
        signature=signature,
        now=1700000020,
    ) is False


def test_verify_slack_signature_rejects_tampered_body() -> None:
    timestamp = "1700000000"
    signature = build_slack_signature("signing-secret", timestamp, b"text=projects")

    assert verify_slack_signature(
        signing_secret="signing-secret",
        timestamp=timestamp,
        body=b"text=status",
        signature=signature,
        now=1700000020,
    ) is False
