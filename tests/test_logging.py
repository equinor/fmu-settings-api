"""Tests for the logging module."""

import json
import logging
from datetime import UTC, datetime
from typing import Any, Final
from unittest.mock import MagicMock, patch

import structlog
from fmu.settings._init import init_user_fmu_directory
from fmu.settings._resources.user_session_log_manager import UserSessionLogManager
from fmu.settings.models.event_info import EventInfo

from fmu_settings_api.config import settings
from fmu_settings_api.logging import (
    attach_fmu_settings_handler,
    get_logger,
    setup_logging,
)


def test_attach_fmu_settings_handler_with_iso_timestamp() -> None:
    """Test handler with ISO string timestamp."""
    log_manager = MagicMock()
    entry_class = EventInfo
    log_level: Final = "INFO"
    processor = attach_fmu_settings_handler(log_manager, entry_class, log_level)

    event_dict = {
        "level": "info",
        "event": "test_event",
        "timestamp": datetime.now(UTC).isoformat(),
    }

    result = processor(None, "info", event_dict)

    assert result == event_dict
    log_manager.add_log_entry.assert_called_once()
    call_args = log_manager.add_log_entry.call_args[0][0]
    assert isinstance(call_args, EventInfo)
    assert call_args.level == "INFO"
    assert call_args.event == "test_event"
    assert call_args.timestamp.tzinfo is not None


def test_attach_fmu_settings_handler_without_timestamp() -> None:
    """Test handler auto-generates correct timestamp when not provided."""
    log_manager = MagicMock()
    entry_class = EventInfo
    log_level: Final = "INFO"
    processor = attach_fmu_settings_handler(log_manager, entry_class, log_level)

    before = datetime.now(UTC)
    event_dict = {"level": "warning", "event": "warning_event"}
    result = processor(None, "warning", event_dict)
    after = datetime.now(UTC)

    assert result == event_dict
    log_manager.add_log_entry.assert_called_once()
    call_args = log_manager.add_log_entry.call_args[0][0]
    assert isinstance(call_args, EventInfo)
    assert call_args.level == "WARNING"
    assert call_args.event == "warning_event"
    assert call_args.timestamp.tzinfo is not None
    assert before <= call_args.timestamp <= after


def test_attach_fmu_settings_handler_with_datetime_timestamp() -> None:
    """Test handler accepts datetime timestamp."""
    log_manager = MagicMock()
    entry_class = EventInfo
    log_level: Final = "INFO"
    processor = attach_fmu_settings_handler(log_manager, entry_class, log_level)

    now = datetime.now(UTC)
    event_dict = {"level": "error", "event": "error_event", "timestamp": now}

    result = processor(None, "error", event_dict)

    assert result == event_dict
    log_manager.add_log_entry.assert_called_once()
    call_args = log_manager.add_log_entry.call_args[0][0]
    assert isinstance(call_args, EventInfo)
    assert call_args.level == "ERROR"
    assert call_args.event == "error_event"


def test_attach_fmu_settings_handler_preserves_extra_fields() -> None:
    """Test handler preserves extra fields in log entry."""
    log_manager = MagicMock()
    entry_class = EventInfo
    log_level: Final = "DEBUG"
    processor = attach_fmu_settings_handler(log_manager, entry_class, log_level)

    event_dict = {
        "level": "debug",
        "event": "debug_event",
        "user_id": "12345",
        "request_id": "abc-def",
        "extra_data": {"key": "value"},
    }

    result = processor(None, "debug", event_dict)

    assert result == event_dict
    log_manager.add_log_entry.assert_called_once()
    call_args = log_manager.add_log_entry.call_args[0][0]
    assert isinstance(call_args, EventInfo)

    assert hasattr(call_args, "user_id")
    assert hasattr(call_args, "request_id")
    assert hasattr(call_args, "extra_data")


def test_attach_fmu_settings_handler_validation_error(capsys: Any) -> None:
    """Test handler gracefully handles validation errors."""
    log_manager = MagicMock()
    log_level: Final = "DEBUG"
    processor = attach_fmu_settings_handler(log_manager, EventInfo, log_level)

    event_dict = {
        "level": "info",
        "event": "test",
        "timestamp": "not-a-valid-timestamp",
    }

    result = processor(None, "info", event_dict)

    assert result == event_dict
    log_manager.add_log_entry.assert_not_called()
    captured = capsys.readouterr()
    assert "Failed to add log entry:" in captured.err


def test_attach_fmu_settings_handler_generic_exception(capsys: Any) -> None:
    """Test handler gracefully handles unexpected exceptions."""
    log_manager = MagicMock()
    log_manager.add_log_entry.side_effect = RuntimeError("Unexpected error")
    log_level: Final = "INFO"

    processor = attach_fmu_settings_handler(log_manager, EventInfo, log_level)

    event_dict = {"level": "info", "event": "test"}

    result = processor(None, "info", event_dict)

    assert result == event_dict
    captured = capsys.readouterr()
    assert "Unexpected logging error:" in captured.err


def test_attach_fmu_settings_handler_default_values() -> None:
    """Test handler uses default values for level and event."""
    log_manager = MagicMock()
    log_level: Final = "INFO"
    processor = attach_fmu_settings_handler(log_manager, EventInfo, log_level)

    event_dict: dict[str, Any] = {}

    result = processor(None, "info", event_dict)

    assert result == event_dict
    log_manager.add_log_entry.assert_called_once()
    call_args = log_manager.add_log_entry.call_args[0][0]
    assert call_args.level == "INFO"
    assert call_args.event == "unknown"


def test_attach_fmu_settings_handler_logs_on_severity() -> None:
    """Tests that handler logs according to the configured log level severity."""
    log_manager = MagicMock()
    entry_class = EventInfo

    now = datetime.now(UTC)
    event_dict_debug = {"level": "debug", "event": "debug_event", "timestamp": now}
    event_dict_info = {"level": "info", "event": "info_event", "timestamp": now}
    event_dict_warning = {
        "level": "warning",
        "event": "warning_event",
        "timestamp": now,
    }
    event_dict_error = {"level": "error", "event": "error_event", "timestamp": now}
    event_dict_critical = {
        "level": "critical",
        "event": "critical_event",
        "timestamp": now,
    }

    def process_event_and_assert_skipped_logging(
        event_type: str, event_dict: dict[str, Any]
    ) -> None:
        log_manager.reset_mock()
        processor(None, event_type, event_dict)
        log_manager.add_log_entry.assert_not_called()

    def process_event_and_assert_logging(
        event_type: str, event_dict: dict[str, Any]
    ) -> None:
        log_manager.reset_mock()
        processor(None, event_type, event_dict)
        log_manager.add_log_entry.assert_called_once()

    # Events with severity CRITICAL or higher should be logged
    log_level_critical: Final = "CRITICAL"
    processor = attach_fmu_settings_handler(
        log_manager, entry_class, log_level_critical
    )
    process_event_and_assert_skipped_logging("debug", event_dict_debug)
    process_event_and_assert_skipped_logging("info", event_dict_info)
    process_event_and_assert_skipped_logging("warning", event_dict_warning)
    process_event_and_assert_skipped_logging("error", event_dict_error)
    process_event_and_assert_logging("critical", event_dict_critical)

    # Events with severity WARNING or higher should be logged
    log_level_warning: Final = "WARNING"
    processor = attach_fmu_settings_handler(log_manager, entry_class, log_level_warning)
    process_event_and_assert_skipped_logging("debug", event_dict_debug)
    process_event_and_assert_skipped_logging("info", event_dict_info)
    process_event_and_assert_logging("warning", event_dict_warning)
    process_event_and_assert_logging("error", event_dict_error)
    process_event_and_assert_logging("critical", event_dict_critical)

    # Events with severity DEBUG or higher should be logged
    log_level_debug: Final = "DEBUG"
    processor = attach_fmu_settings_handler(log_manager, entry_class, log_level_debug)
    process_event_and_assert_logging("debug", event_dict_debug)
    process_event_and_assert_logging("info", event_dict_info)
    process_event_and_assert_logging("warning", event_dict_warning)
    process_event_and_assert_logging("error", event_dict_error)
    process_event_and_assert_logging("critical", event_dict_critical)


def test_setup_logging_configures_structlog() -> None:
    """Test setup_logging configures structlog properly."""
    log_manager = MagicMock()

    structlog.reset_defaults()

    setup_logging(settings, log_manager, EventInfo)

    logger = structlog.get_logger()
    assert logger is not None
    assert hasattr(logger, "info")
    assert hasattr(logger, "error")


def test_setup_logging_sets_log_levels() -> None:
    """Test setup_logging sets appropriate log levels for libraries."""
    log_manager = MagicMock()
    setup_logging(settings, log_manager, EventInfo)

    assert logging.getLogger("uvicorn.access").level == logging.WARNING
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_setup_logging_json_format_in_production() -> None:
    """Test setup_logging uses JSON format in production."""
    log_manager = MagicMock()
    original_env = settings.environment
    original_format = settings.log_format

    try:
        settings.environment = "production"
        settings.log_format = "console"

        structlog.reset_defaults()
        setup_logging(settings, log_manager, EventInfo)

        assert settings.is_production is True

    finally:
        settings.environment = original_env
        settings.log_format = original_format
        structlog.reset_defaults()


def test_setup_logging_console_format_in_development() -> None:
    """Test setup_logging uses console format in development."""
    log_manager = MagicMock()
    original_env = settings.environment
    original_format = settings.log_format

    try:
        settings.environment = "development"
        settings.log_format = "console"

        structlog.reset_defaults()
        setup_logging(settings, log_manager, EventInfo)

        assert settings.is_production is False

    finally:
        settings.environment = original_env
        settings.log_format = original_format
        structlog.reset_defaults()


def test_get_logger_returns_bound_logger() -> None:
    """Test get_logger returns a BoundLogger instance."""
    logger = get_logger("test_logger")
    assert logger is not None
    assert hasattr(logger, "info")
    assert hasattr(logger, "error")
    assert hasattr(logger, "debug")
    assert hasattr(logger, "warning")


def test_get_logger_with_different_names() -> None:
    """Test get_logger can create loggers with different names."""
    logger1 = get_logger("logger1")
    logger2 = get_logger("logger2")

    assert logger1 is not None
    assert logger2 is not None
    assert hasattr(logger1, "info")
    assert hasattr(logger2, "info")


def test_logging_writes_to_user_session_log_file(tmp_path: Any) -> None:
    """Integration test: verify logs are written to user_session_log.json."""
    mocked_user_home = tmp_path / "home"
    mocked_user_home.mkdir()

    with patch("pathlib.Path.home", return_value=mocked_user_home):
        user_fmu_dir = init_user_fmu_directory()
        log_manager = UserSessionLogManager(user_fmu_dir)

        original_log_level = settings.log_level
        original_log_format = settings.log_format
        settings.log_level = "INFO"
        settings.log_format = "json"

        structlog.reset_defaults()
        setup_logging(settings, log_manager, EventInfo)

        logger = get_logger("test_integration")
        logger.info("test_event_1", user_id="user123", action="login")
        logger.warning("test_event_2", error_code=404)
        logger.error("test_event_3", exception="ValueError")

        log_file = user_fmu_dir.path / "logs" / "user_session_log.json"
        assert log_file.exists()

        with open(log_file) as f:
            log_data = json.load(f)

        assert isinstance(log_data, list)
        expected_entry_count = 3
        assert len(log_data) >= expected_entry_count

        events = [entry["event"] for entry in log_data]
        assert "test_event_1" in events
        assert "test_event_2" in events
        assert "test_event_3" in events

        levels = [entry["level"] for entry in log_data]
        assert "INFO" in levels
        assert "WARNING" in levels
        assert "ERROR" in levels

        event_1 = next(e for e in log_data if e["event"] == "test_event_1")
        assert event_1.get("user_id") == "user123"
        assert event_1.get("action") == "login"

        for entry in log_data:
            assert "timestamp" in entry
            timestamp_str = entry["timestamp"]
            parsed_ts = datetime.fromisoformat(timestamp_str)
            assert parsed_ts.tzinfo is not None

        settings.log_level = original_log_level
        settings.log_format = original_log_format

    structlog.reset_defaults()
