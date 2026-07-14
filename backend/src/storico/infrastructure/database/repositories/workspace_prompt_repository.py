"""SQLAlchemy implementation of the WorkspacePromptRepository port."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import RepositoryError, WorkspacePrompt
from storico.domain.ports import WorkspacePromptRepository
from storico.infrastructure.database.models import WorkspacePromptModel


class SQLAlchemyWorkspacePromptRepository(WorkspacePromptRepository):
    """Repository implementation for WorkspacePrompt entities using SQLAlchemy async sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, workspace_id: UUID) -> WorkspacePrompt | None:
        stmt = select(WorkspacePromptModel).where(
            WorkspacePromptModel.workspace_id == workspace_id
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def upsert(self, prompt: WorkspacePrompt) -> WorkspacePrompt:
        try:
            existing = await self._session.execute(
                select(WorkspacePromptModel).where(
                    WorkspacePromptModel.workspace_id == prompt.workspace_id
                )
            )
            existing_row = existing.scalar_one_or_none()
            if existing_row:
                for key, value in self._to_orm_kwargs(prompt).items():
                    setattr(existing_row, key, value)
            else:
                self._session.add(
                    WorkspacePromptModel(**self._to_orm_kwargs(prompt))
                )
            await self._session.commit()
            return prompt
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError(
                "Database error upserting workspace prompt"
            ) from e

    @staticmethod
    def _to_domain(model: WorkspacePromptModel) -> WorkspacePrompt:
        return WorkspacePrompt(
            workspace_id=model.workspace_id,
            system_prompt=model.system_prompt,
            instruction_template=model.instruction_template,
            few_shot_examples=(
                model.few_shot_examples.get("items", [])
                if model.few_shot_examples
                else None
            ),
            id=model.id,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_orm_kwargs(prompt: WorkspacePrompt) -> dict:
        return {
            "id": prompt.id,
            "workspace_id": prompt.workspace_id,
            "system_prompt": prompt.system_prompt,
            "instruction_template": prompt.instruction_template,
            "few_shot_examples": (
                {"items": prompt.few_shot_examples}
                if prompt.few_shot_examples
                else None
            ),
            "updated_at": prompt.updated_at,
        }
