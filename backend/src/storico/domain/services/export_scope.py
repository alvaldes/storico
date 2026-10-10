"""The export scope rule — one target, never two, shared by both exports.

``project_id``, ``user_story_id`` or the whole workspace, never two — two
targets are refused, not resolved, because an ``if``/``elif`` chain would
silently answer one of them, a wrong answer shaped like a right one. The rule
is the one the Kanban cascade already applies (feature
``versioning-visibility``'s D7); it lives here, in the domain, so the Trello
trigger and the file download both call it instead of each growing a resolver
with the same three branches.

The values it returns are the ``TrelloExportScope`` members exactly as they
have always been spelled: the job row's ``scope`` column stores
``export.scope.value`` and the API's ``scope`` field serializes the same
members, so a renaming here would be a storage and wire contract change, not a
refactor.
"""

from __future__ import annotations

from uuid import UUID

from storico.domain.entities.trello_export import TrelloExportScope


class AmbiguousExportScopeError(ValueError):
    """Two export targets in one request — refused, never resolved."""


def resolve_export_scope(project_id: UUID | None, user_story_id: UUID | None) -> TrelloExportScope:
    """Resolve exactly one export scope from the optional targets.

    Raises ``AmbiguousExportScopeError`` when both are given — the same shape
    refusal the tasks route answers with 422 ``REQUEST_VALIDATION_FAILED``.
    """
    if project_id is not None and user_story_id is not None:
        raise AmbiguousExportScopeError(
            "project_id and user_story_id are mutually exclusive: an export "
            "covers the workspace, one project or one story, never two"
        )
    if project_id is not None:
        return TrelloExportScope.PROJECT
    if user_story_id is not None:
        return TrelloExportScope.STORY
    return TrelloExportScope.WORKSPACE
