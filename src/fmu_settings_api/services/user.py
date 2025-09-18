"""Functions for interacting with the user .fmu directory."""

from pathlib import Path

from fmu.settings._fmu_dir import UserFMUDirectory


def add_to_user_recent_projects(
    project_path: Path,
    user_dir: UserFMUDirectory,
) -> None:
    """Adds a project path to the user's recent project directories.

    The directories are ordered with the most recent project first in the list.
    Existing paths will be moved to the start if re-added.
    Only the 5 most recent projects are kept.
    """
    recent_projects = user_dir.get_config_value("recent_project_directories")

    if project_path in recent_projects:
        recent_projects.remove(project_path)

    recent_projects.insert(0, project_path)
    user_dir.set_config_value("recent_project_directories", recent_projects[:5])


def remove_from_recent_projects(
    project_path: Path,
    user_dir: UserFMUDirectory,
) -> None:
    """Removes a project path from the user's recent project directories if existing."""
    recent_projects = user_dir.get_config_value("recent_project_directories")

    if project_path in recent_projects:
        recent_projects.remove(project_path)
        user_dir.set_config_value("recent_project_directories", recent_projects)
