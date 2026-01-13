"""Tests for ResourceService."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fmu.settings import ProjectFMUDirectory

from fmu_settings_api.models.resource import CacheResource
from fmu_settings_api.services.resource import ResourceService


def test_get_cache_content_returns_valid_revision(fmu_dir: ProjectFMUDirectory) -> None:
    """Test cache content is returned for a valid revision."""
    service = ResourceService(fmu_dir)
    payload = {"example": True}
    revision_path = fmu_dir.cache.store_revision(
        Path("config.json"), json.dumps(payload)
    )
    assert revision_path is not None

    result = service.get_cache_content(CacheResource.config, revision_path.name)

    assert result.content == payload


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
    current_config = fmu_dir.config.load()
    updated_config = current_config.model_dump(mode="json")
    updated_config["cache_max_revisions"] = current_config.cache_max_revisions + 2

    revision_path = fmu_dir.cache.store_revision(
        Path("config.json"), json.dumps(updated_config)
    )
    assert revision_path is not None

    with (
        patch.dict(
            "fmu_settings_api.services.resource.RESOURCE_MODEL_MAP", {}, clear=True
        ),
        pytest.raises(ValueError, match="Unsupported cache resource"),
    ):
        service.restore_from_cache(CacheResource.config, revision_path.name)
