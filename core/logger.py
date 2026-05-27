"""
Structured logging with rich console output and JSONL file logs.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from rich.logging import RichHandler
except Exception:  # pragma: no cover - rich is an optional runtime nicety
    RichHandler = None  # type: ignore[assignment]


_CONFIGURED = False


def _json_default(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    return repr(value)


class JsonLineFormatter(logging.Formatter):
    """Format log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        fields = getattr(record, "structured", {}) or {}
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
        }
        payload.update(fields)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=_json_default)


class StructuredLogger:
    """Small adapter that accepts structlog-style event + key fields."""

    def __init__(self, name: str, bound: dict[str, Any] | None = None) -> None:
        self._logger = logging.getLogger(name)
        self._bound = bound or {}

    def bind(self, **fields: Any) -> "StructuredLogger":
        merged = {**self._bound, **fields}
        return StructuredLogger(self._logger.name, merged)

    def _log(self, level: int, event: str, **fields: Any) -> None:
        exc_info = fields.pop("exc_info", None)
        payload = {**self._bound, **fields}
        self._logger.log(
            level,
            event,
            extra={"event": event, "structured": payload},
            exc_info=exc_info,
        )

    def debug(self, event: str, **fields: Any) -> None:
        self._log(logging.DEBUG, event, **fields)

    def info(self, event: str, **fields: Any) -> None:
        self._log(logging.INFO, event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._log(logging.WARNING, event, **fields)

    warn = warning

    def error(self, event: str, **fields: Any) -> None:
        self._log(logging.ERROR, event, **fields)

    def exception(self, event: str, **fields: Any) -> None:
        self._log(logging.ERROR, event, exc_info=True, **fields)


def setup_logging(logs_dir: str | Path = "data/logs", debug: bool = False) -> None:
    """Configure console and JSONL logging handlers."""
    global _CONFIGURED

    log_dir = Path(logs_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if debug else logging.INFO

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    if RichHandler is not None:
        console_handler: logging.Handler = RichHandler(
            rich_tracebacks=debug,
            show_path=False,
            markup=True,
        )
    else:
        console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(console_handler)

    file_handler = logging.FileHandler(
        log_dir / "home-llm.jsonl",
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JsonLineFormatter())
    root.addHandler(file_handler)

    for noisy in ("httpx", "chromadb", "urllib3", "googleapiclient"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> StructuredLogger:
    """Return a structured logger."""
    return StructuredLogger(name)
