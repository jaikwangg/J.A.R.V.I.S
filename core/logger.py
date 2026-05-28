"""
core/logger.py
──────────────
Structured logging — console (rich) + file (JSON Lines)
ไม่ log audio content หรือ sensitive data เด็ดขาด
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import structlog
from rich.console import Console
from rich.logging import RichHandler

_console = Console(stderr=True)


def _drop_sensitive_fields(
    logger: Any, method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """ลบ field ที่อาจมี sensitive data ก่อน log"""
    for key in ("audio", "audio_data", "embedding", "raw_audio", "password", "token"):
        event_dict.pop(key, None)
    return event_dict


def setup_logging(log_dir: Path, debug: bool = False) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "home-llm.jsonl"
    level = logging.DEBUG if debug else logging.INFO

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)

    console_handler = RichHandler(
        console=_console,
        show_time=True,
        show_path=debug,
        rich_tracebacks=True,
        markup=True,
    )
    console_handler.setLevel(level)

    logging.basicConfig(
        level=level,
        handlers=[console_handler, file_handler],
        format="%(message)s",
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _drop_sensitive_fields,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=False),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.ExceptionPrettyPrinter(),   # FIX: dict_tracebacks ไม่มีใน API
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)
