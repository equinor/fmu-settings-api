"""Tests for ResourceService."""

import json
from collections.abc import Callable
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fmu.datamodels.context.mappings import DataSystem
from fmu.settings import (
    CacheResource,
    InternalMappings,
    InternalRelationType,
    InternalStratigraphyIdentifierMapping,
    InternalStratigraphyMappings,
    ProjectFMUDirectory,
)
from fmu.settings.models import ListFieldDiff
from fmu.settings.models.diff import ScalarFieldDiff

from fmu_settings_api.models.resource import MigrationBackupStatus
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


def test_get_cache_diff_returns_structured_scalar_diff(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test cache diff returns structured scalar before/after values."""
    service = ResourceService(fmu_dir)
    current_config = fmu_dir.config.load()
    updated_config = current_config.model_dump(mode="json")
    updated_value = current_config.cache_max_revisions + 1
    updated_config["cache_max_revisions"] = updated_value

    revision_path = fmu_dir.cache.store_revision(
        Path("config.json"), json.dumps(updated_config)
    )
    assert revision_path is not None

    result = service.get_cache_diff(CacheResource.config, revision_path.name)

    assert len(result) == 1
    diff = result[0]
    assert isinstance(diff, ScalarFieldDiff)
    assert diff.field_path == "cache_max_revisions"
    assert diff.before == current_config.cache_max_revisions
    assert diff.after == updated_value


def test_get_cache_diff_returns_mappings_list_diff(
    fmu_dir: ProjectFMUDirectory,
    make_stratigraphy_mapping: Callable[..., InternalStratigraphyIdentifierMapping],
    make_stratigraphy_mappings: Callable[[], InternalStratigraphyMappings],
) -> None:
    """Test cache diff returns added/removed changes for stratigraphy mappings."""
    service = ResourceService(fmu_dir)
    current_stratigraphy = make_stratigraphy_mappings()
    fmu_dir.mappings.update_internal_stratigraphy_mappings(current_stratigraphy)

    incoming_stratigraphy = InternalStratigraphyMappings(
        root=[
            current_stratigraphy[0],
            current_stratigraphy[2],
            current_stratigraphy[3],
            current_stratigraphy[4],
            make_stratigraphy_mapping(
                "TopNew",
                "TopViking",
                InternalRelationType.alias,
                source_system=DataSystem.rms,
                target_system=DataSystem.rms,
            ),
        ]
    )
    revision_path = fmu_dir.cache.store_revision(
        Path("mappings.json"),
        InternalMappings(stratigraphy=incoming_stratigraphy).model_dump_json(
            by_alias=True
        ),
    )
    assert revision_path is not None

    result = service.get_cache_diff(CacheResource.mappings, revision_path.name)

    assert len(result) == 1
    diff = result[0]
    assert isinstance(diff, ListFieldDiff)
    assert diff.field_path == "stratigraphy.root"
    assert len(diff.added) == 1
    assert len(diff.removed) == 1
    assert diff.updated == []
    assert diff.added[0]["source_id"] == "TopNew"
    assert diff.removed[0]["source_id"] == "TopVOLANTIS"


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


@pytest.mark.parametrize("available", [True, False])
def test_get_migration_backup_status_returns_backup_availability(
    available: bool,
) -> None:
    """Tests that the backup availability is returned as a status model."""
    fmu_dir = Mock(spec=ProjectFMUDirectory)
    fmu_dir.has_compatible_migration_backup.return_value = available
    service = ResourceService(fmu_dir)

    assert service.get_migration_backup_status() == MigrationBackupStatus(
        available=available
    )


def test_restore_latest_migration_backup_restores_and_logs_success() -> None:
    """Tests that the latest compatible backup is restored and logged."""
    fmu_dir = Mock(spec=ProjectFMUDirectory)
    service = ResourceService(fmu_dir)

    with patch("fmu_settings_api.services.resource.logger") as logger_mock:
        service.restore_latest_migration_backup()

    fmu_dir.restore_latest_compatible_migration_backup.assert_called_once_with()
    logger_mock.info.assert_called_once_with("migration_backup_restored")
    logger_mock.error.assert_not_called()


def test_restore_latest_migration_backup_without_backup_logs_and_raises() -> None:
    """Tests that a missing compatible backup is logged and raised again."""
    fmu_dir = Mock(spec=ProjectFMUDirectory)
    fmu_dir.restore_latest_compatible_migration_backup.side_effect = FileNotFoundError(
        "No compatible migration backup"
    )
    service = ResourceService(fmu_dir)

    with (
        patch("fmu_settings_api.services.resource.logger") as logger_mock,
        pytest.raises(FileNotFoundError, match="No compatible migration backup"),
    ):
        service.restore_latest_migration_backup()

    logger_mock.error.assert_called_once_with(
        "migration_backup_restore_failed", error="No compatible migration backup"
    )
    logger_mock.info.assert_not_called()


def test_get_cache_diff_unsupported_model(fmu_dir: ProjectFMUDirectory) -> None:
    """Test cache diff fails when resource mapping is missing."""
    service = ResourceService(fmu_dir)

    with (
        patch.object(fmu_dir, "_cacheable_resource_managers", return_value={}),
        pytest.raises(
            ValueError,
            match="Resource 'config.json' is not supported for diff operations",
        ),
    ):
        service.get_cache_diff(CacheResource.config, "missing.json")
