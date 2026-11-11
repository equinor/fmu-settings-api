"""Service for generating, validating and saving ERT config files."""

import asyncio
import contextlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import deque
from pathlib import Path
from typing import Any

from fmu.settings import ProjectFMUDirectory
from runrms.exceptions import RmsVersionError

from fmu_settings_api.logging import get_logger
from fmu_settings_api.models.ert import (
    ErtConfigValidationResult,
    ErtRmsProject,
    ErtRmsProjectList,
)
from fmu_settings_api.services.rms import RmsService

logger = get_logger(__name__)

VALIDATE_SCRIPT = (
    Path(__file__).resolve().parent.parent / "scripts" / "validate_ert_config.py"
)
ERT_PYTHON_ENV_VAR = "FMU_SETTINGS_ERT_PYTHON"
WORKER_STARTUP_TIMEOUT_SECONDS = 300
VALIDATION_TIMEOUT_SECONDS = 120
GUI_STARTUP_CHECK_SECONDS = 3
# Results can contain many errors, so allow long lines from the worker.
WORKER_STREAM_LIMIT_BYTES = 64 * 1024 * 1024


class ErtUnavailableError(RuntimeError):
    """Raised when no Python interpreter with ERT installed can be found."""


class ErtGuiStartError(RuntimeError):
    """Raised when the ERT GUI cannot be started."""


class ErtConfigInvalidError(ValueError):
    """Raised when saving an ERT config that fails validation."""

    def __init__(self, result: ErtConfigValidationResult) -> None:
        """Store the validation result."""
        super().__init__("ERT config is invalid")
        self.result = result


def _ert_executable_pythons() -> list[str]:
    """Interpreters of all `ert` executables on PATH, in PATH order."""
    pythons: list[str] = []
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        executable = Path(directory) / "ert"
        if not (executable.is_file() and os.access(executable, os.X_OK)):
            continue
        try:
            with open(executable, encoding="utf-8", errors="ignore") as f:
                shebang = f.readline().strip()
        except OSError:
            continue
        if shebang.startswith("#!") and len(shebang.split()) == 1:
            python = shebang[2:]
            if python not in pythons:
                pythons.append(python)
    return pythons


def _is_own_environment(python: str) -> bool:
    """Whether the interpreter belongs to the environment running the API."""
    return Path(python).parent.parent.resolve() == Path(sys.prefix).resolve()


def find_ert_python() -> str:
    """Find a Python interpreter with ERT and, preferably, its site plugins.

    In order of precedence:
      1. The FMU_SETTINGS_ERT_PYTHON environment variable.
      2. The interpreter of an `ert` executable on PATH outside the environment
         running the API, e.g. Komodo. This is preferred as an ERT installed in a
         development venv usually lacks site plugins such as fmu-dataio and semeio.
      3. The interpreter running the API, if it can import ERT.
    """
    if env_python := os.environ.get(ERT_PYTHON_ENV_VAR):
        return env_python
    for python in _ert_executable_pythons():
        if not _is_own_environment(python):
            return python
    if importlib.util.find_spec("ert") is not None:
        return sys.executable
    raise ErtUnavailableError(
        "ERT is not available. Run fmu-settings from an environment with ERT "
        f"installed, or set {ERT_PYTHON_ENV_VAR} to a Python interpreter with ERT."
    )


class ErtValidatorWorker:
    """A long-running validate_ert_config.py --serve process.

    Importing ERT and loading its site plugins takes most of the validation time,
    so this is done once per worker and reused for subsequent validations.
    Requests are handled one at a time. The worker is restarted if it dies, times
    out, or if the Python interpreter to use changes.
    """

    def __init__(self) -> None:
        """Initialize without starting a process."""
        self._proc: asyncio.subprocess.Process | None = None
        self._python: str | None = None
        self._lock = asyncio.Lock()
        self._stderr_tail: deque[str] = deque(maxlen=50)
        self._stderr_task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        """Whether a worker process is running."""
        return self._proc is not None and self._proc.returncode is None

    async def warm_up(self) -> None:
        """Start the worker in advance so the first validation is fast."""
        async with self._lock:
            await self._ensure_started(find_ert_python())

    async def validate(self, path: Path, content: str) -> dict[str, Any]:
        """Validate config content as if located at path."""
        python = find_ert_python()
        async with self._lock:
            await self._ensure_started(python)
            assert self._proc is not None and self._proc.stdin is not None
            logger.info("ert_validation_started", python=python, path=str(path))
            request = json.dumps({"path": str(path), "content": content}) + "\n"
            try:
                self._proc.stdin.write(request.encode("utf-8"))
                await self._proc.stdin.drain()
                data = await self._read_message(VALIDATION_TIMEOUT_SECONDS)
            except TimeoutError as e:
                await self._stop()
                raise TimeoutError("ERT config validation timed out") from e
            except (OSError, RuntimeError):
                await self._stop()
                raise
            if "error" in data:
                raise RuntimeError(f"ERT config validation failed: {data['error']}")
            return data

    async def close(self) -> None:
        """Stop the worker process."""
        async with self._lock:
            await self._stop()

    async def _ensure_started(self, python: str) -> None:
        if self.is_running and self._python == python:
            return
        await self._stop()

        logger.info("ert_validator_starting", python=python)
        self._stderr_tail.clear()
        self._proc = await asyncio.create_subprocess_exec(
            python,
            str(VALIDATE_SCRIPT),
            "--serve",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=WORKER_STREAM_LIMIT_BYTES,
        )
        self._python = python
        self._stderr_task = asyncio.create_task(self._drain_stderr(self._proc))

        try:
            ready = await self._read_message(WORKER_STARTUP_TIMEOUT_SECONDS)
        except TimeoutError as e:
            await self._stop()
            raise TimeoutError("Starting ERT for validation timed out") from e
        except RuntimeError:
            await self._stop()
            raise
        if "unavailable" in ready:
            await self._stop()
            raise ErtUnavailableError(f"ERT is not available: {ready['unavailable']}")
        logger.info("ert_validator_ready", python=python)

    async def _read_message(self, timeout: float) -> dict[str, Any]:
        assert self._proc is not None and self._proc.stdout is not None
        line = await asyncio.wait_for(self._proc.stdout.readline(), timeout=timeout)
        if not line:
            await asyncio.sleep(0.1)  # Let stderr be drained for the log.
            logger.error(
                "ert_validator_exited",
                returncode=self._proc.returncode,
                stderr="".join(self._stderr_tail)[-4000:],
            )
            raise RuntimeError("ERT config validation failed unexpectedly")
        try:
            data: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError as e:
            raise RuntimeError("ERT config validation failed unexpectedly") from e
        return data

    async def _drain_stderr(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stderr is not None
        while line := await proc.stderr.readline():
            self._stderr_tail.append(line.decode("utf-8", errors="replace"))

    async def _stop(self) -> None:
        proc, self._proc, self._python = self._proc, None, None
        if proc is not None and proc.returncode is None:
            if proc.stdin is not None:
                proc.stdin.close()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except TimeoutError:
                proc.kill()
                await proc.wait()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stderr_task
            self._stderr_task = None


ert_validator = ErtValidatorWorker()
"""Shared validator worker, so ERT is loaded once per API process."""


async def warm_up_ert_validator() -> None:
    """Start the shared validator worker, logging instead of raising on failure."""
    try:
        await ert_validator.warm_up()
    except Exception as e:  # noqa: BLE001
        logger.warning("ert_validator_warm_up_failed", error=str(e))


class ErtService:
    """Service for ERT config files in the project ert/model directory."""

    def __init__(self, fmu_dir: ProjectFMUDirectory) -> None:
        """Initialize the service with a project FMU directory."""
        self._fmu_dir = fmu_dir

    @property
    def model_dir(self) -> Path:
        """The ert/model directory of the project."""
        return self._fmu_dir.base_path / "ert" / "model"

    def config_path(self, name: str) -> Path:
        """Return the path of a config file in ert/model."""
        path = (self.model_dir / name).resolve()
        if path.parent != self.model_dir.resolve():
            raise ValueError(f"Invalid ERT config file name: {name}")
        return path

    def list_configs(self) -> list[str]:
        """List .ert files in ert/model."""
        if not self.model_dir.is_dir():
            return []
        return sorted(p.name for p in self.model_dir.glob("*.ert") if p.is_file())

    def list_rms_projects(self) -> ErtRmsProjectList:
        """List RMS projects in rms/model with their detected RMS versions."""
        projects = []
        for path in self._fmu_dir.find_rms_projects():
            try:
                version = RmsService.get_rms_version(path)
                projects.append(ErtRmsProject(name=path.name, version=version))
            except (FileNotFoundError, RmsVersionError) as e:
                projects.append(ErtRmsProject(name=path.name, error=str(e)))
        return ErtRmsProjectList(projects=projects)

    def read_config(self, name: str) -> str:
        """Read a config file from ert/model."""
        return self.config_path(name).read_text(encoding="utf-8")

    async def validate(self, name: str, content: str) -> ErtConfigValidationResult:
        """Validate config content with ERT as if saved as name in ert/model."""
        data = await ert_validator.validate(self.config_path(name), content)
        return ErtConfigValidationResult.model_validate(data)

    async def launch_gui(self, name: str) -> int:
        """Start `ert gui` for a saved config in ert/model and return its PID.

        ERT is started detached from the API, on the display of the API process,
        from the same Python interpreter used for validation. Output is written
        to a log file in the system temp directory.

        Raises:
            FileNotFoundError: If the config file does not exist.
            ErtUnavailableError: If ERT is not available.
            ErtGuiStartError: If there is no display or ERT exits immediately.
        """
        path = self.config_path(name)
        if not path.is_file():
            raise FileNotFoundError(f"{name} not found in ert/model")
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            raise ErtGuiStartError(
                "No display is available to the fmu-settings API, so the ERT GUI "
                "cannot be opened."
            )

        python = find_ert_python()
        env = os.environ.copy()
        # Make executables next to the ERT interpreter (e.g. Komodo) take
        # precedence, as ERT plugins look up executables on PATH.
        env["PATH"] = os.pathsep.join([str(Path(python).parent), env.get("PATH", "")])
        log_path = Path(tempfile.gettempdir()) / (
            f"fmu-settings-ert-gui-{os.getuid()}-{path.stem}-{int(time.time())}.log"
        )
        with open(log_path, "w", encoding="utf-8") as log:
            proc = subprocess.Popen(
                [python, "-m", "ert", "gui", str(path)],
                cwd=path.parent,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

        # Report errors from ERT exiting immediately, e.g. an unreadable config.
        for _ in range(GUI_STARTUP_CHECK_SECONDS * 10):
            if proc.poll() is not None:
                break
            await asyncio.sleep(0.1)
        if proc.returncode is not None:
            output = log_path.read_text(encoding="utf-8", errors="replace").strip()
            logger.error(
                "ert_gui_exited",
                returncode=proc.returncode,
                log=str(log_path),
                output=output[-2000:],
            )
            last_line = output.splitlines()[-1] if output else ""
            raise ErtGuiStartError(
                f"ERT GUI exited immediately (code {proc.returncode}). "
                f"{last_line} See {log_path}".strip()
            )

        logger.info("ert_gui_started", pid=proc.pid, path=str(path), log=str(log_path))
        return proc.pid

    async def save(self, name: str, content: str) -> ErtConfigValidationResult:
        """Validate and, if valid, atomically write the config to ert/model."""
        result = await self.validate(name, content)
        if not result.valid:
            raise ErtConfigInvalidError(result)

        path = self.config_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{name}.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            Path(tmp_name).chmod(0o664)
            Path(tmp_name).replace(path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        logger.info("ert_config_saved", path=str(path))
        return result
