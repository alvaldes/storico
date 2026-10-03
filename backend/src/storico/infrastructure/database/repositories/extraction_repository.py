"""SQLAlchemy implementation of the ExtractionRepository port."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from uuid import UUID

from sqlalchemy import Update, func, insert, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import EntityNotFound, Extraction, RepositoryError
from storico.domain.entities.exceptions import VersionAllocationConflictError
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.user_story import UserStoryStatus
from storico.domain.ports import ExtractionRepository
from storico.infrastructure.database.models import ExtractionModel, ProjectModel, UserStoryModel
from storico.infrastructure.database.pagination import fetch_page, with_total

# Bounded allocation: a lost race is retried, a conflict on every attempt is a loud
# failure with its own exception type. The bound lives in the adapter — the port never
# learns the word "retry".
MAX_ALLOCATION_ATTEMPTS = 3

# The constraint the allocation race is lost on. Written here as the single literal the
# migration, the model and this discrimination all name.
_VERSION_CONSTRAINT = "uq_extractions_story_version"


def _is_version_conflict(exc: IntegrityError) -> bool:
    """True exactly when *exc* is the per-story version-pair unique violation.

    Both driver shapes are read, so the retry never depends on an attribute a driver
    version may or may not expose: the asyncpg shape carries ``constraint_name`` on the
    driver error (``exc.orig``), the sqlite3 shape reports the violated table/column pair
    in the message, and psycopg names the constraint in its message. Anything else —
    notably a ``NOT NULL`` violation — is not a collision and must not burn the retry
    bound before reporting a conflict that never happened.
    """
    orig = exc.orig
    constraint_name = getattr(orig, "constraint_name", None)
    if constraint_name is not None:
        return constraint_name == _VERSION_CONSTRAINT
    message = str(orig)
    if _VERSION_CONSTRAINT in message:
        return True
    return "UNIQUE constraint failed" in message and (
        "extractions.user_story_id" in message and "extractions.version_number" in message
    )


class SQLAlchemyExtractionRepository(ExtractionRepository):
    """Repository implementation for Extraction entities using SQLAlchemy async sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_next_version(self, extraction: Extraction) -> Extraction:
        """Insert the extraction with its version number minted inside the INSERT.

        One statement computes ``max(version_number) + 1`` for the story and inserts
        the row with it — read and write cannot be split by ``asyncio.create_task``
        interleaving. A lost race surfaces as the per-story unique violation; the
        statement is retried inside a fresh transaction up to
        ``MAX_ALLOCATION_ATTEMPTS`` times. Any other integrity failure (a ``NOT NULL``
        on ``provider``, a null ``model_used``) is discriminated *before* the generic
        wrap and reported immediately instead of burning the bound. A conflict on
        every attempt raises ``VersionAllocationConflictError``.

        The returned entity is the only source of the minted number: any
        ``version_number`` the passed entity carries is ignored.
        """
        stmt = (
            insert(ExtractionModel)
            .values(
                **self._to_orm_kwargs(extraction),
                version_number=(
                    select(func.coalesce(func.max(ExtractionModel.version_number), 0) + 1)
                    .where(ExtractionModel.user_story_id == extraction.user_story_id)
                    .scalar_subquery()
                ),
            )
            .returning(ExtractionModel.version_number)
        )
        for _attempt in range(MAX_ALLOCATION_ATTEMPTS):
            try:
                result = await self._session.execute(stmt)
                version_number = result.scalar_one()
            except IntegrityError as exc:
                # Discriminated before the ``SQLAlchemyError`` wrap: ``IntegrityError``
                # is a subclass, so this arm must come first.
                await self._session.rollback()
                if not _is_version_conflict(exc):
                    raise RepositoryError("Database error creating extraction") from exc
                continue
            except SQLAlchemyError as e:
                await self._session.rollback()
                raise RepositoryError("Database error creating extraction") from e
            await self._session.commit()
            return replace(extraction, version_number=version_number)
        raise VersionAllocationConflictError(
            f"Could not allocate a version number for story '{extraction.user_story_id}' "
            f"after {MAX_ALLOCATION_ATTEMPTS} attempts"
        )

    async def record_rendered_prompt(
        self,
        extraction_id: UUID,
        *,
        prompt_rendered: str,
        prompt_config: dict | None,
    ) -> None:
        """Write the rendered prompt and its config — the two columns, nothing else.

        ``prompt_config`` is replaced wholesale (Postgres ``json`` has no merge
        operator), so the caller restates the keys it wants stored.
        """
        stmt = (
            update(ExtractionModel)
            .where(ExtractionModel.id == extraction_id)
            .values(prompt_rendered=prompt_rendered, prompt_config=prompt_config)
        )
        try:
            result = await self._session.execute(stmt)
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error recording rendered prompt") from e
        if result.rowcount == 0:
            await self._session.rollback()
            raise EntityNotFound("Extraction", str(extraction_id))
        await self._session.commit()

    async def record_usage(
        self,
        extraction_id: UUID,
        *,
        prompt_config: dict,
    ) -> None:
        """Record the usage container on the snapshot — one UPDATE, only ``prompt_config``.

        Mirrors ``record_rendered_prompt``'s shape but names no other column: the
        rendered prompt, provider/model/temperature and status columns keep the
        values written at birth/render time because this statement cannot touch
        them.
        """
        stmt = (
            update(ExtractionModel)
            .where(ExtractionModel.id == extraction_id)
            .values(prompt_config=prompt_config)
        )
        try:
            result = await self._session.execute(stmt)
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error recording usage") from e
        if result.rowcount == 0:
            await self._session.rollback()
            raise EntityNotFound("Extraction", str(extraction_id))
        await self._session.commit()

    async def mark_completed(
        self,
        extraction_id: UUID,
        *,
        raw_response: str,
        confidence_score: float | None,
        completed_at: datetime,
    ) -> None:
        """Mark the extraction completed with one targeted UPDATE.

        The statement names exactly these columns and no snapshot column — not
        preserved by convention, but unreachable. The status pair is hardcoded here
        because ``COMPLETED`` and ``EXTRACTED`` move together and no caller may pair
        them differently.
        """
        stmt = (
            update(ExtractionModel)
            .where(ExtractionModel.id == extraction_id)
            .values(
                status=ExtractionStatus.COMPLETED,
                user_story_status=UserStoryStatus.EXTRACTED,
                raw_response=raw_response,
                confidence_score=confidence_score,
                completed_at=completed_at,
            )
        )
        await self._execute_mark(stmt, extraction_id)

    async def mark_failed(
        self,
        extraction_id: UUID,
        *,
        error_info: str,
        completed_at: datetime,
    ) -> None:
        """Mark the extraction failed with one targeted UPDATE.

        The statement names exactly these columns and no snapshot column: a failed
        version keeps its number, provider, temperature and rendered prompt.
        """
        stmt = (
            update(ExtractionModel)
            .where(ExtractionModel.id == extraction_id)
            .values(
                status=ExtractionStatus.FAILED,
                user_story_status=UserStoryStatus.FAILED_EXTRACTION,
                error_info=error_info,
                completed_at=completed_at,
            )
        )
        await self._execute_mark(stmt, extraction_id)

    async def _execute_mark(self, stmt: Update, extraction_id: UUID) -> None:
        """Run one mark statement; raise ``EntityNotFound`` when no row matched."""
        try:
            result = await self._session.execute(stmt)
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error marking extraction") from e
        if result.rowcount == 0:
            await self._session.rollback()
            raise EntityNotFound("Extraction", str(extraction_id))
        await self._session.commit()

    async def find_by_id(self, extraction_id: UUID) -> Extraction | None:
        result = await self._session.get(ExtractionModel, extraction_id)
        return self._to_domain(result) if result else None

    async def find_current_version(self, user_story_id: UUID) -> Extraction | None:
        """Return the story's current version — derived, never stored.

        The highest-numbered completed version wins; a pending or failed run above it
        never steals the title. Served by ``uq_extractions_story_version``.
        """
        stmt = (
            select(ExtractionModel)
            .where(
                ExtractionModel.user_story_id == user_story_id,
                ExtractionModel.status == ExtractionStatus.COMPLETED,
            )
            .order_by(ExtractionModel.version_number.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def list_versions(self, user_story_id: UUID) -> list[Extraction]:
        """Every version of the story, ordered ``version_number DESC``, newest first.

        Deliberately unbounded: the version list is the pagination *input* for the
        version selector, not a paginated resource, and the paginator's 20/100 window
        would truncate a long history silently — exactly the failure this read exists
        to avoid. A story's version count is bounded by hand-run extractions, so no
        window is applied here, and a ``pending`` or ``failed`` run is part of the
        history the user must see, never filtered out.

        Agreement with ``find_current_version``: "current" is derived here as the
        first ``completed`` entry of this ordered list and there as a ``LIMIT 1``
        query; both mean "highest-numbered completed version", and the repository
        test pinning one against the other for a three-version story is what keeps
        them in step. Do not unify them by making ``find_current_version`` load this
        list and filter in Python: it sits on the hot path of every task write (the
        frozen check) and must stay a ``LIMIT 1`` query.
        """
        stmt = (
            select(ExtractionModel)
            .where(ExtractionModel.user_story_id == user_story_id)
            .order_by(ExtractionModel.version_number.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(model) for model in result.scalars()]

    async def list_page(
        self,
        *,
        workspace_id: UUID | None = None,
        user_story_id: UUID | None = None,
        workspace_ids: list[UUID] | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[Extraction], int]:
        """Return one page of extractions for exactly one scope, plus the total.

        The page and its total come from one statement: ``count(*) OVER ()``
        rides on the rows' own query (see ``fetch_page``), so no separate
        ``SELECT COUNT(*)`` is issued on the normal path.

        An empty ``workspace_ids`` is answered here rather than sent as
        ``IN ()``: no memberships means no rows, not a statement — and against
        the dev pooler a statement costs ~2s (a bare ``SELECT 1`` already
        measures 800ms in ``/api/v1/health``), so an unasked statement is pure
        latency. This is also what replaced the old per-workspace fold, whose
        caller in 12 workspaces paid for 12 statements and measured 25-32s.

        Results are ordered by ``created_at DESC, id DESC`` in SQL — a
        requirement, not decoration: ``LIMIT``/``OFFSET`` over an unordered
        set is undefined behaviour and a row could repeat or vanish between
        pages. ``id DESC`` is the tiebreaker, so two rows written in the same
        instant cannot swap.

        More than one scope is refused rather than resolved: the three arguments
        are mutually exclusive, and a plain ``if``/``elif`` chain would let a
        caller pass two and silently get one of them -- a wrong answer that looks
        like a right one, which is the exact failure mode this change removes.
        """
        scopes = [
            value for value in (workspace_ids, user_story_id, workspace_id) if value is not None
        ]
        if len(scopes) != 1:
            raise ValueError(
                "list_page requires exactly one of workspace_id, user_story_id or workspace_ids; "
                f"got {len(scopes)}"
            )

        if workspace_ids is not None:
            if not workspace_ids:
                return [], 0
            scope = ProjectModel.workspace_id.in_(workspace_ids)
            stmt = select(ExtractionModel).join(UserStoryModel).join(ProjectModel).where(scope)
            count_stmt = (
                select(func.count())
                .select_from(ExtractionModel)
                .join(UserStoryModel)
                .join(ProjectModel)
                .where(scope)
            )
        elif user_story_id is not None:
            # No join: extractions carry their own ``user_story_id`` foreign key.
            scope = ExtractionModel.user_story_id == user_story_id
            stmt = select(ExtractionModel).where(scope)
            count_stmt = select(func.count()).select_from(ExtractionModel).where(scope)
        elif workspace_id is not None:
            # Extractions have no workspace column: walk ``extraction → story → project``.
            scope = ProjectModel.workspace_id == workspace_id
            stmt = select(ExtractionModel).join(UserStoryModel).join(ProjectModel).where(scope)
            count_stmt = (
                select(func.count())
                .select_from(ExtractionModel)
                .join(UserStoryModel)
                .join(ProjectModel)
                .where(scope)
            )
        stmt = stmt.order_by(ExtractionModel.created_at.desc(), ExtractionModel.id.desc())
        rows, total = await fetch_page(
            self._session, with_total(stmt), count_stmt, limit=limit, offset=offset
        )
        return [self._to_domain(model) for model, _total in rows], total

    async def list(self) -> list[Extraction]:
        result = await self._session.execute(select(ExtractionModel))
        return [self._to_domain(row) for row in result.scalars()]

    def _to_domain(self, model: ExtractionModel) -> Extraction:
        return Extraction(
            user_story_id=model.user_story_id,
            model_used=model.model_used,
            raw_response=model.raw_response,
            provider=model.provider,
            temperature=model.temperature,
            status=ExtractionStatus(model.status),
            user_story_status=UserStoryStatus(model.user_story_status),
            error_info=model.error_info,
            prompt_config=model.prompt_config,
            confidence_score=model.confidence_score,
            id=model.id,
            created_at=model.created_at,
            completed_at=model.completed_at,
            version_number=model.version_number,
            prompt_rendered=model.prompt_rendered,
        )

    @staticmethod
    def _to_orm_kwargs(extraction: Extraction) -> dict:
        return {
            "id": extraction.id,
            "user_story_id": extraction.user_story_id,
            "model_used": extraction.model_used,
            # ``version_number`` is deliberately absent: only ``create_next_version``'s
            # statement may ever set it, and ignoring any value the entity carries is
            # what makes that structural.
            "provider": extraction.provider,
            "temperature": extraction.temperature,
            "prompt_rendered": extraction.prompt_rendered,
            "status": extraction.status.value,
            "user_story_status": extraction.user_story_status.value,
            "error_info": extraction.error_info,
            "raw_response": extraction.raw_response,
            "prompt_config": extraction.prompt_config,
            "confidence_score": extraction.confidence_score,
            "created_at": extraction.created_at,
            "completed_at": extraction.completed_at,
        }
