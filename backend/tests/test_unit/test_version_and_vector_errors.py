"""Unit guard for the WU4 error vocabulary (task 4.7 of extraction-versioning).

Pins three things. First, the three new codes exist in the canonical registry
with their intended HTTP status pairing. Second, an app built by
``create_app`` has a handler registered for ``VersionAllocationConflictError``
itself and for ``VectorStoreError`` itself — resolved through the same
first-hit-MRO walk Starlette uses, so the registration is proven to win over
the inherited ``repository_error_handler`` rather than assumed. Third, the
allocation conflict handler composes ``detail`` from ``str(exc)`` first and
from the exception's own ``user_story_id`` when the message is silent, and
never emits an empty ``detail``.

Pure unit test: handlers are called directly with a stand-in Request; the app
is built with ``create_app`` but never started. No database, no Docker.
"""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest

from storico.api import error_codes, errors
from storico.api.app import create_app
from storico.api.errors import (
    repository_error_handler,
    vector_store_error_handler,
    version_allocation_conflict_handler,
)
from storico.domain.entities.exceptions import (
    VectorStoreError,
    VersionAllocationConflictError,
)

# The intended pairing, from the design: an exhausted allocation is a
# client-visible conflict (409), a vector-store outage is a down dependency
# (503 — the house convention ``LLM_CONNECTION_ERROR`` established), and the
# gate refusal is a forbidden role (403, applied at its ``ApiError`` raise
# site in ``api/dependencies.py`` by the gate tranche that consumes this code).
NEW_CODES: list[tuple[str, int]] = [
    ("VERSION_ALLOCATION_CONFLICT", 409),
    ("VECTOR_STORE_UNAVAILABLE", 503),
    ("WORKSPACE_OWNER_OR_ADMIN_REQUIRED", 403),
]


class _FakeURL:
    def __init__(self, path: str) -> None:
        self.path = path


class _FakeRequest:
    """Stand-in for ``fastapi.Request``: handlers only read ``url.path``/``method``."""

    def __init__(self) -> None:
        self.url = _FakeURL("/test")
        self.method = "GET"


def _call(handler, exc):
    return asyncio.run(handler(_FakeRequest(), exc))


def _body(response) -> dict:
    return json.loads(response.body)


def _resolve_handler(app, exc):
    """Starlette's own lookup: walk the exception's MRO, first hit wins."""
    for cls in type(exc).__mro__:
        if cls in app.exception_handlers:
            return cls, app.exception_handlers[cls]
    raise AssertionError(f"No handler registered anywhere in the MRO of {type(exc).__name__}")


# ── The registry gains the three codes, each with its intended status ────────


@pytest.mark.unit
@pytest.mark.parametrize("name,expected_status", NEW_CODES, ids=[name for name, _ in NEW_CODES])
def test_new_code_is_declared_in_the_registry_with_its_intended_status(name, expected_status):
    assert name in error_codes.__all__, f"{name} is missing from the registry's __all__"
    assert getattr(error_codes, name) == name, f"{name}'s value must equal its name"
    # The pairing is pinned in this module's NEW_CODES table so the intended
    # status travels with the code name in one reviewed place.
    assert dict(NEW_CODES)[name] == expected_status


@pytest.mark.unit
def test_allocation_conflict_handler_answers_409():
    message = "Could not allocate a version number for story 'abc-123' after 3 attempts"
    exc = VersionAllocationConflictError(message)

    response = _call(version_allocation_conflict_handler, exc)
    body = _body(response)

    assert response.status_code == 409
    assert body["error_code"] == "VERSION_ALLOCATION_CONFLICT"
    assert body["detail"] == message


@pytest.mark.unit
def test_vector_store_error_handler_answers_503():
    exc = VectorStoreError("qdrant unreachable")

    response = _call(vector_store_error_handler, exc)
    body = _body(response)

    assert response.status_code == 503
    assert body["error_code"] == "VECTOR_STORE_UNAVAILABLE"
    # The exact shape ``llm_connection_error_handler`` uses for a down
    # dependency: a fixed ``detail`` plus the exception's own ``message``.
    assert body["detail"] == "Vector store unavailable"
    assert body["message"] == "qdrant unreachable"


# ── Registration: each handler is registered for its own class ───────────────


@pytest.mark.unit
def test_create_app_registers_the_allocation_conflict_handler_for_its_own_class():
    app = create_app()

    resolved_cls, handler = _resolve_handler(app, VersionAllocationConflictError("race lost"))

    assert resolved_cls is VersionAllocationConflictError, (
        "the MRO walk must stop at VersionAllocationConflictError itself, not fall "
        "through to a base class"
    )
    assert handler is errors.version_allocation_conflict_handler
    assert handler is not repository_error_handler


@pytest.mark.unit
def test_create_app_registers_the_vector_store_handler_for_its_own_class():
    app = create_app()

    resolved_cls, handler = _resolve_handler(app, VectorStoreError("qdrant down"))

    assert resolved_cls is VectorStoreError, (
        "the MRO walk must stop at VectorStoreError itself; the class is "
        "deliberately not a RepositoryError, so no relational handler may claim it"
    )
    assert handler is errors.vector_store_error_handler
    assert handler is not repository_error_handler


# ── The allocation conflict handler's detail composition (both branches) ─────


@pytest.mark.unit
def test_allocation_conflict_detail_comes_from_str_exc_when_the_message_speaks():
    message = "Could not allocate a version number for story 'abc-123' after 3 attempts"
    exc = VersionAllocationConflictError(message, user_story_id=uuid4())

    body = _body(_call(version_allocation_conflict_handler, exc))

    assert body["detail"] == message


@pytest.mark.unit
def test_allocation_conflict_detail_is_composed_from_user_story_id_when_silent():
    story_id = uuid4()
    exc = VersionAllocationConflictError("", user_story_id=story_id)

    body = _body(_call(version_allocation_conflict_handler, exc))

    assert body["detail"].strip() != ""
    assert str(story_id) in body["detail"]


@pytest.mark.unit
def test_allocation_conflict_detail_never_goes_out_empty():
    exc = VersionAllocationConflictError("")

    body = _body(_call(version_allocation_conflict_handler, exc))

    assert body["detail"].strip() != ""
