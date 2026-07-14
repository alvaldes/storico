"""Repository implementations — re-export all SQLAlchemy repository classes."""

from storico.infrastructure.database.repositories.extraction_repository import (
    SQLAlchemyExtractionRepository,
)
from storico.infrastructure.database.repositories.project_repository import (
    SQLAlchemyProjectRepository,
)
from storico.infrastructure.database.repositories.task_repository import (
    SQLAlchemyTaskRepository,
)
from storico.infrastructure.database.repositories.user_preferences_repository import (
    SQLAlchemyUserPreferencesRepository,
)
from storico.infrastructure.database.repositories.user_repository import (
    SQLAlchemyUserRepository,
)
from storico.infrastructure.database.repositories.user_story_repository import (
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.database.repositories.workspace_repository import (
    SQLAlchemyWorkspaceRepository,
)
from storico.infrastructure.database.repositories.workspace_member_repository import (
    SQLAlchemyWorkspaceMemberRepository,
)
from storico.infrastructure.database.repositories.workspace_llm_config_repository import (
    SQLAlchemyWorkspaceLLMConfigRepository,
)
from storico.infrastructure.database.repositories.workspace_prompt_repository import (
    SQLAlchemyWorkspacePromptRepository,
)

__all__ = [
    "SQLAlchemyUserRepository",
    "SQLAlchemyUserPreferencesRepository",
    "SQLAlchemyProjectRepository",
    "SQLAlchemyUserStoryRepository",
    "SQLAlchemyTaskRepository",
    "SQLAlchemyExtractionRepository",
    "SQLAlchemyWorkspaceRepository",
    "SQLAlchemyWorkspaceMemberRepository",
    "SQLAlchemyWorkspaceLLMConfigRepository",
    "SQLAlchemyWorkspacePromptRepository",
]
