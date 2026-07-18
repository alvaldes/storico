"""RenameWorkspaceUseCase — renames a user's personal workspace during onboarding."""

from __future__ import annotations

from uuid import UUID

from storico.application.workspaces.slug import generate_slug
from storico.domain.entities import DuplicateEntity, Workspace
from storico.domain.ports import WorkspaceRepository


class RenameWorkspaceUseCase:
    """Use case: rename a user's personal workspace.

    Used during first-login onboarding to let users customize the
    auto-created workspace name. Generates a new slug from the new name
    and validates uniqueness before persisting.
    """

    def __init__(self, ws_repo: WorkspaceRepository) -> None:
        self._ws_repo = ws_repo

    async def execute(
        self,
        user_id: UUID,
        new_name: str,
        new_icon: str | None = None,
    ) -> Workspace:
        """Rename the user's personal workspace.

        Finds the user's first workspace, generates a new unique slug
        from the new name, and persists the update.

        Args:
            user_id: UUID of the workspace owner.
            new_name: New display name for the workspace (required,
                non-empty).
            new_icon: Optional new icon identifier for the workspace.

        Returns:
            The updated ``Workspace`` entity with the new name and slug.

        Raises:
            ValueError: If ``new_name`` is empty or whitespace-only.
            DuplicateEntity: If the generated slug conflicts with an
                existing workspace slug.
        """
        if not new_name or not new_name.strip():
            raise ValueError("Workspace name cannot be empty")

        workspaces = await self._ws_repo.list_by_user(user_id)
        if not workspaces:
            raise ValueError("User has no workspace to rename")

        workspace = workspaces[0]

        existing_slugs = await self._ws_repo.list_slugs()
        # Remove this workspace's own slug from the list to avoid
        # false conflicts (same slug after rename should always be allowed).
        current_slugs = [s for s in existing_slugs if s != workspace.slug]

        new_slug = generate_slug(new_name, current_slugs)

        if new_slug in current_slugs:
            raise DuplicateEntity("Workspace", "slug", new_slug)

        renamed = Workspace(
            name=new_name.strip(),
            slug=new_slug,
            owner_id=workspace.owner_id,
            icon=new_icon or workspace.icon,
            id=workspace.id,
            created_at=workspace.created_at,
            updated_at=workspace.updated_at,
        )

        return await self._ws_repo.save(renamed)
