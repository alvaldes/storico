"""Guard for the canonical error envelope of the domain-error handlers.

Feature ``api-error-code-envelope`` (decisions D2/D3): every handler in
``storico.api.errors`` must emit exactly one machine-readable code, top-level
``error_code`` with SCREAMING_SNAKE values. ``type`` is not part of the envelope
and must never reappear.

Pure unit test: handlers are called directly with a stand-in Request — no app,
no database, no Docker.
"""

from __future__ import annotations

import asyncio
import json
import re
from uuid import uuid4

import pytest

from storico.api import errors
from storico.domain.entities import (
    CannotRemoveOwnerError,
    DuplicateEntity,
    EntityNotFound,
    InsufficientRole,
    LastAdminError,
    LLMConnectionError,
    LLMModelNotFoundError,
    LLMResponseError,
    OwnerTransferError,
    ParseError,
    RepositoryError,
)
from storico.domain.entities.exceptions import (
    CipherError,
    CredentialUndecryptable,
    EncryptionKeyMissing,
)

ERROR_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


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


CASES = [
    (
        errors.entity_not_found_handler,
        EntityNotFound("Project", "abc-123"),
        "ENTITY_NOT_FOUND",
        {},
    ),
    (
        errors.duplicate_entity_handler,
        DuplicateEntity("Project", "name", "alpha"),
        "DUPLICATE_ENTITY",
        {},
    ),
    (
        errors.repository_error_handler,
        RepositoryError("connection reset"),
        "REPOSITORY_ERROR",
        {},
    ),
    (errors.generic_error_handler, RuntimeError("boom"), "INTERNAL_ERROR", {}),
    (
        errors.llm_connection_error_handler,
        LLMConnectionError("cannot reach host"),
        "LLM_CONNECTION_ERROR",
        {"message": "cannot reach host"},
    ),
    (
        errors.llm_model_not_found_handler,
        LLMModelNotFoundError("llama3.2"),
        "LLM_MODEL_NOT_FOUND",
        {"model": "llama3.2"},
    ),
    (
        errors.llm_response_error_handler,
        LLMResponseError("unparseable output"),
        "LLM_RESPONSE_ERROR",
        {"message": "unparseable output"},
    ),
    (errors.parse_error_handler, ParseError("bad format"), "PARSE_ERROR", {}),
    (
        errors.insufficient_role_handler,
        InsufficientRole(uuid4(), uuid4(), "admin"),
        "INSUFFICIENT_ROLE",
        {},
    ),
    (
        errors.owner_transfer_error_handler,
        OwnerTransferError("transfer failed"),
        "OWNER_TRANSFER_ERROR",
        {},
    ),
    (
        errors.last_admin_error_handler,
        LastAdminError(),
        "LAST_ADMIN_ERROR",
        {},
    ),
    (
        errors.cannot_remove_owner_handler,
        CannotRemoveOwnerError(),
        "CANNOT_REMOVE_OWNER",
        {},
    ),
    (
        errors.cipher_error_handler,
        EncryptionKeyMissing(),
        "ENCRYPTION_KEY_MISSING",
        {},
    ),
    (
        errors.cipher_error_handler,
        CredentialUndecryptable(),
        "CREDENTIAL_UNDECRYPTABLE",
        {},
    ),
    (errors.cipher_error_handler, CipherError("generic cipher failure"), "CIPHER_ERROR", {}),
]

CASE_IDS = [f"{case[0].__name__}:{case[2]}" for case in CASES]


@pytest.mark.unit
@pytest.mark.parametrize("handler,exc,expected_code,expected_extra", CASES, ids=CASE_IDS)
def test_handler_emits_canonical_error_envelope(handler, exc, expected_code, expected_extra):
    response = _call(handler, exc)
    body = _body(response)

    assert body["error_code"] == expected_code
    assert ERROR_CODE_RE.match(body["error_code"])
    assert "type" not in body
    for key, value in expected_extra.items():
        assert body[key] == value
