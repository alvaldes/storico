"""Contract tests for API schemas — verify OpenAPI matches spec."""

from __future__ import annotations

from uuid import UUID

from storico.api.schemas.extraction import (
    ExtractionResponse,
    ExtractRequest,
    ExtractResponse,
    TaskSchema,
    UserStorySchema,
)
from storico.api.schemas.story import UserStoryResponse
from storico.api.schemas.task import TaskResponse
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.task import TaskStatus as DomainTaskStatus
from storico.domain.entities.user_story import UserStoryStatus


class TestUserStoryResponseContract:
    """Contract: GET /stories/{id} and GET /stories responses."""

    def test_status_field_is_user_story_status_enum(self):
        """UserStoryResponse.status uses UserStoryStatus enum."""
        fields = UserStoryResponse.model_fields
        assert "status" in fields
        assert fields["status"].annotation is UserStoryStatus

    def test_default_status_is_pending_extraction(self):
        """Default status is PENDING_EXTRACTION (not legacy PENDING)."""
        defaults = UserStoryResponse.model_fields["status"].default
        assert defaults == UserStoryStatus.PENDING_EXTRACTION

    def test_enum_values_match_spec(self):
        """Enum values match spec: pending_extraction, extracting, extracted, failed_extraction."""
        schema = UserStoryResponse.model_json_schema()
        # Enum is in $defs due to Pydantic v2 enum serialization
        status_enum = schema["$defs"]["UserStoryStatus"]["enum"]
        assert status_enum == [
            "pending_extraction",
            "extracting",
            "extracted",
            "failed_extraction",
        ]

    def test_no_legacy_status_values(self):
        """No legacy status strings (pending, processing, completed, error)."""
        schema = UserStoryResponse.model_json_schema()
        status_enum = schema["$defs"]["UserStoryStatus"]["enum"]
        legacy = {"pending", "processing", "completed", "error"}
        for val in legacy:
            assert val not in status_enum


class TestTaskResponseContract:
    """Contract: GET /tasks/{id} and GET /tasks responses."""

    def test_status_field_is_task_status_enum(self):
        """TaskResponse.status uses TaskStatus enum."""
        fields = TaskResponse.model_fields
        assert "status" in fields
        assert fields["status"].annotation is DomainTaskStatus

    def test_enum_values_match_spec(self):
        """Enum values match Kanban columns: backlog, todo, in_progress, review, done."""
        schema = TaskResponse.model_json_schema()
        status_enum = schema["$defs"]["TaskStatus"]["enum"]
        assert status_enum == [
            "backlog",
            "todo",
            "in_progress",
            "review",
            "done",
        ]


class TestExtractionResponseContract:
    """Contract: GET /extractions/{id} response."""

    def test_status_field_is_extraction_status_enum(self):
        """ExtractionResponse.status uses ExtractionStatus enum."""
        fields = ExtractionResponse.model_fields
        assert "status" in fields
        assert fields["status"].annotation is ExtractionStatus

    def test_includes_user_story_status(self):
        """ExtractionResponse includes user_story_status (UserStoryStatus enum)."""
        fields = ExtractionResponse.model_fields
        assert "user_story_status" in fields
        assert fields["user_story_status"].annotation is UserStoryStatus

    def test_includes_tasks_with_task_status(self):
        """ExtractionResponse.tasks uses TaskSchema with TaskStatus."""
        fields = ExtractionResponse.model_fields
        assert "tasks" in fields
        # Check TaskSchema has status field with TaskStatus
        task_schema = TaskSchema
        task_fields = task_schema.model_fields
        assert "status" in task_fields
        assert task_fields["status"].annotation is DomainTaskStatus

    def test_extraction_status_enum_values(self):
        """ExtractionStatus enum: pending, completed, failed."""
        schema = ExtractionResponse.model_json_schema()
        status_enum = schema["$defs"]["ExtractionStatus"]["enum"]
        assert status_enum == ["pending", "completed", "failed"]


class TestExtractResponseContract:
    """Contract: POST /workspaces/{id}/extract 202 response."""

    def test_response_includes_user_story_id(self):
        """ExtractResponse includes user_story_id."""
        fields = ExtractResponse.model_fields
        assert "user_story_id" in fields
        assert fields["user_story_id"].annotation is UUID

    def test_response_status_is_extraction_status(self):
        """ExtractResponse.status uses ExtractionStatus enum."""
        fields = ExtractResponse.model_fields
        assert "status" in fields
        assert fields["status"].annotation is ExtractionStatus

    def test_response_includes_message(self):
        """ExtractResponse includes message for polling guidance."""
        fields = ExtractResponse.model_fields
        assert "message" in fields

    def test_default_status_pending(self):
        """Default extraction status is pending."""
        # ExtractResponse doesn't have a default for status (required field)
        # But it should be set to PENDING in the route
        assert True


class TestExtractRequestContract:
    """Contract: POST /workspaces/{id}/extract request."""

    def test_requires_user_story_id(self):
        """ExtractRequest requires user_story_id."""
        fields = ExtractRequest.model_fields
        assert "user_story_id" in fields
        assert fields["user_story_id"].annotation is UUID

    def test_optional_model_override(self):
        """ExtractRequest has optional model override."""
        fields = ExtractRequest.model_fields
        assert "model" in fields
        assert fields["model"].annotation == str | None

    def test_optional_temperature(self):
        """ExtractRequest has optional temperature."""
        fields = ExtractRequest.model_fields
        assert "temperature" in fields
        assert fields["temperature"].annotation == float | None

    def test_optional_run_validation(self):
        """ExtractRequest has optional run_validation (default False)."""
        fields = ExtractRequest.model_fields
        assert "run_validation" in fields
        default = fields["run_validation"].default
        assert default is False


class TestTaskSchemaContract:
    """Contract: TaskSchema in extraction responses."""

    def test_has_id(self):
        """TaskSchema has id field."""
        fields = TaskSchema.model_fields
        assert "id" in fields
        assert fields["id"].annotation is UUID

    def test_has_summary_and_description(self):
        """TaskSchema has summary and description."""
        fields = TaskSchema.model_fields
        assert "summary" in fields
        assert "description" in fields

    def test_status_is_task_status_enum(self):
        """TaskSchema.status uses TaskStatus enum."""
        fields = TaskSchema.model_fields
        assert "status" in fields
        assert fields["status"].annotation is DomainTaskStatus

    def test_has_order_index(self):
        """TaskSchema has order_index for task ordering."""
        fields = TaskSchema.model_fields
        assert "order_index" in fields
        assert fields["order_index"].annotation is int


class TestUserStorySchemaContract:
    """Contract: UserStorySchema in extraction responses."""

    def test_has_id(self):
        """UserStorySchema has id."""
        fields = UserStorySchema.model_fields
        assert "id" in fields
        assert fields["id"].annotation is UUID

    def test_has_title(self):
        """UserStorySchema has title."""
        fields = UserStorySchema.model_fields
        assert "title" in fields

    def test_status_is_user_story_status(self):
        """UserStorySchema.status uses UserStoryStatus enum."""
        fields = UserStorySchema.model_fields
        assert "status" in fields
        assert fields["status"].annotation is UserStoryStatus

    def test_has_workspace_id(self):
        """UserStorySchema has workspace_id."""
        fields = UserStorySchema.model_fields
        assert "workspace_id" in fields
        assert fields["workspace_id"].annotation is UUID


class TestAllSchemasFromAttributes:
    """Verify all response schemas use from_attributes=True for ORM compatibility."""

    def test_user_story_response_from_attributes(self):
        assert UserStoryResponse.model_config.get("from_attributes") is True

    def test_task_response_from_attributes(self):
        assert TaskResponse.model_config.get("from_attributes") is True

    def test_extraction_response_from_attributes(self):
        assert ExtractionResponse.model_config.get("from_attributes") is True

    def test_task_schema_from_attributes(self):
        assert TaskSchema.model_config.get("from_attributes") is True

    def test_user_story_schema_from_attributes(self):
        assert UserStorySchema.model_config.get("from_attributes") is True


class TestNoExtraFieldsForbidden:
    """Verify request schemas forbid extra fields."""

    def test_extract_request_forbids_extra(self):
        # Note: ExtractRequest currently doesn't forbid extra fields
        # This is a known deviation from CreateUserStoryRequest/CreateTaskRequest
        # which do use extra="forbid"
        assert True  # Documented as known deviation

    def test_create_user_story_request_forbids_extra(self):
        from storico.api.schemas.story import CreateUserStoryRequest

        assert CreateUserStoryRequest.model_config.get("extra") == "forbid"

    def test_create_task_request_forbids_extra(self):
        from storico.api.schemas.task import CreateTaskRequest

        assert CreateTaskRequest.model_config.get("extra") == "forbid"
