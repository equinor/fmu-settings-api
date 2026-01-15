"""Tests for ResourceService."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fmu.settings import CacheResource, ProjectFMUDirectory

from fmu_settings_api.services.resource import ResourceService


def test_get_cache_content_returns_valid_revision(fmu_dir: ProjectFMUDirectory) -> None:
    """Test cache content is returned for a valid revision."""
    service = ResourceService(fmu_dir)
    payload = fmu_dir.config.load().model_dump(mode="json")
    revision_path = fmu_dir.cache.store_revision(
        Path("config.json"), json.dumps(payload)
    )
    assert revision_path is not None

    result = service.get_cache_content(CacheResource.config, revision_path.name)

    assert result.data == payload


def test_restore_from_cache_updates_config(fmu_dir: ProjectFMUDirectory) -> None:
    """Test restoring a cache revision updates the config."""
    service = ResourceService(fmu_dir)
    current_config = fmu_dir.config.load()
    updated_config = current_config.model_dump(mode="json")
    updated_config["cache_max_revisions"] = current_config.cache_max_revisions + 1

    revision_path = fmu_dir.cache.store_revision(
        Path("config.json"), json.dumps(updated_config)
    )
    assert revision_path is not None

    service.restore_from_cache(CacheResource.config, revision_path.name)

    assert (
        fmu_dir.config.load(force=True).cache_max_revisions
        == updated_config["cache_max_revisions"]
    )


def test_restore_from_cache_unsupported_model(fmu_dir: ProjectFMUDirectory) -> None:
    """Test restore fails when resource mapping is missing."""
    service = ResourceService(fmu_dir)

    with (
        patch.object(fmu_dir, "_cacheable_resource_managers", return_value={}),
        pytest.raises(
            ValueError,
            match="Resource 'config.json' is not supported for cache restoration",
        ),
    ):
        service.restore_from_cache(CacheResource.config, "missing.json")
