from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
import logging
import re


SENSITIVE_HEADER_NAMES = {"authorization", "x-api-key", "x-ab-llm-token"}


def _mask_sensitive_text(value: str) -> str:
    masked_value = re.sub(r"(Bearer\s+)[^\s,;]+", r"\1***", value, flags=re.IGNORECASE)
    return re.sub(
        r"((?:Authorization|X-API-Key|X-AB-LLM-Token)\s*[:=]\s*)([^\s,;]+)",
        r"\1***",
        masked_value,
        flags=re.IGNORECASE,
    )


def sanitize_for_logging(value: object) -> object:
    if isinstance(value, str):
        return _mask_sensitive_text(value)
    if isinstance(value, Mapping):
        return {
            key: ("***" if isinstance(key, str) and key.lower() in SENSITIVE_HEADER_NAMES else sanitize_for_logging(item))
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(sanitize_for_logging(item) for item in value)
    if isinstance(value, list):
        return [sanitize_for_logging(item) for item in value]
    return value


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = sanitize_for_logging(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = sanitize_for_logging(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(sanitize_for_logging(item) for item in record.args)
            else:
                record.args = sanitize_for_logging(record.args)
        fields = getattr(record, "fields", None)
        if fields is not None:
            record.fields = sanitize_for_logging(fields)
        return True


class PlainStructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        base = f"{timestamp} {record.levelname} {record.name}: {record.getMessage()}"
        fields = getattr(record, "fields", {})
        if isinstance(fields, dict) and fields:
            rendered = " ".join(f"{key}={fields[key]!r}" for key in sorted(fields))
            return f"{base} {rendered}"
        return base


class JsonStructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        fields = getattr(record, "fields", {})
        if isinstance(fields, dict):
            payload.update(fields)
        return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def configure_logging(*, level: str, log_format: str) -> None:
    formatter: logging.Formatter
    if log_format == "json":
        formatter = JsonStructuredFormatter()
    else:
        formatter = PlainStructuredFormatter()

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logging.basicConfig(level=getattr(logging, level, logging.INFO), handlers=[handler], force=True)
    root_logger = logging.getLogger()
    root_logger.addFilter(SensitiveDataFilter())
    for configured_handler in root_logger.handlers:
        configured_handler.addFilter(SensitiveDataFilter())


def log_event(logger: logging.Logger, level: int, message: str, **fields: object) -> None:
    logger.log(level, message, extra={"fields": fields})
