"""Dependencies injected into FastAPI."""

from fmu_settings_api.interfaces.smda_api import SmdaAPI

from .auth import AuthTokenDep
from .permissions import RefreshLockDep, WritePermissionDep
from .project import ProjectRestoreServiceDep, ProjectServiceDep
from .resource import ResourceServiceDep
from .session import (
    ProjectSessionDep,
    ProjectSessionServiceDep,
    ProjectSmdaSessionDep,
    SessionDep,
    SessionServiceDep,
    get_session,
    get_smda_session,
)
from .smda import (
    ProjectSmdaServiceDep,
    SmdaInterfaceDep,
    SmdaServiceDep,
)
from .user_fmu import UserFMUDirDep

__all__ = [
    "AuthTokenDep",
    "UserFMUDirDep",
    "get_session",
    "SessionDep",
    "SessionServiceDep",
    "ProjectSessionDep",
    "ProjectSessionServiceDep",
    "RefreshLockDep",
    "get_smda_session",
    "ProjectSmdaSessionDep",
    "SmdaInterfaceDep",
    "ProjectSmdaServiceDep",
    "SmdaServiceDep",
    "WritePermissionDep",
    "SmdaAPI",
    "ProjectServiceDep",
    "ProjectRestoreServiceDep",
    "ResourceServiceDep",
]
