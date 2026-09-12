from __future__ import annotations

from typing import Any

import pytest

from app.backend.app.evidence.abx import _privacy_issues, _text_privacy_issues


@pytest.mark.parametrize(
    ("payload", "expected_message"),
    [
        ({"apiKey": "hello-secret"}, "secret-bearing field"),
        ({"APIKey": "hello-secret"}, "secret-bearing field"),
        ({"phoneNumber": 1_416_555_0123}, "detected numeric_identifier"),
        ({"contact": "+7 (916) 123-45-67"}, "detected phone_number"),
        ({"subjectId": 1_234_567}, "detected numeric_identifier"),
        ({"account_id": "0123456"}, "detected numeric_identifier"),
        ({"note": "call +14165550123"}, "detected phone_number"),
        ({"host": "192.0.2.44"}, "detected ipv4_address"),
        ({"host": "2001:db8::1"}, "detected ipv6_address"),
        ({"path": r"C:\Users\alice\data.csv"}, "detected absolute_path"),
        ({"path": "/opt/acme/data.csv"}, "detected absolute_path"),
        ({"path": "/Users/alice/data.csv"}, "detected absolute_path"),
    ],
    ids=(
        "camel-case-secret-key",
        "pascal-acronym-secret-key",
        "numeric-phone-field",
        "russian-phone-format",
        "numeric-subject-id",
        "numeric-account-id-string",
        "e164-phone-in-text",
        "ipv4-address",
        "compressed-ipv6-address",
        "windows-absolute-path",
        "generic-posix-absolute-path",
        "users-posix-absolute-path",
    ),
)
def test_privacy_scanner_rejects_adversarial_corpus(
    payload: dict[str, Any], expected_message: str
) -> None:
    messages = [message for _, message in _privacy_issues(payload)]

    assert any(expected_message in message for message in messages), messages


def test_privacy_scanner_ignores_bounded_non_sensitive_values() -> None:
    payload = {
        "apiKey": "",
        "subjectId": 123_456,
        "experimentNumber": 1_234_567,
        "relativePath": "reports/data.csv",
        "jsonPointer": "/preflight/findings/0",
        "htmlClosingTag": "</section>",
        "escapedHtmlClosingTag": "&lt;/section&gt;",
        "url": "https://example.test/opt/data.csv",
        "invalidIp": "999.999.999.999",
        "invalidIpv6": "2001:db8::not-an-ip",
        "ipv6LikeHostname": "2001:db8::1.example",
    }

    assert _privacy_issues(payload) == []


def test_privacy_scanner_rejects_long_numeric_values_in_sensitive_containers() -> None:
    payload = {
        "userIds": [999_999, 1_000_000],
        "accountNumber": 1_000_000.25,
    }

    assert _privacy_issues(payload) == [
        ("/userIds/1", "detected numeric_identifier in field 'userIds'"),
        ("/accountNumber", "detected numeric_identifier in field 'accountNumber'"),
    ]


def test_privacy_scanner_ignores_complete_sha256_digest_as_phone_number() -> None:
    digest = "sha256:60fee3fae970b607fec89bec8d6e8fc423d55a42f6d3f02b679436c281b694b3"

    assert _privacy_issues({"bundle_id": digest}) == []


def test_privacy_scanner_ignores_valid_git_commit_field_as_phone_number() -> None:
    commit = "73c97ee6838c5e85272879925d1c9512d1c3651b"

    assert _privacy_issues({"git_commit": commit}) == []
    assert _privacy_issues({"note": commit}) == [
        ("/note", "detected phone_number")
    ]


def test_privacy_scanner_ignores_digest_backed_run_ids() -> None:
    run_id = "run_decision_7fce32e85752211574c36881"

    assert _privacy_issues({"run_id": run_id}) == []
    assert _text_privacy_issues(f"<code>{run_id}</code>") == []


def test_privacy_scanner_ignores_embedded_digests_in_scanned_text() -> None:
    # This exact digest is the protocol_revision_id of examples/pilot/protocol.yaml;
    # it embeds "80493398107", which the Russian branch of the phone pattern reads as
    # a phone number. rendered/report.html is scanned as one text blob, so the
    # whole-value SHA256_RE guard never applies and publishing the bundle failed.
    digest = "sha256:ff307b009d4aae9d0f80493398107df55df7028abcaefd45626356a5cff13bd8"
    bare = digest.removeprefix("sha256:")

    assert _text_privacy_issues(f"<td>{digest}</td>") == []
    assert _text_privacy_issues(f"<td>{bare}</td>") == []
    assert _text_privacy_issues(f"SELECT 1 -- {bare}.sql") == []
    assert _privacy_issues({"note": f"bundle {digest} verified"}) == []


def test_privacy_scanner_still_reports_a_phone_number_beside_a_digest() -> None:
    digest = "sha256:ff307b009d4aae9d0f80493398107df55df7028abcaefd45626356a5cff13bd8"

    assert _text_privacy_issues(f"{digest} call +14165550123") == [
        ("", "detected phone_number")
    ]
