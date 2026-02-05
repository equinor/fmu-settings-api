"""Service for managing FMU project resource access."""

import json
from pathlib import Path
from typing import Any

from fmu.settings import CacheResource, ProjectFMUDirectory
from pydantic import BaseModel

from fmu_settings_api.logging import get_logger
from fmu_settings_api.models.resource import CacheContent, CacheList

logger = get_logger(__name__)


class ResourceService:
    """Service for handling project resource access."""

    _LIST_DIFF_KEYS: dict[str, str] = {
        "rms.zones": "name",
        "rms.horizons": "name",
        "rms.wells": "name",
        "masterdata.smda.country": "uuid",
        "masterdata.smda.discovery": "uuid",
        "masterdata.smda.field": "uuid",
        "stratigraphy.root": "__full__",
    }

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

    def get_cache_diff(
        self, resource: CacheResource, revision_id: str
    ) -> list[dict[str, object]]:
        """Get the diff between the current resource and a cache revision."""
        resource_path = Path(resource.value)
        manager = self._fmu_dir._cacheable_resource_managers().get(resource_path)
        if manager is None:
            raise ValueError(
                f"Resource '{resource.value}' is not supported for diff operations"
            )
        current_model = manager.load(force=True, store_cache=True)
        cached_model = self._fmu_dir.get_cache_content(resource_path, revision_id)

        changes = manager.get_model_diff(current_model, cached_model)
        results: list[dict[str, object]] = []
        for path, current, selected in changes:
            if path in self._LIST_DIFF_KEYS:
                list_key = self._LIST_DIFF_KEYS[path]
                list_diff = self._build_list_diff(current, selected, list_key)
                if list_diff is not None:
                    results.append({"field_path": path, **list_diff})
                    continue

            results.append(
                {
                    "field_path": path,
                    "updated": {
                        "before": self._dump_value(current),
                        "after": self._dump_value(selected),
                    },
                }
            )
        return results

    def _build_list_diff(
        self,
        current: Any | None,
        selected: Any | None,
        key_field: str,
    ) -> dict[str, object] | None:
        """Build a per-item diff for lists of dict-like items keyed by key_field."""
        current_items = current or []
        selected_items = selected or []

        def _get_key(item: Any) -> object:
            if key_field == "__full__":
                return json.dumps(self._dump_value(item), sort_keys=True, default=str)
            return getattr(item, key_field)

        current_map = {_get_key(item): item for item in current_items}
        selected_map = {_get_key(item): item for item in selected_items}

        current_keys = set(current_map)
        selected_keys = set(selected_map)

        added = [
            self._dump_value(item)
            for item in selected_items
            if _get_key(item) not in current_keys
        ]
        removed = [
            self._dump_value(item)
            for item in current_items
            if _get_key(item) not in selected_keys
        ]

        updated: list[dict[str, object]] = []
        for key_value in sorted(current_keys & selected_keys, key=str):
            if current_map[key_value] != selected_map[key_value]:
                updated.append(
                    {
                        "key": key_value,
                        "before": self._dump_value(current_map[key_value]),
                        "after": self._dump_value(selected_map[key_value]),
                    }
                )

        return {
            "added": added,
            "removed": removed,
            "updated": updated,
        }

    @staticmethod
    def _dump_value(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json", by_alias=True)
        return value

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
