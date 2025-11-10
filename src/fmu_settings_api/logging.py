"""Logging configuration using structlog."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from pydantic import ValidationError

if TYPE_CHECKING:
    from collections.abc import Callable

    from fmu_settings_api.config import APISettings


def attach_fmu_settings_handler(
    log_manager: Any,
    entry_class: type[Any],
) -> Callable[..., Any]:
    """Create a processor that forwards logs to fmu-settings LogManager."""

    def processor(
        logger: Any, method_name: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        """Forward structured log to fmu-settings LogManager."""
        try:
            now_iso = datetime.now(UTC).isoformat()
            log_entry_data = {
                "level": event_dict.get("level", "info").upper(),
                "event": event_dict.get("event", "unknown"),
                "timestamp": event_dict.get("timestamp") or now_iso,
                **{
                    k: v
                    for k, v in event_dict.items()
                    if k not in ["level", "event", "timestamp"]
                },
            }
            log_entry = entry_class.model_validate(log_entry_data)
            log_manager.add_log_entry(log_entry)
        except ValidationError as e:
            print(f"Failed to add log entry: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Unexpected logging error: {e}", file=sys.stderr)

        return event_dict

    return processor


def setup_logging(
    settings: APISettings,
    fmu_log_manager: Any,
    log_entry_class: type[Any],
) -> None:
    """Configure structured logging with structlog."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=settings.log_level,
    )

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    processors: list[Callable[..., Any]] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        attach_fmu_settings_handler(fmu_log_manager, log_entry_class),
    ]

    if settings.log_format == "json" or settings.is_production:
        processors += [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors += [
            structlog.processors.ExceptionRenderer(),
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)
