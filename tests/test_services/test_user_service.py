"""Tests the user service functions."""

from pathlib import Path

import pytest
from fmu.settings._init import init_user_fmu_directory

from fmu_settings_api.services.user import (
    add_to_user_recent_projects,
    remove_from_recent_projects,
)


def test_add_to_user_recent_projects(tmp_path_mocked_home: Path) -> None:
    """Tests adding to recent projects works as expected."""
    user_dir = init_user_fmu_directory()

    # Initially empty
    assert user_dir.get_config_value("recent_project_directories") == []

    project_path = Path("/some/project")
    add_to_user_recent_projects(project_path, user_dir)
    assert user_dir.get_config_value("recent_project_directories") == [project_path]

    # add yet another project and see that it is added first in the list
    new_project_path = Path("/new/project")
    add_to_user_recent_projects(new_project_path, user_dir)
    assert user_dir.get_config_value("recent_project_directories") == [
        new_project_path,
        project_path,
    ]


def test_add_to_user_recent_projects_does_not_add_duplicate(
    tmp_path_mocked_home: Path,
) -> None:
    """Tests adding to recent projects does not add duplicates."""
    user_dir = init_user_fmu_directory()
    project_path = Path("/some/project")

    # call it twice
    add_to_user_recent_projects(project_path, user_dir)
    add_to_user_recent_projects(project_path, user_dir)
    assert user_dir.get_config_value("recent_project_directories") == [project_path]


def test_add_to_user_recent_projects_removes_oldest_when_full(
    tmp_path_mocked_home: Path,
) -> None:
    """Tests adding to recent projects does not exceed max limit."""
    user_dir = init_user_fmu_directory()
    max_number_of_recent_projects = 5

    project_paths = [
        Path(f"/project/{i}") for i in range(max_number_of_recent_projects)
    ]
    user_dir.set_config_value("recent_project_directories", project_paths)
    assert len(project_paths) == max_number_of_recent_projects

    # add a new project and check that the length
    # is still 5 and the oldest (last) is removed
    new_path = Path("/project/new")
    expected_recent_projects = [new_path] + project_paths[:-1]
    add_to_user_recent_projects(new_path, user_dir)
    recent_projects = user_dir.get_config_value("recent_project_directories")
    assert recent_projects == expected_recent_projects
    assert len(recent_projects) == max_number_of_recent_projects

    # directly set the value to more than 5
    # should fail unless length requirement in fmu-settings is changed
    with pytest.raises(ValueError):
        user_dir.set_config_value(
            "recent_project_directories", [Path(f"/project/{i}") for i in range(6)]
        )


def test_remove_from_user_recent_projects(tmp_path_mocked_home: Path) -> None:
    """Tests removing a non-existing path from recent projects works."""
    user_dir = init_user_fmu_directory()

    non_existing_user_copy = Path("/some/user/project_1")

    user_dir.set_config_value("recent_project_directories", [non_existing_user_copy])

    remove_from_recent_projects(non_existing_user_copy, user_dir)
    assert user_dir.get_config_value("recent_project_directories") == []


def test_remove_from_user_recent_projects_does_not_remove_existing(
    tmp_path_mocked_home: Path,
) -> None:
    """Tests removing a path not present does not modify recent projects."""
    user_dir = init_user_fmu_directory()

    project_path = tmp_path_mocked_home / "some/project"

    user_dir.set_config_value("recent_project_directories", [project_path])

    another_project_path = tmp_path_mocked_home / "some/other/project"

    remove_from_recent_projects(another_project_path, user_dir)

    assert user_dir.get_config_value("recent_project_directories") == [project_path]
