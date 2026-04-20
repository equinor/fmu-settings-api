"""Models for mappings API responses."""

from uuid import UUID

from fmu.datamodels.context.mappings import DataSystem, MappingType, RelationType
from fmu.settings.models.mappings import MappingGroup
from pydantic import Field

from fmu_settings_api.models.common import BaseResponseModel


class IdentifierMappingResponse(BaseResponseModel):
    """A mapping entry exposed by the mappings API."""

    relation_type: RelationType
    """Relationship between the source identifier and the official identifier."""

    source_id: str
    """Identifier from the source system."""

    source_uuid: UUID | None = Field(default=None)
    """Optional UUID associated with the source identifier."""


class MappingGroupResponse(BaseResponseModel):
    """Mappings grouped by official target identifier for API responses."""

    official_name: str
    """Official target identifier shared by all mappings in the group."""

    target_uuid: UUID | None = Field(default=None)
    """Optional UUID associated with the official identifier."""

    mapping_type: MappingType
    """Kind of mapping represented by this group."""

    target_system: DataSystem
    """Target system that owns the official identifier."""

    source_system: DataSystem
    """Source system that owns the mapped identifiers."""

    mappings: list[IdentifierMappingResponse]
    """Mappings that point to the same official identifier."""

    @classmethod
    def from_mapping_group(cls, mapping_group: MappingGroup) -> "MappingGroupResponse":
        """Create an API response model from an internal MappingGroup."""
        return cls.model_validate(mapping_group.model_dump())
