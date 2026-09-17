"""Tests for workspace prompt resolution — seed on read, seed on create,
and pipeline wiring of the workspace-configured prompts."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from storico.application.prompts.resolve_workspace_prompt import (
    build_default_prompt,
    resolve_workspace_prompt,
)
from storico.domain.entities import WorkspacePrompt
from storico.infrastructure.llm.prompt_manager import (
    SYSTEM_PROMPT_TASK_GENERATION,
    PromptManager,
)


class TestResolveWorkspacePrompt:
    """resolve_workspace_prompt: seed on read when the row is missing."""

    @pytest.mark.asyncio
    async def test_seed_on_read_creates_row_with_defaults(self) -> None:
        """Missing row is seeded with the shared defaults and returned."""
        workspace_id = uuid4()
        prompt_repo = AsyncMock()
        prompt_repo.get.return_value = None
        prompt_repo.upsert.side_effect = lambda p: p

        result = await resolve_workspace_prompt(workspace_id, prompt_repo)

        prompt_repo.get.assert_called_once_with(workspace_id)
        prompt_repo.upsert.assert_called_once()
        seeded = prompt_repo.upsert.call_args[0][0]
        assert seeded.workspace_id == workspace_id
        assert seeded.system_prompt == SYSTEM_PROMPT_TASK_GENERATION
        assert seeded.instruction_template is not None
        assert "{{user_story}}" in seeded.instruction_template
        assert result is seeded

    @pytest.mark.asyncio
    async def test_existing_row_returned_without_upsert(self) -> None:
        """A workspace override is returned as-is, nothing is persisted."""
        workspace_id = uuid4()
        custom = WorkspacePrompt(
            workspace_id=workspace_id,
            system_prompt="Custom system",
            instruction_template="Custom: {{user_story}}",
        )
        prompt_repo = AsyncMock()
        prompt_repo.get.return_value = custom

        result = await resolve_workspace_prompt(workspace_id, prompt_repo)

        assert result is custom
        prompt_repo.upsert.assert_not_called()

    def test_build_default_prompt_uses_single_source_defaults(self) -> None:
        """Defaults come from the constant and the real .j2 template."""
        prompt = build_default_prompt(uuid4())
        assert prompt.system_prompt == SYSTEM_PROMPT_TASK_GENERATION
        assert prompt.instruction_template is not None
        assert "{{user_story}}" in prompt.instruction_template
        assert prompt.few_shot_examples is None


class TestCreateWorkspaceSeedsPrompts:
    """create_workspace seeds the prompt row with defaults."""

    @pytest.mark.asyncio
    async def test_create_workspace_creates_prompt_row(self, db_session) -> None:
        from storico.application.workspaces.create_workspace import CreateWorkspaceUseCase
        from storico.domain.entities import WorkspaceRole
        from storico.infrastructure.database.repositories.workspace_member_repository import (
            SQLAlchemyWorkspaceMemberRepository,
        )
        from storico.infrastructure.database.repositories.workspace_prompt_repository import (
            SQLAlchemyWorkspacePromptRepository,
        )
        from storico.infrastructure.database.repositories.workspace_repository import (
            SQLAlchemyWorkspaceRepository,
        )

        ws_repo = SQLAlchemyWorkspaceRepository(db_session)
        member_repo = SQLAlchemyWorkspaceMemberRepository(db_session)
        prompt_repo = SQLAlchemyWorkspacePromptRepository(db_session)

        use_case = CreateWorkspaceUseCase(ws_repo, member_repo, prompt_repo)
        user_id = uuid4()
        workspace = await use_case.execute(name="Seeded WS", user_id=user_id)

        member = await member_repo.find_by_workspace_and_user(workspace.id, user_id)
        assert member is not None
        assert member.role == WorkspaceRole.ADMIN

        seeded = await prompt_repo.get(workspace.id)
        assert seeded is not None
        assert seeded.system_prompt == SYSTEM_PROMPT_TASK_GENERATION
        assert seeded.instruction_template is not None
        assert "{{user_story}}" in seeded.instruction_template


class TestPipelineUsesWorkspacePrompt:
    """The resolved workspace prompt flows into the extraction pipeline."""

    @pytest.mark.asyncio
    async def test_pipeline_uses_resolved_workspace_prompts(self) -> None:
        """Custom workspace prompt (system + instruction) reaches the LLM call."""
        from storico.domain.ports import LLMConfig, ParsedTask
        from storico.domain.services.extraction_service import ExtractionService

        workspace_id = uuid4()
        custom = WorkspacePrompt(
            workspace_id=workspace_id,
            system_prompt="Custom system role",
            instruction_template="Custom instruction for {{user_story}}",
        )
        prompt_repo = AsyncMock()
        prompt_repo.get.return_value = custom

        resolved = await resolve_workspace_prompt(workspace_id, prompt_repo)
        prompt_repo.upsert.assert_not_called()

        llm_port = AsyncMock()
        llm_port.generate.return_value = "1. summary: T\ndescription: D"
        task_parser = MagicMock()
        task_parser.parse.return_value = [ParsedTask(summary="T", description="D")]
        service = ExtractionService(
            llm_port=llm_port,
            prompt_manager=PromptManager(),
            task_parser=task_parser,
            extraction_repo=AsyncMock(),
            task_repo=AsyncMock(),
        )
        story = MagicMock()
        story.id = uuid4()
        story.raw_text = "Story text"

        await service.extract(
            story,
            LLMConfig(model="test"),
            system_prompt=resolved.system_prompt,
            instruction_template=resolved.instruction_template,
        )

        # DB instruction template was rendered via Jinja2 and the system
        # prompt delivered separately.
        llm_port.generate.assert_called_once_with(
            "Custom instruction for Story text",
            LLMConfig(model="test"),
            system_prompt="Custom system role",
        )

    @pytest.mark.asyncio
    async def test_judge_receives_workspace_system_prompt(self) -> None:
        """LLMJudgeService forwards the workspace system prompt to the LLM."""
        from storico.domain.ports import LLMConfig
        from storico.domain.services.extraction_judge_service import LLMJudgeService

        llm_port = AsyncMock()
        llm_port.generate.return_value = '{"approved": true, "total_score": 45}'
        prompt_manager = MagicMock()
        prompt_manager.render_judge_prompt.return_value = "Judge prompt"
        judge = LLMJudgeService(llm_port=llm_port, prompt_manager=prompt_manager)

        result = await judge.validate(
            user_story="Story",
            tasks=[{"summary": "T", "description": "D"}],
            config=LLMConfig(model="test"),
            system_prompt="Workspace system role",
        )

        assert result.approved is True
        llm_port.generate.assert_called_once_with(
            "Judge prompt",
            LLMConfig(model="test"),
            system_prompt="Workspace system role",
        )
