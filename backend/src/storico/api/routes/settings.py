"""Settings API routes — user preferences CRUD + account deletion."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from storico.api.dependencies import get_current_user, get_repository
from storico.api.error_codes import ACCOUNT_DELETE_BLOCKED
from storico.api.errors import ApiError
from storico.api.schemas.settings import (
    REMOVED_PREFERENCE_KEYS,
    RETIRED_EXPORT_FORMATS,
    AppSettings,
    DeleteAccountResponse,
    UserPreferencesResponse,
    UserPreferencesUpdate,
)
from storico.domain.entities import User
from storico.infrastructure.database.repositories import (
    SQLAlchemyTaskInvalidationRepository,
    SQLAlchemyUserPreferencesRepository,
    SQLAlchemyUserRepository,
)

# ── User Settings Router ──────────────────────────────────────────────────────

settings_router = APIRouter(
    prefix="/api/v1/users/me",
    tags=["settings"],
)

CurrentUserDep = Annotated[User, Depends(get_current_user)]
PrefRepoDep = Annotated[
    SQLAlchemyUserPreferencesRepository,
    Depends(get_repository(SQLAlchemyUserPreferencesRepository)),
]
UserRepoDep = Annotated[
    SQLAlchemyUserRepository,
    Depends(get_repository(SQLAlchemyUserRepository)),
]
InvalidationRepoDep = Annotated[
    SQLAlchemyTaskInvalidationRepository,
    Depends(get_repository(SQLAlchemyTaskInvalidationRepository)),
]


@settings_router.get(
    "/settings",
    response_model=UserPreferencesResponse,
    response_model_by_alias=True,
)
async def get_settings(
    current_user: CurrentUserDep,
    repo: PrefRepoDep,
) -> UserPreferencesResponse:
    """Return the current user's application preferences.

    Returns defaults (from pydantic schema) when no preferences exist yet.

    A stored document is read through the schema with the removed keys dropped: ``AppSettings``
    forbids extras, so a row written before the per-user LLM block was removed would otherwise
    fail validation and answer 500. Revision ``0022`` cleaned storage; this covers a row it did
    not reach.
    """
    existing = await repo.get(current_user.id)
    if existing is None:
        return UserPreferencesResponse(
            preferences=AppSettings(),
            updated_at=current_user.created_at,
        )
    return UserPreferencesResponse(
        preferences=AppSettings(**_for_schema(existing.preferences)),
        updated_at=existing.updated_at,
    )


def _for_schema(stored: dict) -> dict:
    """A stored document the schema can accept: removed keys dropped, retired values rewritten.

    Applied on both directions of the contract, not only where it is needed today. The read
    needs it (a row written before the removal must not 500 the endpoint); the write response
    does not, because ``PUT`` validates the body against ``AppSettings`` and both a removed key
    and a retired value are refused there. Going through the same helper anyway is what keeps
    the invariant "anything this endpoint hands to ``AppSettings`` from storage has been
    through this reconciliation" true by construction, rather than by one call site
    remembering it.

    The two halves have to differ, and the difference is the schema's: ``extra="forbid"``
    refuses a removed *key*, so dropping it is enough, while a retired *value* is invisible to
    it and fails the ``Literal`` instead — so the value is rewritten, not dropped.

    Both spellings the store can hold are rewritten: ``model_dump()`` writes ``default_format``
    and a client on the old contract wrote ``defaultFormat``, and ``populate_by_name`` makes
    either validate. Nothing else in the document is touched.
    """
    reconciled = {key: value for key, value in stored.items() if key not in REMOVED_PREFERENCE_KEYS}
    export = reconciled.get("export")
    if isinstance(export, dict):
        export = dict(export)
        for spelling in ("default_format", "defaultFormat"):
            stored_value = export.get(spelling)
            # ``isinstance`` before the membership test: a JSON document can hold any scalar,
            # and ``in`` on a dict hashes the value.
            if isinstance(stored_value, str) and stored_value in RETIRED_EXPORT_FORMATS:
                export[spelling] = RETIRED_EXPORT_FORMATS[stored_value]
        reconciled["export"] = export
    return reconciled


@settings_router.put(
    "/settings",
    response_model=UserPreferencesResponse,
    response_model_by_alias=True,
)
async def update_settings(
    body: UserPreferencesUpdate,
    current_user: CurrentUserDep,
    repo: PrefRepoDep,
) -> UserPreferencesResponse:
    """Create or replace the current user's application preferences."""
    prefs = await repo.upsert(
        current_user.id,
        body.preferences.model_dump(),
    )
    return UserPreferencesResponse(
        preferences=AppSettings(**_for_schema(prefs.preferences)),
        updated_at=prefs.updated_at,
    )


# ── Account Deletion ──────────────────────────────────────────────────────────


@settings_router.delete("", response_model=DeleteAccountResponse)
async def delete_account(
    current_user: CurrentUserDep,
    repo: UserRepoDep,
    invalidation_repo: InvalidationRepoDep,
) -> DeleteAccountResponse:
    """Permanently delete the current user's account and ALL associated data.

    This action cannot be undone. All projects, stories, tasks, extractions,
    and linked accounts are cascade-deleted — with one designed refusal: if
    the account's invalidation revocations still stand, the delete is refused
    with 409 ``ACCOUNT_DELETE_BLOCKED`` before anything is touched.
    ``fk_task_invalidations_revoked_by_users`` is ``ON DELETE RESTRICT``, so
    those rows refuse to lose their revoker; the pre-check names each blocking
    mark (story id, version number, task title) so the user can act on it —
    by having the marking stories deleted, since a revoke is history and has
    no undo endpoint. A revoke that lands between the pre-check and the delete
    still surfaces as the raw integrity refusal: translating it belongs to
    ``UserRepository.delete``, which this route does not own.
    """
    standing = await invalidation_repo.list_standing_revocations_by_user(current_user.id)
    if standing:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            error_code=ACCOUNT_DELETE_BLOCKED,
            detail={
                "message": (
                    "This account's invalidation revocations still stand, and the "
                    "marked rows refuse to lose their revoker. Delete the stories "
                    "that hold the marked tasks, then delete the account."
                ),
                "count": len(standing),
                "revocations": [
                    {
                        "user_story_id": str(entry.user_story_id),
                        "version_number": entry.version_number,
                        "task_title": entry.title,
                    }
                    for entry in standing
                ],
            },
        )
    await repo.delete(current_user.id)
    return DeleteAccountResponse()
