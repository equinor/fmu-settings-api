"""Dependencies injected into FastAPI."""

from fmu_settings_api.interfaces.smda_api import SmdaAPI

from .auth import AuthTokenDep
from .permissions import WritePermissionDep
from .project import ProjectServiceDep
from .session import (
    ProjectSessionDep,
    ProjectSessionNoExtendDep,
    ProjectSmdaSessionDep,
    SessionDep,
    SessionNoExtendDep,
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
    "ProjectSessionDep",
    "ProjectSessionNoExtendDep",
    "get_smda_session",
    "ProjectSmdaSessionDep",
    "SmdaInterfaceDep",
    "ProjectSmdaServiceDep",
    "SmdaServiceDep",
    "WritePermissionDep",
    "SmdaAPI",
    "ProjectServiceDep",
]
