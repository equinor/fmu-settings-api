"""Service for managing FMU project resource access."""

from pathlib import Path

from fmu.settings import CacheResource, ProjectFMUDirectory

from fmu_settings_api.logging import get_logger
from fmu_settings_api.models.resource import CacheContent, CacheList

logger = get_logger(__name__)


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

        try:
            cached_model = self._fmu_dir.get_cache_content(resource_path, revision_id)
            return CacheContent(
                data=cached_model.model_dump(mode="json", by_alias=True)
            )
        except (FileNotFoundError, ValueError):
            raise

    def restore_from_cache(self, resource: CacheResource, revision_id: str) -> None:
        """Restore a resource file from a cache revision by overwriting it.

        The current state is cached before overwriting (when present) to enable undo.
        """
        resource_path = Path(resource.value)

        try:
            self._fmu_dir.restore_from_cache(resource_path, revision_id)
        except (FileNotFoundError, ValueError) as e:
            logger.error(
                "cache_restore_failed",
                resource=resource.value,
                revision_id=revision_id,
                error=str(e),
            )
            raise

        logger.info(
            "cache_revision_restored",
            resource=resource.value,
            revision_id=revision_id,
        )
