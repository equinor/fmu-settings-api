"""Validate an ERT config with ERT and the site plugins.

Standalone script, deliberately free of fmu-settings-api imports, so it can be run
with any Python interpreter that has ERT installed (e.g. Komodo):

    python validate_ert_config.py path/to/config.ert
    cat content.ert | python validate_ert_config.py path/to/config.ert --stdin
    python validate_ert_config.py --serve

The path is used to resolve relative paths and <CONFIG_PATH> in the config, so it
should be the location the config is (or will be) saved to, even if it does not
exist yet when --stdin is used.

In the single-shot modes the result is printed to stdout as a single line of JSON:
    {"valid": bool, "errors": [...], "warnings": [...]}
or {"valid": false, "unavailable": "<reason>", ...} if ERT cannot be imported.
Exit code is 0 if valid, 1 if invalid and 2 if ERT is unavailable.

With --serve, ERT and its plugins are loaded once, which takes most of the time,
and configs are then validated on request. The first stdout line is
{"ready": true} (or the "unavailable" result above). Then, for every request line
{"path": "...", "content": "..."} read from stdin, one result line is written.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import warnings
from pathlib import Path
from typing import Any, TextIO


def _info_to_dict(info: Any) -> dict[str, Any]:
    return {
        "message": str(getattr(info, "message", info)),
        "line": getattr(info, "line", None),
        "column": getattr(info, "column", None),
        "filename": getattr(info, "filename", None),
    }


class Validator:
    """Holds ERT and the site plugins, loaded once."""

    def __init__(self) -> None:
        """Import ERT and load the site plugins."""
        from ert.config import (  # type: ignore[import-not-found,unused-ignore]  # noqa: PLC0415, E501
            ConfigValidationError,
            ConfigWarning,
            ErtConfig,
        )
        from ert.plugins import (  # type: ignore[import-not-found,unused-ignore]  # noqa: PLC0415, E501
            get_site_plugins,
        )

        self._config_validation_error = ConfigValidationError
        self._config_warning = ConfigWarning
        self._ert_config = ErtConfig.with_plugins(get_site_plugins())

    def validate(self, contents: str, config_path: Path) -> dict[str, Any]:
        """Validate ERT config contents as if located at config_path."""
        errors: list[dict[str, Any]] = []
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", self._config_warning)
            try:
                self._ert_config.from_file_contents(contents, str(config_path))
            except self._config_validation_error as e:
                errors = [_info_to_dict(info) for info in e.errors]

        config_warnings = [
            _info_to_dict(getattr(w.message, "info", w.message))
            for w in caught
            if issubclass(w.category, self._config_warning)
        ]
        return {"valid": not errors, "errors": errors, "warnings": config_warnings}


def _load_validator() -> Validator | dict[str, Any]:
    try:
        return Validator()
    except ImportError as e:
        return {"valid": False, "unavailable": str(e), "errors": [], "warnings": []}


def _protocol_stdout() -> TextIO:
    """Reserve the real stdout for the JSON protocol.

    ERT and its plugins may print, also from native code, so file descriptor 1 is
    redirected to stderr and a private duplicate is used for the results.
    """
    sys.stdout.flush()
    protocol_fd = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return os.fdopen(protocol_fd, "w", encoding="utf-8", buffering=1)


def serve() -> int:
    """Load ERT once and validate configs requested on stdin."""
    out = _protocol_stdout()
    validator = _load_validator()
    if isinstance(validator, dict):
        out.write(json.dumps(validator) + "\n")
        return 2
    out.write(json.dumps({"ready": True}) + "\n")

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            result = validator.validate(
                request["content"], Path(request["path"]).resolve()
            )
        except Exception as e:  # noqa: BLE001
            result = {"error": f"{type(e).__name__}: {e}"}
        out.write(json.dumps(result) + "\n")
    return 0


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Validate an ERT config file.")
    parser.add_argument(
        "config", type=Path, nargs="?", help="Path of the ERT config file"
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read config contents from stdin instead of from the config path",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Load ERT once and validate JSON requests read line by line from stdin",
    )
    args = parser.parse_args()

    if args.serve:
        return serve()
    if args.config is None:
        parser.error("the config path is required unless --serve is used")

    config_path: Path = args.config.resolve()
    contents = (
        sys.stdin.read() if args.stdin else config_path.read_text(encoding="utf-8")
    )

    # ERT and its plugins may print; keep stdout reserved for the JSON result.
    with contextlib.redirect_stdout(sys.stderr):
        validator = _load_validator()
        result = (
            validator
            if isinstance(validator, dict)
            else validator.validate(contents, config_path)
        )

    print(json.dumps(result))
    if "unavailable" in result:
        return 2
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
