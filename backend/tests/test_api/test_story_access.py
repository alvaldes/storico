"""Direct tests for the shared story-access walk in ``api.dependencies``.

``require_story_workspace_access`` is the single ``story → project → workspace``
authorization walk behind every story, task and extraction route. Two of its
failure branches cannot be reached through the API with the seeded chains:

- ``story is None`` and ``project is None`` need a dangling reference, but
  ``user_stories.project_id`` is a NOT NULL foreign key, so a persisted story
  always has an owning project row.
- ``member is None`` is reachable through the API, but only once a full chain is
  seeded and a route happens to call the walk; driving it through a route pins
  the 403 payload to that route's wiring instead of to the walk itself.

Calling the helper directly with stub repositories exercises exactly those
branches. It also makes the walk's arguments observable, which is what the happy
path asserts: the project lookup must be driven by the story's own
``project_id``, and the membership lookup by *that project's* ``workspace_id``.
Both stubs stay deliberately minimal — only the methods the walk calls — so a
change that reaches for anything else fails loudly here instead of silently.
"""

from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from storico.api.dependencies import require_story_workspace_access
from storico.domain.entities import EntityNotFound, Project, User, UserStory
from storico.domain.entities.workspace_member import WorkspaceMember, WorkspaceRole
from storico.infrastructure.database.repositories import (
    SQLAlchemyProjectRepository,
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.database.repositories.workspace_member_repository import (
    SQLAlchemyWorkspaceMemberRepository,
)

FORBIDDEN_DETAIL = "Not a member of this workspace"


def _stub_user() -> User:
    """A caller identity; the walk only ever reads ``.id`` from it."""
    return User(email="stub@test.com", name="Stub Caller")


def _stub_story(project_id: UUID) -> UserStory:
    """A story pointing at ``project_id`` — the walk's first hop."""
    return UserStory(
        project_id=project_id,
        actor="user",
        feature="use a stub chain",
        benefit="the walk is observable",
        raw_text="As a user, I want to use a stub chain so that the walk is observable",
    )


def _stub_member(workspace_id: UUID, user_id: UUID) -> WorkspaceMember:
    """A membership row proving the caller may reach ``workspace_id``."""
    return WorkspaceMember(
        workspace_id=workspace_id,
        user_id=user_id,
        role=WorkspaceRole.ADMIN,
    )


class _StubStoryRepo:
    """``find_by_id`` stand-in that records the id the walk asked for."""

    def __init__(self, story: UserStory | None) -> None:
        self._story = story
        self.requested_ids: list[UUID] = []

    async def find_by_id(self, story_id: UUID) -> UserStory | None:
        self.requested_ids.append(story_id)
        return self._story


class _StubProjectRepo:
    """``find_by_id`` stand-in that records the id the walk asked for."""

    def __init__(self, project: Project | None) -> None:
        self._project = project
        self.requested_ids: list[UUID] = []

    async def find_by_id(self, project_id: UUID) -> Project | None:
        self.requested_ids.append(project_id)
        return self._project


class _StubMemberRepo:
    """``find_by_workspace_and_user`` stand-in recording the pair asked for."""

    def __init__(self, member: WorkspaceMember | None) -> None:
        self._member = member
        self.requested_pairs: list[tuple[UUID, UUID]] = []

    async def find_by_workspace_and_user(
        self, workspace_id: UUID, user_id: UUID
    ) -> WorkspaceMember | None:
        self.requested_pairs.append((workspace_id, user_id))
        return self._member


async def _walk(
    story_id: UUID,
    user: User,
    *,
    story_repo: _StubStoryRepo,
    project_repo: _StubProjectRepo,
    member_repo: _StubMemberRepo,
    reported_as: tuple[str, UUID] | None = None,
) -> UserStory:
    """Call the walk with the duck-typed stubs above.

    The walk only ever calls ``find_by_id`` and ``find_by_workspace_and_user``,
    which each stub implements; its parameters are annotated with the concrete
    SQLAlchemy repositories, so the three casts record that substitution in one
    place instead of at every call site.
    """
    return await require_story_workspace_access(
        story_id,
        user,
        story_repo=cast(SQLAlchemyUserStoryRepository, story_repo),
        project_repo=cast(SQLAlchemyProjectRepository, project_repo),
        member_repo=cast(SQLAlchemyWorkspaceMemberRepository, member_repo),
        reported_as=reported_as,
    )


class TestRequireStoryWorkspaceAccess:
    """``require_story_workspace_access`` — the shared authorization walk."""

    async def test_returns_the_story_and_walks_project_then_workspace(self) -> None:
        """The member path returns the story after resolving both hops.

        This is the happy path that proves the stubs are wired: the project
        lookup is issued with the story's ``project_id`` (not the caller's
        ``story_id``) and the membership lookup with that project's
        ``workspace_id`` (not the workspace of some other row). A walk that
        short-circuited either hop — or resolved the wrong id — cannot satisfy
        both recorded calls at once.
        """
        user = _stub_user()
        story = _stub_story(project_id=uuid4())
        workspace_id = uuid4()
        project = Project(name="Stub Project", workspace_id=workspace_id)

        story_repo = _StubStoryRepo(story)
        project_repo = _StubProjectRepo(project)
        member_repo = _StubMemberRepo(_stub_member(workspace_id, user.id))

        result = await _walk(
            story.id,
            user,
            story_repo=story_repo,
            project_repo=project_repo,
            member_repo=member_repo,
        )

        assert result is story
        assert story_repo.requested_ids == [story.id]
        assert project_repo.requested_ids == [story.project_id]
        assert member_repo.requested_pairs == [(workspace_id, user.id)]

    async def test_reports_a_missing_story_as_the_default_head_entity(self) -> None:
        """A missing story is reported as the ``UserStory`` the caller asked for.

        Pins the default ``reported_as``: the route's head entity is named by
        ``story_id``, so a miss on the very first hop reads to the caller as
        their own addressed story being absent.
        """
        user = _stub_user()
        story_id = uuid4()

        with pytest.raises(EntityNotFound) as exc_info:
            await _walk(
                story_id,
                user,
                story_repo=_StubStoryRepo(None),
                project_repo=_StubProjectRepo(None),
                member_repo=_StubMemberRepo(None),
            )

        assert exc_info.value.entity_type == "UserStory"
        assert exc_info.value.entity_id == str(story_id)

    async def test_reports_a_missing_project_as_the_caller_head_entity(self) -> None:
        """A story whose owning project row is gone is reported as the *caller's* entity.

        The branch this file exists for: ``project_repo`` returns ``None`` while
        the story resolves, so the walk cannot know which workspace the story
        belonged to. Reporting the caller's head entity (here ``Extraction``, as
        the extraction routes pass it) is what keeps the walk from revealing
        which hop failed. Removing the ``project is None`` guard would make this
        test fail with an ``AttributeError`` on ``None.workspace_id`` instead of
        the expected ``EntityNotFound``.
        """
        user = _stub_user()
        story = _stub_story(project_id=uuid4())
        extraction_id = uuid4()

        with pytest.raises(EntityNotFound) as exc_info:
            await _walk(
                story.id,
                user,
                story_repo=_StubStoryRepo(story),
                project_repo=_StubProjectRepo(None),
                member_repo=_StubMemberRepo(None),
                reported_as=("Extraction", extraction_id),
            )

        assert exc_info.value.entity_type == "Extraction"
        assert exc_info.value.entity_id == str(extraction_id)

    async def test_rejects_a_non_member_with_the_shared_forbidden_detail(self) -> None:
        """A caller outside the workspace gets 403 with the shared detail string.

        The walk resolves the story and its project, then finds no membership.
        The payload is asserted here so the string has one owner: every route
        that delegates to this walk reports the same fact the same way.
        """
        user = _stub_user()
        story = _stub_story(project_id=uuid4())
        workspace_id = uuid4()
        project = Project(name="Stub Project", workspace_id=workspace_id)

        with pytest.raises(HTTPException) as exc_info:
            await _walk(
                story.id,
                user,
                story_repo=_StubStoryRepo(story),
                project_repo=_StubProjectRepo(project),
                member_repo=_StubMemberRepo(None),
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == FORBIDDEN_DETAIL
