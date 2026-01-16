"""Services the end points need to use."""

from fmu_settings_api.services.project import ProjectService
from fmu_settings_api.services.resource import ResourceService
from fmu_settings_api.services.smda import SmdaService

__all__ = ["ProjectService", "ResourceService", "SmdaService"]
