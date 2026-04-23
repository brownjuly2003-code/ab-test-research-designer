import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.logging_utils import configure_logging, log_event


def test_llm_token_is_masked_in_captured_logs(caplog) -> None:
    configure_logging(level="INFO", log_format="plain")
    logger = logging.getLogger("app.backend.tests.llm_logging")
    root_logger = logging.getLogger()
    token = "sk-live-super-secret-token"

    caplog.set_level(logging.INFO)
    root_logger.addHandler(caplog.handler)

    log_event(
        logger,
        logging.INFO,
        "request headers captured",
        headers={
            "X-AB-LLM-Provider": "openai",
            "X-AB-LLM-Token": token,
            "Authorization": f"Bearer {token}",
        },
    )
    logger.info("headers %s", {"X-AB-LLM-Token": token, "Authorization": f"Bearer {token}"})

    rendered = [
        record.getMessage()
        for record in caplog.records
    ] + [
        repr(getattr(record, "fields", {}))
        for record in caplog.records
    ]

    assert all(token not in entry for entry in rendered)
    assert any("***" in entry for entry in rendered)
