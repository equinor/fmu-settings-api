"""Models for ERT configuration files."""

from typing import Annotated

from pydantic import Field, StringConstraints

from .common import BaseResponseModel

ERT_CONFIG_FILE_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.ert$"

ErtConfigFileName = Annotated[
    str,
    StringConstraints(pattern=ERT_CONFIG_FILE_NAME_PATTERN, max_length=255),
]
"""A plain .ert file name located directly in the project ert/model directory."""


class ErtConfigList(BaseResponseModel):
    """The ERT config files found in the project ert/model directory."""

    files: list[str]
    """File names of .ert files in ert/model."""


class ErtRmsProject(BaseResponseModel):
    """An RMS project in rms/model that can be used in an ERT config."""

    name: str
    """The RMS project directory name in rms/model, used as <RMS_NAME>."""

    version: str | None = None
    """The RMS version detected from the project's .master file, if possible."""

    error: str | None = None
    """Why the RMS version could not be detected, if it could not."""


class ErtRmsProjectList(BaseResponseModel):
    """The RMS projects in the project rms/model directory."""

    projects: list[ErtRmsProject]
    """RMS projects sorted by name."""


class ErtConfigContent(BaseResponseModel):
    """The content of an ERT config file."""

    content: str
    """The complete file content."""


class ErtConfigValidateRequest(ErtConfigContent):
    """Request to validate an ERT config as if saved with the given name."""

    name: ErtConfigFileName
    """The file name the config would be saved as in ert/model."""


class ErtConfigIssue(BaseResponseModel):
    """A single error or warning reported by ERT."""

    message: str
    """The message from ERT."""

    line: int | None = None
    """1-based line number, if known."""

    column: int | None = None
    """1-based column number, if known."""

    filename: str | None = None
    """The file the issue originated from, if known."""


class ErtConfigValidationResult(BaseResponseModel):
    """Result of validating an ERT config with ERT."""

    valid: bool
    """True if ERT reported no errors."""

    errors: list[ErtConfigIssue] = Field(default_factory=list)
    """Errors reported by ERT."""

    warnings: list[ErtConfigIssue] = Field(default_factory=list)
    """Warnings reported by ERT."""


class ErtConfigInvalidDetail(BaseResponseModel):
    """Detail returned when saving an ERT config that fails validation."""

    message: str
    """A summary of the failure."""

    validation: ErtConfigValidationResult
    """The validation result from ERT."""
