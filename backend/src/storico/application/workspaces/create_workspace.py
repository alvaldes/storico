"""CreateWorkspaceUseCase — creates a workspace with the creator as admin+owner."""

from __future__ import annotations

from uuid import UUID

from storico.application.workspaces.slug import generate_slug
from storico.domain.entities import DuplicateEntity, Workspace, WorkspaceMember, WorkspaceRole
from storico.domain.ports import WorkspaceMemberRepository, WorkspaceRepository


class CreateWorkspaceUseCase:
    """Use case: create a new workspace with the authenticated user as both
    admin and owner.

    The creator is automatically added as an admin member of the newly
    created workspace. Slug generation and uniqueness validation happen
    before persistence.

    Note: The workspace and member are persisted in two sequential repo
    calls, each managing its own transaction. A future improvement could
    introduce a unit-of-work pattern for true atomicity.
    """

    def __init__(
        self,
        ws_repo: WorkspaceRepository,
        member_repo: WorkspaceMemberRepository,
    ) -> None:
        self._ws_repo = ws_repo
        self._member_repo = member_repo

    async def execute(
        self,
        name: str,
        user_id: UUID,
        slug: str | None = None,
        icon: str | None = None,
    ) -> Workspace:
        """Create a workspace and add the creator as admin+owner.

        Args:
            name: Display name for the workspace (required, non-empty).
            user_id: UUID of the authenticated user (becomes owner + admin).
            slug: Optional explicit slug. Auto-generated from ``name`` if
                not provided.

        Returns:
            The newly created ``Workspace`` entity.

        Raises:
            ValueError: If ``name`` is empty or whitespace-only.
            DuplicateEntity: If the generated or provided ``slug`` is already
                taken.
        """
        if not name or not name.strip():
            raise ValueError("Workspace name cannot be empty")

        existing_slugs = await self._ws_repo.list_slugs()
        final_slug = slug if slug else generate_slug(name, existing_slugs)

        if final_slug in existing_slugs:
            raise DuplicateEntity("Workspace", "slug", final_slug)

        workspace = Workspace(name=name.strip(), slug=final_slug, owner_id=user_id, icon=icon)

        # Persist workspace first, then add the owner as an admin member.
        # Each repo call manages its own transaction.
        saved = await self._ws_repo.save(workspace)

        member = WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user_id,
            role=WorkspaceRole.ADMIN,
        )
        await self._member_repo.add(member)

        return saved
