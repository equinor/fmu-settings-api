"""Routes for generating, validating and saving ERT config files."""

from collections.abc import Awaitable
from textwrap import dedent
from typing import Annotated, Final, TypeVar

from fastapi import APIRouter, BackgroundTasks, HTTPException, Path as PathParam

from fmu_settings_api.deps import RefreshLockDep, WritePermissionDep
from fmu_settings_api.deps.ert import ErtServiceDep
from fmu_settings_api.models import Message
from fmu_settings_api.models.ert import (
    ERT_CONFIG_FILE_NAME_PATTERN,
    ErtConfigContent,
    ErtConfigInvalidDetail,
    ErtConfigList,
    ErtConfigValidateRequest,
    ErtConfigValidationResult,
    ErtRmsProjectList,
)
from fmu_settings_api.services.ert import (
    ErtConfigInvalidError,
    ErtGuiStartError,
    ErtUnavailableError,
    warm_up_ert_validator,
)
from fmu_settings_api.v1.responses import (
    GetSessionResponses,
    Responses,
    inline_add_response,
)

from .project import LockConflictResponses, ProjectResponses

router = APIRouter(prefix="/project/ert", tags=["ert"])

T = TypeVar("T")

ConfigName = Annotated[
    str, PathParam(pattern=ERT_CONFIG_FILE_NAME_PATTERN, max_length=255)
]

ErtValidationResponses: Final[Responses] = {
    **inline_add_response(
        503,
        "ERT is not available in the environment running fmu-settings.",
        [{"detail": "ERT is not available. ..."}],
    ),
    **inline_add_response(
        504,
        "ERT config validation timed out.",
        [{"detail": "ERT config validation timed out"}],
    ),
}


async def _run(coro: Awaitable[T]) -> T:
    try:
        return await coro
    except ErtUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get(
    "/configs",
    response_model=ErtConfigList,
    summary="Lists the ERT config files in the project ert/model directory",
    description=dedent(
        """
        Lists the ERT config files in the project ert/model directory. Also starts
        the ERT validator in the background, if not already running, so that
        subsequent validations are fast.
        """
    ),
    responses={**GetSessionResponses, **ProjectResponses},
)
async def get_ert_configs(
    ert_service: ErtServiceDep, background_tasks: BackgroundTasks
) -> ErtConfigList:
    """Lists the ERT config files in the project ert/model directory."""
    background_tasks.add_task(warm_up_ert_validator)
    return ErtConfigList(files=ert_service.list_configs())


@router.get(
    "/rms_projects",
    response_model=ErtRmsProjectList,
    summary="Lists the RMS projects in rms/model with their RMS versions",
    description=dedent(
        """
        Lists the RMS projects in the project rms/model directory, with the RMS
        version detected from each project's .master file. If the version cannot
        be detected, `version` is null and `error` describes why.
        """
    ),
    responses={**GetSessionResponses, **ProjectResponses},
)
async def get_ert_rms_projects(ert_service: ErtServiceDep) -> ErtRmsProjectList:
    """Lists the RMS projects in rms/model with their RMS versions."""
    try:
        return ert_service.list_rms_projects()
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail="Permission denied while scanning for RMS projects.",
        ) from e


@router.get(
    "/configs/{name}",
    response_model=ErtConfigContent,
    summary="Returns the content of an ERT config file in ert/model",
    responses={
        **GetSessionResponses,
        **ProjectResponses,
        **inline_add_response(
            404, "The config file does not exist", [{"detail": "{name} not found"}]
        ),
    },
)
async def get_ert_config(
    ert_service: ErtServiceDep, name: ConfigName
) -> ErtConfigContent:
    """Returns the content of an ERT config file in ert/model."""
    try:
        return ErtConfigContent(content=ert_service.read_config(name))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"{name} not found") from e


@router.post(
    "/validate",
    response_model=ErtConfigValidationResult,
    summary="Validates an ERT config with ERT without saving it",
    description=dedent(
        """
        Validates the ERT config content with ERT and the installed site plugins,
        as if it was saved with the given name in the project ert/model directory.
        Relative paths in the config are resolved from that location.
        Validation runs ERT in a separate process and may take some time.
        """
    ),
    responses={**GetSessionResponses, **ProjectResponses, **ErtValidationResponses},
)
async def post_validate_ert_config(
    ert_service: ErtServiceDep, request: ErtConfigValidateRequest
) -> ErtConfigValidationResult:
    """Validates an ERT config with ERT without saving it."""
    return await _run(ert_service.validate(request.name, request.content))


@router.put(
    "/configs/{name}",
    response_model=ErtConfigValidationResult,
    dependencies=[WritePermissionDep, RefreshLockDep],
    summary="Validates and saves an ERT config file to ert/model",
    description=dedent(
        """
        Validates the ERT config content with ERT and, if valid, writes it to the
        project ert/model directory, replacing any existing file with the same
        name. If ERT reports errors, nothing is written and 422 is returned with
        the validation result.
        """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
        **LockConflictResponses,
        **ErtValidationResponses,
        422: {
            "description": "The ERT config failed validation",
            "model": ErtConfigInvalidDetail,
        },
    },
)
async def put_ert_config(
    ert_service: ErtServiceDep, name: ConfigName, config: ErtConfigContent
) -> ErtConfigValidationResult:
    """Validates and saves an ERT config file to ert/model."""
    try:
        return await _run(ert_service.save(name, config.content))
    except ErtConfigInvalidError as e:
        raise HTTPException(
            status_code=422,
            detail=ErtConfigInvalidDetail(
                message="The ERT config is invalid and was not saved",
                validation=e.result,
            ).model_dump(),
        ) from e


@router.post(
    "/configs/{name}/gui",
    response_model=Message,
    summary="Opens a saved ERT config in the ERT GUI",
    description=dedent(
        """
        Starts `ert gui` for the saved config file in the project ert/model
        directory. ERT is started on the machine and display running the API,
        using the same ERT as for validation. Unsaved changes are not included.
        """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
        **inline_add_response(
            404, "The config file does not exist", [{"detail": "{name} not found"}]
        ),
        **inline_add_response(
            500,
            "The ERT GUI could not be started",
            [{"detail": "ERT GUI exited immediately (code 1). ..."}],
        ),
        **inline_add_response(
            503,
            "ERT or a display is not available to the API",
            [{"detail": "ERT is not available. ..."}],
        ),
    },
)
async def post_open_ert_gui(ert_service: ErtServiceDep, name: ConfigName) -> Message:
    """Opens a saved ERT config in the ERT GUI."""
    try:
        pid = await ert_service.launch_gui(name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"{name} not found") from e
    except ErtUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ErtGuiStartError as e:
        status = 503 if "No display" in str(e) else 500
        raise HTTPException(status_code=status, detail=str(e)) from e
    return Message(message=f"Started the ERT GUI for {name} (pid {pid})")
