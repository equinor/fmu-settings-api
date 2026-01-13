"""Service for managing FMU project resource access."""

import json
from pathlib import Path

from fmu.settings import ProjectFMUDirectory
from fmu.settings.models.project_config import ProjectConfig
from pydantic import BaseModel, ValidationError

from fmu_settings_api.logging import get_logger
from fmu_settings_api.models.resource import (
    CacheContent,
    CacheList,
    CacheResource,
)

logger = get_logger(__name__)

RESOURCE_MODEL_MAP: dict[CacheResource, type[BaseModel]] = {
    CacheResource.config: ProjectConfig,
}


class ResourceService:
    """Service for handling project resource access."""

    def __init__(self, fmu_dir: ProjectFMUDirectory) -> None:
        """Initialize the service with a project FMU directory."""
        self._fmu_dir = fmu_dir

    @property
    def fmu_dir_path(self) -> Path:
        """Returns the path to the .fmu directory."""
        return self._fmu_dir.path

    def list_cache_revisions(self, resource: CacheResource) -> CacheList:
        """List all cache revisions for a specific resource from oldest to newest."""
        resource_path = Path(resource.value)
        revision_paths = self._fmu_dir.cache.list_revisions(resource_path)
        return CacheList(revisions=[path.name for path in revision_paths])

    def get_cache_content(
        self, resource: CacheResource, revision_id: str
    ) -> CacheContent:
        """Get the content of a specific cache revision."""
        resource_path = Path(resource.value)

        cache_relative = Path("cache") / resource_path.stem / revision_id
        if not self._fmu_dir.file_exists(cache_relative):
            raise FileNotFoundError(
                f"Cache revision '{revision_id}' not found for "
                f"resource '{resource.value}'"
            )

        content_str = self._fmu_dir.read_text_file(cache_relative)

        try:
            content_dict = json.loads(content_str)
        except json.JSONDecodeError as e:
            logger.error(
                "cache_revision_json_parse_failed",
                revision_id=revision_id,
                resource=resource.value,
                error=str(e),
            )
            raise ValueError(f"Invalid JSON in cache revision: {e}") from e

        return CacheContent(content=content_dict)

    def restore_from_cache(self, resource: CacheResource, revision_id: str) -> None:
        """Restore a resource file from a cache revision by overwriting it.

        The current state is cached before overwriting (when present) to enable undo.
        """
        revision = self.get_cache_content(resource, revision_id)

        resource_path = Path(resource.value)

        # Cache current state before overwriting (when present).
        try:
            current_content = self._fmu_dir.read_text_file(resource_path)
        except FileNotFoundError:
            current_content = None
        if current_content is not None:
            self._fmu_dir.cache.store_revision(resource_path, current_content)

        # Validate cache content, serialize, and refresh cached in-memory resource
        try:
            model = self._get_resource_model(resource).model_validate(revision.content)
        except ValidationError as e:
            raise ValueError(
                f"Invalid cached content for '{resource.value}': {e}"
            ) from e
        content_str = model.model_dump_json(by_alias=True, indent=2)
        self._fmu_dir.write_text_file(resource_path, content_str)
        self._refresh_resource_cache(resource)

        logger.info(
            "cache_revision_restored",
            resource=resource.value,
            revision_id=revision_id,
        )

    def _get_resource_model(self, resource: CacheResource) -> type[BaseModel]:
        """Resolve the validation model for a cached resource."""
        try:
            return RESOURCE_MODEL_MAP[resource]
        except KeyError as e:
            raise ValueError(f"Unsupported cache resource '{resource.value}'") from e

    def _refresh_resource_cache(self, resource: CacheResource) -> None:
        """Refresh cached in-memory resources after restore."""
        if resource is CacheResource.config:
            self._fmu_dir.config.load(force=True, store_cache=True)
