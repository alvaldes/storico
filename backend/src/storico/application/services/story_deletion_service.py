"""StoryDeletionService — the sanctioned deletion's ordering owner.

The delete of a story that carries extraction versions is not a single
``DELETE`` statement: it is snapshot → vector cleanup → delete-with-record, in
that exact order (design.md, "Decision: story deletion is snapshot → vector
cleanup → delete-with-record, in one transaction"). The service owns that
ordering and nothing else: authorization is the route's gate
(``require_story_owner_or_admin``), and the atomicity of the last step is the
repository's (``delete_with_record``, one transaction). A vector-store failure
raises ``VectorStoreError`` out of step 3, aborting the operation before the
relational delete runs, so the story and its versions stay intact for a retry.
"""

from __future__ import annotations

from uuid import UUID

from storico.domain.entities import EntityNotFound, UserStory
from storico.domain.entities.story_deletion import StoryDeletion
from storico.domain.ports.extraction_repository import ExtractionRepository
from storico.domain.ports.project_repository import ProjectRepository
from storico.domain.ports.user_story_repository import UserStoryRepository
from storico.domain.ports.vector_store_port import VectorStorePort


class StoryDeletionService:
    """Runs the sanctioned story deletion: snapshot, vector cleanup, record."""

    def __init__(
        self,
        story_repo: UserStoryRepository,
        extraction_repo: ExtractionRepository,
        project_repo: ProjectRepository,
        vector_store: VectorStorePort | None,
    ) -> None:
        self._story_repo = story_repo
        self._extraction_repo = extraction_repo
        self._project_repo = project_repo
        self._vector_store = vector_store

    async def delete_story(self, story: UserStory, *, deleted_by: UUID | None) -> StoryDeletion:
        """Delete ``story`` and return the audit record that was written.

        Steps, in the fixed order:

        1. **snapshot** — ``list_versions`` reads the story's versions (newest
           first) so the record can name exactly what this deletion destroys;
        2. **record** — build the frozen ``StoryDeletion`` from the story's
           identity as values. ``version_numbers`` is stored **ascending**
           (``sorted(...)``), not in the read's ``DESC`` order: the record is
           ``[1, 2]`` by spec, and an audit row whose order flipped with a
           repository read order would be a needless trap;
        3. **vector cleanup** — remove the story's points when a store is
           configured. ``vector_store is None`` means "no store is
           configured", a legitimate completion with nothing to clean; a
           *configured* store that cannot be reached raises
           ``VectorStoreError`` and aborts the whole operation;
        4. **relational** — ``delete_with_record`` removes the story and
           writes the record in one transaction. The story's versions and
           their tasks disappear through the ``0014`` cascade.

        The workspace id is resolved from the story's project here rather than
        accepted from the caller: the gate already walked that path, so the
        second read is one cheap query, and the service stays independent of
        HTTP concerns. A missing project raises ``EntityNotFound`` —
        unreachable through the gate, but honest.

        Raises:
            EntityNotFound: when the story's project no longer resolves.
            VectorStoreError: when a configured vector store cannot be
                reached; the relational delete never runs in that case.
        """
        project = await self._project_repo.find_by_id(story.project_id)
        if project is None:
            raise EntityNotFound("UserStory", str(story.id))

        # 1. snapshot: the read returns version_number DESC, newest first.
        versions = await self._extraction_repo.list_versions(story.id)

        # 2. record: the identity as values, the destroyed numbers ascending.
        record = StoryDeletion(
            story_id=story.id,
            project_id=story.project_id,
            workspace_id=project.workspace_id,
            actor=story.actor,
            feature=story.feature,
            benefit=story.benefit,
            version_numbers=sorted(v.version_number for v in versions),
            deleted_by=deleted_by,
        )

        # 3. vector cleanup: skipped when no store is configured — no points
        # exist to clean; a configured-but-unreachable store raises and aborts.
        if self._vector_store is not None:
            await self._vector_store.delete_by_story(
                workspace_id=project.workspace_id,
                user_story_id=str(story.id),
            )

        # 4. relational: one transaction — story DELETE plus record INSERT.
        await self._story_repo.delete_with_record(story.id, record)
        return record
