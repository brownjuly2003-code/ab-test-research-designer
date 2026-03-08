from __future__ import annotations

from datetime import datetime, timezone
import json
import logging


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


def log_event(logger: logging.Logger, level: int, message: str, **fields: object) -> None:
    logger.log(level, message, extra={"fields": fields})
