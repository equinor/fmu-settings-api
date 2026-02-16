"""Tests for ChangelogService."""

from fmu.settings import ProjectFMUDirectory
from fmu.settings.models._enums import ChangeType
from fmu.settings.models.change_info import ChangeInfo

from fmu_settings_api.services.changelog import ChangelogService


def test_get_changelog_contains_changeinfo_entries(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test get_changelog returns entries of type ChangeInfo."""
    service = ChangelogService(fmu_dir)
    fmu_dir.changelog.add_log_entry(
        ChangeInfo(
            change_type=ChangeType.update,
            user="test_user",
            path=fmu_dir.path,
            change="Updated field names",
            hostname="localhost",
            file="config.json",
            key="changelog_test",
        )
    )
    result = service.get_changelog()
    assert len(result) == 1
    assert result[0].change_type == ChangeType.update
    assert result[0].user == "test_user"
    assert result[0].path == fmu_dir.path
    assert result[0].change == "Updated field names"
    assert result[0].hostname == "localhost"
    assert result[0].file == "config.json"
    assert result[0].key == "changelog_test"
