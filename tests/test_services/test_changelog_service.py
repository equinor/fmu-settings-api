"""Tests for ChangelogService."""

from fmu.settings import ProjectFMUDirectory
from fmu.settings.models.change_info import ChangeInfo
from fmu.settings.models.log import Log

from fmu_settings_api.services.changelog import ChangelogService


def test_get_changelog_returns_log(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test get_changelog returns a Log[ChangeInfo]."""
    service = ChangelogService(fmu_dir)

    result = service.get_changelog()

    assert isinstance(result, Log)


def test_get_changelog_contains_changeinfo_entries(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test get_changelog returns entries of type ChangeInfo."""
    service = ChangelogService(fmu_dir)

    result = service.get_changelog()

    for entry in result.root:
        assert isinstance(entry, ChangeInfo)
