"""
Structured logging configuration for VAULT Backend.
Supports JSON format for machine parsing and human-readable text format for local development.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """Formats log records as structured JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include standard extra attributes if attached to record
        for attr in ("request_id", "method", "path", "status_code", "duration_ms", "client_ip"):
            if hasattr(record, attr):
                log_obj[attr] = getattr(record, attr)

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


class TextFormatter(logging.Formatter):
    """Formats log records as clean readable text."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        extras = []
        for attr in ("request_id", "method", "path", "status_code", "duration_ms"):
            if hasattr(record, attr):
                extras.append(f"{attr}={getattr(record, attr)}")
        extra_str = f" [{', '.join(extras)}]" if extras else ""
        msg = f"[{timestamp}] [{record.levelname:<7}] [{record.name}] {record.getMessage()}{extra_str}"
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return msg


def setup_logging(log_level: str = "INFO", log_format: str = "json") -> logging.Logger:
    """Configures root and application loggers."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    if log_format.lower() == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(TextFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid duplicate handlers if setup_logging is invoked multiple times
    if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        root_logger.addHandler(handler)
    else:
        # Update formatter on existing stream handlers
        for h in root_logger.handlers:
            if isinstance(h, logging.StreamHandler):
                h.setFormatter(JSONFormatter() if log_format.lower() == "json" else TextFormatter())
                h.setLevel(level)

    app_logger = logging.getLogger("vault")
    app_logger.setLevel(level)
    return app_logger
