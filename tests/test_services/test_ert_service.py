"""Tests for the ERT service."""

import os
import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fmu.settings import ProjectFMUDirectory
from runrms.exceptions import RmsVersionError

from fmu_settings_api.models.ert import ErtConfigValidationResult
from fmu_settings_api.services import ert as ert_module
from fmu_settings_api.services.ert import (
    ErtConfigInvalidError,
    ErtService,
    ErtUnavailableError,
    ErtValidatorWorker,
    find_ert_python,
)

VALID = ErtConfigValidationResult(valid=True)
INVALID = ErtConfigValidationResult.model_validate(
    {"valid": False, "errors": [{"message": "bad", "line": 1, "column": 1}]}
)


@pytest.fixture(autouse=True)
async def fresh_ert_validator() -> AsyncGenerator[ErtValidatorWorker]:
    """Use a fresh validator worker per test and stop it afterwards."""
    worker = ErtValidatorWorker()
    with patch.object(ert_module, "ert_validator", worker):
        yield worker
    await worker.close()


@pytest.fixture
def ert_service(fmu_dir: ProjectFMUDirectory) -> ErtService:
    """Returns an ErtService with an ert/model directory."""
    (fmu_dir.base_path / "ert" / "model").mkdir(parents=True, exist_ok=True)
    return ErtService(fmu_dir)


def _fake_worker(tmp_path: Path, body: str) -> Path:
    """Write a fake `--serve` worker. `body` handles each request line `req`."""
    script = tmp_path / "fake_worker.py"
    script.write_text(
        "import json, sys, time\n"
        f"open({str(tmp_path / 'starts')!r}, 'a').write('x')\n"
        "print(json.dumps({'ready': True}), flush=True)\n"
        "for line in sys.stdin:\n"
        "    req = json.loads(line)\n"
        + "".join(f"    {code}\n" for code in body.splitlines())
    )
    return script


def _starts(tmp_path: Path) -> int:
    starts = tmp_path / "starts"
    return len(starts.read_text()) if starts.exists() else 0


def test_list_and_read_configs(ert_service: ErtService) -> None:
    """Only .ert files in ert/model are listed."""
    (ert_service.model_dir / "b.ert").write_text("NUM_REALIZATIONS 1\n")
    (ert_service.model_dir / "a.ert").write_text("NUM_REALIZATIONS 2\n")
    (ert_service.model_dir / "notes.txt").write_text("x")
    assert ert_service.list_configs() == ["a.ert", "b.ert"]
    assert ert_service.read_config("a.ert") == "NUM_REALIZATIONS 2\n"


def test_config_path_rejects_traversal(ert_service: ErtService) -> None:
    """Names resolving outside ert/model are rejected."""
    with pytest.raises(ValueError, match="Invalid ERT config file name"):
        ert_service.config_path("../evil.ert")


def test_find_ert_python_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """The environment variable takes precedence."""
    monkeypatch.setenv(ert_module.ERT_PYTHON_ENV_VAR, "/some/python")
    assert find_ert_python() == "/some/python"


def _make_ert_executable(directory: Path, python: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    ert_exe = directory / "ert"
    ert_exe.write_text(f"#!{python}\nimport ert\n")
    ert_exe.chmod(0o755)
    return ert_exe


def test_find_ert_python_from_executable_shebang(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Uses the interpreter of the ert executable on PATH."""
    _make_ert_executable(tmp_path / "komodo", "/komodo/bin/python")
    monkeypatch.delenv(ert_module.ERT_PYTHON_ENV_VAR, raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "komodo"))
    with patch.object(ert_module.importlib.util, "find_spec", return_value=None):
        assert find_ert_python() == "/komodo/bin/python"


def test_find_ert_python_prefers_external_ert_over_own_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Prefers an ert outside the API environment, e.g. Komodo.

    An ert installed in the API environment usually lacks site plugins.
    """
    own_python = str(Path(sys.prefix) / "bin" / "python")
    _make_ert_executable(tmp_path / "venv", own_python)
    _make_ert_executable(tmp_path / "komodo", "/komodo/bin/python")
    monkeypatch.delenv(ert_module.ERT_PYTHON_ENV_VAR, raising=False)
    monkeypatch.setenv("PATH", f"{tmp_path / 'venv'}{os.pathsep}{tmp_path / 'komodo'}")
    with patch.object(ert_module.importlib.util, "find_spec", return_value=object()):
        assert find_ert_python() == "/komodo/bin/python"


def test_find_ert_python_falls_back_to_own_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The API interpreter is used if it is the only one with ERT."""
    _make_ert_executable(tmp_path / "venv", str(Path(sys.prefix) / "bin" / "python"))
    monkeypatch.delenv(ert_module.ERT_PYTHON_ENV_VAR, raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "venv"))
    with patch.object(ert_module.importlib.util, "find_spec", return_value=object()):
        assert find_ert_python() == sys.executable


def test_find_ert_python_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Raises when ERT cannot be found."""
    monkeypatch.delenv(ert_module.ERT_PYTHON_ENV_VAR, raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    with (
        patch.object(ert_module.importlib.util, "find_spec", return_value=None),
        pytest.raises(ErtUnavailableError),
    ):
        find_ert_python()


async def test_validate_reuses_worker(ert_service: ErtService, tmp_path: Path) -> None:
    """ERT is loaded once; subsequent validations reuse the worker process."""
    script = _fake_worker(
        tmp_path,
        "valid = 'abc' not in req['content']\n"
        "errors = [] if valid else [{'message': 'bad', 'line': 1, 'column': 1}]\n"
        "print(json.dumps({'valid': valid, 'errors': errors}), flush=True)",
    )
    with (
        patch.object(ert_module, "find_ert_python", return_value=sys.executable),
        patch.object(ert_module, "VALIDATE_SCRIPT", script),
    ):
        first = await ert_service.validate("a.ert", "NUM_REALIZATIONS 1\n")
        second = await ert_service.validate("a.ert", "NUM_REALIZATIONS abc\n")
    assert first.valid
    assert second == INVALID
    assert _starts(tmp_path) == 1


async def test_warm_up_starts_worker_once(tmp_path: Path) -> None:
    """Warming up starts the worker, and is a no-op when it is running."""
    script = _fake_worker(tmp_path, "pass")
    worker = ert_module.ert_validator
    with (
        patch.object(ert_module, "find_ert_python", return_value=sys.executable),
        patch.object(ert_module, "VALIDATE_SCRIPT", script),
    ):
        await ert_module.warm_up_ert_validator()
        await ert_module.warm_up_ert_validator()
    assert worker.is_running
    assert _starts(tmp_path) == 1
    await worker.close()
    assert not worker.is_running


async def test_warm_up_failure_is_logged_not_raised() -> None:
    """A failing warm-up does not raise."""
    with patch.object(
        ert_module, "find_ert_python", side_effect=ErtUnavailableError("no ert")
    ):
        await ert_module.warm_up_ert_validator()


async def test_validate_unavailable(ert_service: ErtService, tmp_path: Path) -> None:
    """The worker reporting ERT unavailable raises ErtUnavailableError."""
    script = tmp_path / "unavailable.py"
    script.write_text("import json; print(json.dumps({'unavailable': 'no ert'}))\n")
    with (
        patch.object(ert_module, "find_ert_python", return_value=sys.executable),
        patch.object(ert_module, "VALIDATE_SCRIPT", script),
        pytest.raises(ErtUnavailableError, match="no ert"),
    ):
        await ert_service.validate("a.ert", "")
    assert not ert_module.ert_validator.is_running


async def test_validate_restarts_crashed_worker(
    ert_service: ErtService, tmp_path: Path
) -> None:
    """A worker that dies raises RuntimeError and is restarted on the next call."""
    script = _fake_worker(tmp_path, "sys.exit(1)")
    with (
        patch.object(ert_module, "find_ert_python", return_value=sys.executable),
        patch.object(ert_module, "VALIDATE_SCRIPT", script),
    ):
        for _ in range(2):
            with pytest.raises(RuntimeError, match="failed unexpectedly"):
                await ert_service.validate("a.ert", "")
    assert _starts(tmp_path) == 2


async def test_validate_worker_error(ert_service: ErtService, tmp_path: Path) -> None:
    """An error reported by the worker raises RuntimeError but keeps the worker."""
    script = _fake_worker(
        tmp_path, "print(json.dumps({'error': 'KeyError: x'}), flush=True)"
    )
    with (
        patch.object(ert_module, "find_ert_python", return_value=sys.executable),
        patch.object(ert_module, "VALIDATE_SCRIPT", script),
        pytest.raises(RuntimeError, match="KeyError: x"),
    ):
        await ert_service.validate("a.ert", "")
    assert ert_module.ert_validator.is_running


async def test_validate_timeout_stops_worker(
    ert_service: ErtService, tmp_path: Path
) -> None:
    """A validation that times out stops the worker."""
    script = _fake_worker(tmp_path, "time.sleep(30)")
    with (
        patch.object(ert_module, "find_ert_python", return_value=sys.executable),
        patch.object(ert_module, "VALIDATE_SCRIPT", script),
        patch.object(ert_module, "VALIDATION_TIMEOUT_SECONDS", 0.5),
        pytest.raises(TimeoutError, match="timed out"),
    ):
        await ert_service.validate("a.ert", "")
    assert not ert_module.ert_validator.is_running


async def test_save_valid_writes_file(ert_service: ErtService) -> None:
    """A valid config is written to ert/model."""
    with patch.object(ert_service, "validate", AsyncMock(return_value=VALID)):
        result = await ert_service.save("new.ert", "NUM_REALIZATIONS 1\n")
    assert result.valid
    assert (ert_service.model_dir / "new.ert").read_text() == "NUM_REALIZATIONS 1\n"
    assert [p.name for p in ert_service.model_dir.iterdir()] == ["new.ert"]


async def test_save_invalid_does_not_write(ert_service: ErtService) -> None:
    """An invalid config is not written."""
    with (
        patch.object(ert_service, "validate", AsyncMock(return_value=INVALID)),
        pytest.raises(ErtConfigInvalidError) as exc_info,
    ):
        await ert_service.save("new.ert", "NUM_REALIZATIONS x\n")
    assert exc_info.value.result == INVALID
    assert not (ert_service.model_dir / "new.ert").exists()


def _ert_available() -> bool:
    try:
        find_ert_python()
    except ErtUnavailableError:
        return False
    return True


@pytest.mark.skipif(not _ert_available(), reason="ERT is not available")
async def test_validate_with_real_ert(ert_service: ErtService) -> None:
    """Validates real configs with ERT, without writing any files."""
    valid = await ert_service.validate("a.ert", "NUM_REALIZATIONS 1\n")
    assert valid.valid, valid

    invalid = await ert_service.validate("a.ert", "NUM_REALIZATIONS x\n")
    assert not invalid.valid
    assert ert_module.ert_validator.is_running
    assert invalid.errors[0].line == 1
    assert list(ert_service.model_dir.iterdir()) == []


def test_list_rms_projects_detects_versions(ert_service: ErtService) -> None:
    """RMS versions are detected per project; failures are reported, not raised."""
    rms_model = ert_service.model_dir.parent.parent / "rms" / "model"
    good = rms_model / "good.rms14.2.2"
    bad = rms_model / "bad"
    for project in (good, bad):
        project.mkdir(parents=True)
        (project / ".master").touch()
        (project / "rms.ini").touch()

    def fake_version(path: Path) -> str:
        if path.name == "bad":
            raise RmsVersionError("unsupported")
        return "14.2.2"

    with patch.object(ert_module.RmsService, "get_rms_version", fake_version):
        result = ert_service.list_rms_projects()

    assert [(p.name, p.version) for p in result.projects] == [
        ("bad", None),
        ("good.rms14.2.2", "14.2.2"),
    ]
    assert result.projects[0].error == "unsupported"
