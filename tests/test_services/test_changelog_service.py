"""Tests for ChangelogService."""

from fmu.settings import ProjectFMUDirectory
from fmu.settings.models._enums import ChangeType, FilterType
from fmu.settings.models.change_info import ChangeInfo
from fmu.settings.models.log import Filter

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
    entry = next(entry for entry in result if entry.key == "changelog_test")
    assert entry.change_type == ChangeType.update
    assert entry.user == "test_user"
    assert entry.path == fmu_dir.path
    assert entry.change == "Updated field names"
    assert entry.hostname == "localhost"
    assert entry.file == "config.json"


def test_get_changelog_filtered_by_change_type(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test get_changelog filters entries by change type."""
    service = ChangelogService(fmu_dir)
    fmu_dir.changelog.add_log_entry(
        ChangeInfo(
            change_type=ChangeType.update,
            user="test_user",
            path=fmu_dir.path,
            change="Updated field names",
            hostname="localhost",
            file="config.json",
            key="changelog_update",
        )
    )
    fmu_dir.changelog.add_log_entry(
        ChangeInfo(
            change_type=ChangeType.remove,
            user="test_user",
            path=fmu_dir.path,
            change="Removed field",
            hostname="localhost",
            file="config.json",
            key="changelog_remove",
        )
    )

    result = service.get_changelog(change_type=ChangeType.update)

    assert len(result) == 1
    assert result[0].change_type == ChangeType.update
    assert result[0].key == "changelog_update"


def test_get_changelog_filtered_by_generic_filter(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test get_changelog applies the upstream generic Filter."""
    service = ChangelogService(fmu_dir)
    fmu_dir.changelog.add_log_entry(
        ChangeInfo(
            change_type=ChangeType.update,
            user="test_user",
            path=fmu_dir.path,
            change="Updated field names",
            hostname="localhost",
            file="config.json",
            key="changelog_update",
        )
    )
    fmu_dir.changelog.add_log_entry(
        ChangeInfo(
            change_type=ChangeType.remove,
            user="test_user",
            path=fmu_dir.path,
            change="Removed field",
            hostname="localhost",
            file="config.json",
            key="changelog_remove",
        )
    )

    result = service.get_changelog(
        filter_=Filter(
            field_name="key",
            filter_value="changelog_update",
            filter_type=FilterType.text,
            operator="==",
        )
    )

    assert len(result) == 1
    assert result[0].key == "changelog_update"


def test_get_changelog_max_entries_returns_latest_entries(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test get_changelog limits entries to the latest max_entries items."""
    service = ChangelogService(fmu_dir)
    for key in ("entry_1", "entry_2", "entry_3"):
        fmu_dir.changelog.add_log_entry(
            ChangeInfo(
                change_type=ChangeType.update,
                user="test_user",
                path=fmu_dir.path,
                change="Updated field names",
                hostname="localhost",
                file="config.json",
                key=key,
            )
        )

    result = service.get_changelog(max_entries=2)

    assert len(result) == 2
    assert [entry.key for entry in result] == ["entry_2", "entry_3"]


def test_get_changelog_applies_all_filters(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test get_changelog combines change type, generic filter, and max entries."""
    service = ChangelogService(fmu_dir)
    for change_type, user, key in (
        (ChangeType.update, "test_user", "entry_1"),
        (ChangeType.update, "test_user", "entry_2"),
        (ChangeType.remove, "test_user", "entry_3"),
        (ChangeType.update, "other_user", "excluded_entry"),
        (ChangeType.update, "test_user", "entry_4"),
    ):
        fmu_dir.changelog.add_log_entry(
            ChangeInfo(
                change_type=change_type,
                user=user,
                path=fmu_dir.path,
                change="Changed field names",
                hostname="localhost",
                file="config.json",
                key=key,
            )
        )

    result = service.get_changelog(
        change_type=ChangeType.update,
        filter_=Filter(
            field_name="user",
            filter_value="test_user",
            filter_type=FilterType.text,
            operator="==",
        ),
        max_entries=2,
    )

    assert len(result) == 2
    assert [entry.key for entry in result] == ["entry_2", "entry_4"]
