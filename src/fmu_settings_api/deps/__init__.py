"""Dependencies injected into FastAPI."""

from fmu_settings_api.interfaces.smda_api import SmdaAPI

from .auth import AuthTokenDep
from .permissions import RefreshLockDep, WritePermissionDep
from .project import ProjectServiceDep
from .resource import ResourceServiceDep
from .session import (
    ProjectSessionDep,
    ProjectSessionNoExtendDep,
    ProjectSessionServiceDep,
    ProjectSessionServiceNoExtendDep,
    ProjectSmdaSessionDep,
    SessionDep,
    SessionNoExtendDep,
    SessionServiceDep,
    SessionServiceNoExtendDep,
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
    "SessionNoExtendDep",
    "SessionServiceDep",
    "SessionServiceNoExtendDep",
    "ProjectSessionDep",
    "ProjectSessionNoExtendDep",
    "ProjectSessionServiceDep",
    "ProjectSessionServiceNoExtendDep",
    "RefreshLockDep",
    "get_smda_session",
    "ProjectSmdaSessionDep",
    "SmdaInterfaceDep",
    "ProjectSmdaServiceDep",
    "SmdaServiceDep",
    "WritePermissionDep",
    "SmdaAPI",
    "ProjectServiceDep",
    "ResourceServiceDep",
]
