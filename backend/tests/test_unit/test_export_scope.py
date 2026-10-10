"""Unit tests for the export scope rule — one target, never two.

The rule lives in ``domain/services/export_scope.py`` so both exports — the
Trello trigger and the file download — resolve scope through the same code
instead of growing a second resolver with the same three branches. These tests
pin the rule itself and, deliberately, the exact spellings it stores and
returns: the job row's ``scope`` column and the API's ``scope`` field are
written from these values, so a renaming here would be a wire and storage
contract change, not a refactor.
"""

from uuid import uuid4

import pytest

from storico.domain.entities.trello_export import TrelloExportScope
from storico.domain.services.export_scope import (
    AmbiguousExportScopeError,
    resolve_export_scope,
)


class TestResolveExportScope:
    def test_no_target_is_the_whole_workspace(self) -> None:
        assert resolve_export_scope(None, None) is TrelloExportScope.WORKSPACE

    def test_project_id_alone_is_the_project_scope(self) -> None:
        project_id = uuid4()
        scope = resolve_export_scope(project_id, None)
        assert scope is TrelloExportScope.PROJECT

    def test_user_story_id_alone_is_the_story_scope(self) -> None:
        story_id = uuid4()
        scope = resolve_export_scope(None, story_id)
        assert scope is TrelloExportScope.STORY

    def test_two_targets_are_refused(self) -> None:
        with pytest.raises(AmbiguousExportScopeError):
            resolve_export_scope(uuid4(), uuid4())


class TestScopeSpellingsAreTheStoredContract:
    """The values the resolver returns are the values storage and the API emit.

    ``SQLAlchemyTrelloExportRepository`` writes ``export.scope.value`` into the
    job row's ``scope`` column and reads it back with
    ``TrelloExportScope(model.scope)``; the API's ``scope`` field serializes the
    same members. Renaming one of these strings would silently change every
    historical job row's meaning.
    """

    def test_workspace_spelling(self) -> None:
        assert TrelloExportScope.WORKSPACE.value == "workspace"

    def test_project_spelling(self) -> None:
        assert TrelloExportScope.PROJECT.value == "project"

    def test_story_spelling(self) -> None:
        assert TrelloExportScope.STORY.value == "story"

    def test_the_resolver_returns_those_same_members(self) -> None:
        assert resolve_export_scope(None, None).value == "workspace"
        assert resolve_export_scope(uuid4(), None).value == "project"
        assert resolve_export_scope(None, uuid4()).value == "story"
