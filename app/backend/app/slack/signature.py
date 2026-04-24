import hashlib
import hmac
import time


def build_slack_signature(signing_secret: str, timestamp: str, body: bytes) -> str:
    base_string = b"v0:" + timestamp.encode("utf-8") + b":" + body
    digest = hmac.new(signing_secret.encode("utf-8"), base_string, hashlib.sha256).hexdigest()
    return f"v0={digest}"


def verify_slack_signature(
    *,
    signing_secret: str,
    timestamp: str | None,
    body: bytes,
    signature: str | None,
    now: int | None = None,
    tolerance_seconds: int = 300,
) -> bool:
    if not signing_secret or not timestamp or not signature:
        return False
    try:
        request_timestamp = int(timestamp)
    except ValueError:
        return False
    current_time = int(time.time() if now is None else now)
    if abs(current_time - request_timestamp) > tolerance_seconds:
        return False
    expected = build_slack_signature(signing_secret, timestamp, body)
    return hmac.compare_digest(expected, signature)
