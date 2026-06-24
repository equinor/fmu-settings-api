"""Changelog service dependencies."""

from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query
from fmu.settings.models._enums import ChangeType, FilterType
from fmu.settings.models.log import Filter

from fmu_settings_api.deps.session import ProjectSessionDep
from fmu_settings_api.services.changelog import ChangelogService


@dataclass(frozen=True)
class ChangelogFilters:
    """Query filters for changelog retrieval."""

    change_type: ChangeType | None = None
    max_entries: int | None = None
    filter_: Filter | None = None


async def get_changelog_filters(
    change_type: ChangeType | None = None,
    max_entries: int | None = Query(default=None, ge=1),
    field_name: str | None = None,
    filter_value: str | None = None,
    filter_type: FilterType | None = None,
    operator: Literal[">", ">=", "<", "<=", "==", "!="] | None = None,
) -> ChangelogFilters:
    """Return parsed changelog query filters."""
    generic_log_filter_values = (field_name, filter_value, filter_type, operator)
    has_any_generic_filter = any(
        value is not None for value in generic_log_filter_values
    )
    has_all_generic_filter = all(
        value is not None for value in generic_log_filter_values
    )

    if has_any_generic_filter and not has_all_generic_filter:
        raise HTTPException(
            status_code=422,
            detail=(
                "Changelog filtering requires all of the generic log filtering "
                "fields: field_name, filter_value, filter_type, operator."
            ),
        )

    filter_: Filter | None = None
    if has_all_generic_filter:
        assert field_name is not None
        assert filter_value is not None
        assert filter_type is not None
        assert operator is not None
        filter_ = Filter(
            field_name=field_name,
            filter_value=filter_value,
            filter_type=filter_type,
            operator=operator,
        )

    return ChangelogFilters(
        change_type=change_type,
        max_entries=max_entries,
        filter_=filter_,
    )


async def get_changelog_service(
    project_session: ProjectSessionDep,
) -> ChangelogService:
    """Returns a ChangelogService instance."""
    return ChangelogService(project_session.project_fmu_directory)


ChangelogServiceDep = Annotated[ChangelogService, Depends(get_changelog_service)]
ChangelogFiltersDep = Annotated[ChangelogFilters, Depends(get_changelog_filters)]
