"""RequestValidationError coverage: FastAPI's own 422 carries an app code.

WU2 of ``api-error-code-envelope`` (decision D2): the raw FastAPI default 422 body
carries no app code at all. The frontend already parses this list detail
(``api.ts`` ``buildErrorMessage`` reads ``first.msg``), so the handler must keep
``detail`` byte-identical to FastAPI's default list shape and only ADD top-level
``error_code``.

Route-level test over the real app (httpx over ASGITransport, in-memory SQLite):
no Docker, no external services.
"""

import pytest

pytestmark = pytest.mark.unit


async def test_request_validation_error_carries_app_code(authed_client, db_session, seed_workspace):
    """A 422 from body validation gains top-level ``error_code``; detail stays the list."""
    ws = await seed_workspace(stories=0)
    response = await authed_client.post(
        f"/api/v1/workspaces/{ws.workspace_id}/projects/",
        json={"description": "no name here"},
    )
    body = response.json()

    assert response.status_code == 422
    assert body["error_code"] == "REQUEST_VALIDATION_FAILED"
    # ``detail`` must stay the list shape the frontend parses: every item with
    # ``msg`` (and the type/loc/input trio FastAPI's default puts there).
    #
    # Fidelity to the default was measured, not assumed: on FastAPI 0.139.0 the same
    # request without our handler returns
    # ``[{"type": "missing", "loc": ["body", "name"], "msg": "Field required", "input": {...}}]``
    # and ``jsonable_encoder(exc.errors())`` reproduces it item-for-item (deep-equal),
    # with no ``url`` key in this version. The assertions stay on ``msg`` rather than
    # pinning the exact key set on purpose: a future FastAPI that adds a field must not
    # fail a test over a key the frontend ignores.
    assert isinstance(body["detail"], list)
    assert all(isinstance(item, dict) for item in body["detail"])
    assert all("msg" in item for item in body["detail"])
