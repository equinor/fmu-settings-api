"""Logging configuration using structlog."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

import structlog
from fmu.settings import Telemetry, configure_telemetry
from pydantic import ValidationError

if TYPE_CHECKING:
    from collections.abc import Callable

    from fmu_settings_api.config import APISettings


def attach_telemetry(telemetry: Telemetry) -> Callable[..., Any]:
    """Create a processor that forwards an event copy to telemetry."""

    def processor(
        logger: Any, method_name: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a copy of the event and return the original event."""
        telemetry_event = event_dict.copy()
        # Do not send the session ID to Azure because it is also the
        # authentication cookie and could give access to the active session.
        telemetry_event.pop("session_id", None)
        event = str(telemetry_event.pop("event", "unknown"))
        level_name = str(telemetry_event.pop("level", method_name)).upper()
        level = logging.getLevelNamesMapping().get(level_name, logging.INFO)
        exc_info = telemetry_event.pop("exc_info", None)

        telemetry.emit(
            event,
            level=level,
            exc_info=exc_info,
            **telemetry_event,
        )

        return event_dict

    return processor


def setup_telemetry(settings: APISettings, *, run_id: str | None = None) -> Telemetry:
    """Configure telemetry for the API."""
    return configure_telemetry(
        app_name=settings.APP_NAME,
        app_version=settings.APP_VERSION,
        environment=settings.environment,
        run_id=run_id,
        minimum_level=logging.INFO,
    )


def attach_fmu_settings_handler(
    log_manager: Any,
    entry_class: type[Any],
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
) -> Callable[..., Any]:
    """Create a processor that forwards logs to fmu-settings LogManager."""

    def processor(
        logger: Any, method_name: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        """Forward structured log to fmu-settings LogManager."""
        event_log_level = event_dict.get("level", "info").upper()
        log_level_scores = logging.getLevelNamesMapping()
        if log_level_scores.get(event_log_level, 0) >= log_level_scores.get(
            log_level, 0
        ):
            try:
                now_iso = datetime.now(UTC).isoformat()
                log_entry_data = {
                    "level": event_log_level,
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
    *,
    telemetry: Telemetry | None = None,
) -> None:
    """Configure structured logging with structlog."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=settings.log_level,
    )

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        attach_fmu_settings_handler(
            fmu_log_manager, log_entry_class, settings.log_level
        ),
    ]

    if telemetry is not None:
        processors.append(attach_telemetry(telemetry))

    if settings.log_format == "json" or settings.is_production:
        processors += [
            structlog.processors.ExceptionRenderer(),
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors += [
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            ),
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
