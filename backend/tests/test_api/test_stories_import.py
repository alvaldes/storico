"""Integration tests for the CSV story-import endpoint.

``POST /api/v1/workspaces/{workspace_id}/stories/import`` accepts a multipart
upload carrying ``project_id`` as a form field alongside the CSV file. The
header selects the mode: ``actor,feature,benefit`` (parts mode) or
``story``/``input``/``raw_text`` (full mode, parsed to parts). The contract
under test: blocking row errors reject the whole file with nothing written,
duplicates are skipped and reported but never block, and the byte cap is
enforced before any parsing.

The route is workspace-scoped, like every newer feature in this API. The flat
legacy router was the wrong home for it: an import must resolve workspace
membership from the path before anything else, and a flat path cannot.
"""

import csv
import io
from uuid import uuid4

from starlette.datastructures import UploadFile as StarletteUploadFile

from storico.domain.services.story_import import CANONICAL_RAW_TEXT_TEMPLATE

IMPORT_PATH = "/api/v1/workspaces/{workspace_id}/stories/import"


def canonical_text(actor: str, feature: str, benefit: str) -> str:
    """The canonical user-story sentence built from its three parts.

    Built from the implementation's own template rather than retyped here: a test-side copy
    of a contract is exactly how the two drift apart, and this string is the text that
    becomes the LLM prompt.
    """
    return CANONICAL_RAW_TEXT_TEMPLATE.format(actor=actor, feature=feature, benefit=benefit)


def csv_bytes(header: list[str], rows: list[list[str]]) -> bytes:
    """Encode a header plus data rows as UTF-8 CSV bytes."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


async def _import_file(client, workspace_id, project_id, payload: bytes):
    return await client.post(
        IMPORT_PATH.format(workspace_id=workspace_id),
        data={"project_id": str(project_id)},
        files={"file": ("stories.csv", payload, "text/csv")},
    )


async def _list_project_stories(client, project_id) -> list[dict]:
    response = await client.get(f"/api/v1/stories/?project_id={project_id}")
    assert response.status_code == 200
    return response.json()["items"]


def _error_envelope(response) -> dict:
    """Unwrap the typed error payload from its ``detail`` envelope.

    ``HTTPException(detail={...})`` serialises as ``{"detail": {...}}``, which is the shape
    published for this endpoint and the one the extraction route already uses for
    ``LLM_CONFIG_INCOMPLETE``. Unwrapping here keeps that shape asserted in one place.
    """
    body = response.json()
    assert isinstance(body["detail"], dict), body
    return body["detail"]


class TestImportPartsMode:
    """POST import with an ``actor,feature,benefit`` header."""

    async def test_import_three_rows_creates_three_stories(self, authed_client, seed_workspace):
        """Three valid rows into an empty project create three stories verbatim."""
        seeded = await seed_workspace(stories=0)
        rows = [
            ["user", "log in", "access my account"],
            ["admin", "view profile", "see my details"],
            ["user", "reset password", "regain access"],
        ]
        response = await _import_file(
            authed_client,
            seeded.workspace_id,
            seeded.project_id,
            csv_bytes(["actor", "feature", "benefit"], rows),
        )

        assert response.status_code == 201
        data = response.json()
        assert data["created"] == 3
        assert data["skipped"] == 0
        assert data["total_rows"] == 3
        assert len(data["story_ids"]) == 3

        items = await _list_project_stories(authed_client, seeded.project_id)
        assert len(items) == 3
        by_feature = {item["feature"]: item for item in items}
        for actor, feature, benefit in rows:
            item = by_feature[feature]
            assert item["actor"] == actor
            assert item["benefit"] == benefit
            assert item["raw_text"] == canonical_text(actor, feature, benefit)


class TestImportFullMode:
    """POST import with a ``story`` header — text is parsed into parts."""

    async def test_import_parses_story_column_into_parts(self, authed_client, seed_workspace):
        """Two parseable rows create two stories with parsed parts and raw_text."""
        seeded = await seed_workspace(stories=0)
        rows = [
            canonical_text("user", "log in", "access my account"),
            canonical_text("admin", "view profile", "see my details"),
        ]
        response = await _import_file(
            authed_client,
            seeded.workspace_id,
            seeded.project_id,
            csv_bytes(["story"], [[row] for row in rows]),
        )

        assert response.status_code == 201
        assert response.json()["created"] == 2

        items = await _list_project_stories(authed_client, seeded.project_id)
        assert len(items) == 2
        by_feature = {item["feature"]: item for item in items}

        detail = await authed_client.get(f"/api/v1/stories/{by_feature['log in']['id']}")
        assert detail.status_code == 200
        story = detail.json()
        assert story["actor"] == "user"
        assert story["feature"] == "log in"
        assert story["benefit"] == "access my account"
        assert story["raw_text"] == rows[0]


class TestImportValidation:
    """Blocking row errors reject the whole file with nothing written."""

    async def test_blocking_error_writes_nothing(self, authed_client, seed_workspace):
        """An empty feature makes the file 422 and leaves zero stories behind."""
        seeded = await seed_workspace(stories=0)
        rows = [
            ["user", "log in", "access my account"],
            ["admin", "", "see my details"],
        ]
        response = await _import_file(
            authed_client,
            seeded.workspace_id,
            seeded.project_id,
            csv_bytes(["actor", "feature", "benefit"], rows),
        )

        assert response.status_code == 422
        data = _error_envelope(response)
        assert data["error_code"] == "IMPORT_VALIDATION_FAILED"
        assert data["created"] == 0
        assert data["total_rows"] == 2
        assert data["errors"][0]["line"] == 3
        assert data["errors"][0]["reason"] == "empty_field"

        items = await _list_project_stories(authed_client, seeded.project_id)
        assert items == []

    async def test_too_long_row_reports_field_and_lengths(self, authed_client, seed_workspace):
        """A 301-character benefit reports field, length and max."""
        seeded = await seed_workspace(stories=0)
        rows = [
            ["user", "log in", "access my account"],
            ["admin", "view profile", "b" * 301],
        ]
        response = await _import_file(
            authed_client,
            seeded.workspace_id,
            seeded.project_id,
            csv_bytes(["actor", "feature", "benefit"], rows),
        )

        assert response.status_code == 422
        error = _error_envelope(response)["errors"][0]
        assert error["line"] == 3
        assert error["reason"] == "too_long"
        assert error["field"] == "benefit"
        assert error["length"] == 301
        assert error["max"] == 300


class TestImportStructuralDefects:
    """Rows whose column structure disagrees with the header are refused, not mapped."""

    async def test_a_full_story_pasted_into_parts_mode_is_refused_not_written_as_a_story(
        self, authed_client, seed_workspace
    ):
        """A split-story corruption used to be written as a plausible garbage story.

        Under ``actor,feature,benefit`` a pasted canonical story splits on its own
        commas into exactly three fields, so the field-count guard cannot see it and the
        row used to be mapped positionally into a story that looked fine and was wrong.
        Written as raw bytes on purpose: ``csv_bytes`` would quote the field and turn
        this defect into a different one.
        """
        seeded = await seed_workspace(stories=0)
        payload = b"actor,feature,benefit\nAs a user, I want A, so that B\n"

        response = await _import_file(
            authed_client, seeded.workspace_id, seeded.project_id, payload
        )

        assert response.status_code == 422
        data = _error_envelope(response)
        assert data["error_code"] == "IMPORT_VALIDATION_FAILED"
        assert data["errors"][0]["reason"] == "parts_look_like_a_full_story"

        items = await _list_project_stories(authed_client, seeded.project_id)
        assert items == []

    async def test_a_ragged_row_reports_observed_and_expected_counts(
        self, authed_client, seed_workspace
    ):
        """A four-field row under a three-column header reports both counts."""
        seeded = await seed_workspace(stories=0)
        payload = b"actor,feature,benefit\nAs a user, I want A, B, so that C\n"

        response = await _import_file(
            authed_client, seeded.workspace_id, seeded.project_id, payload
        )

        assert response.status_code == 422
        error = _error_envelope(response)["errors"][0]
        assert error["reason"] == "field_count_mismatch"
        assert error["observed"] == 4
        assert error["expected"] == 3


class TestImportDuplicates:
    """Duplicates are skipped and reported, but never block the import."""

    async def test_existing_story_is_duplicate_not_error(self, authed_client, seed_workspace):
        """A row matching a seeded story is skipped with a duplicate entry."""
        seeded = await seed_workspace(stories=1)
        rows = [
            ["user", "use seeded feature 0", "the seeded chain is addressable"],
            ["user", "a brand new feature", "a brand new benefit"],
        ]
        response = await _import_file(
            authed_client,
            seeded.workspace_id,
            seeded.project_id,
            csv_bytes(["actor", "feature", "benefit"], rows),
        )

        assert response.status_code == 201
        data = response.json()
        assert data["created"] == 1
        assert data["skipped"] == 1
        # A success body carries no ``errors`` key at all; only the blocked path does.
        assert "errors" not in data
        duplicate = data["duplicates"][0]
        assert duplicate["reason"] == "duplicate"
        assert duplicate["existing_story_id"] == str(seeded.story_ids[0])

    async def test_in_file_duplicate_skipped_and_points_at_first_line(
        self, authed_client, seed_workspace
    ):
        """A repeated row inside the upload references the first occurrence."""
        seeded = await seed_workspace(stories=0)
        row = ["user", "log in", "access my account"]
        response = await _import_file(
            authed_client,
            seeded.workspace_id,
            seeded.project_id,
            csv_bytes(["actor", "feature", "benefit"], [row, row]),
        )

        assert response.status_code == 201
        data = response.json()
        assert data["created"] == 1
        assert data["skipped"] == 1
        duplicate = data["duplicates"][0]
        assert duplicate["reason"] == "duplicate_in_file"
        assert duplicate["first_line"] == 2
        assert duplicate["line"] == 3
        assert "existing_story_id" not in duplicate

    async def test_reuploading_the_same_file_is_idempotent(self, authed_client, seed_workspace):
        """Uploading the same file twice creates the rows only once."""
        seeded = await seed_workspace(stories=0)
        rows = [
            ["user", "log in", "access my account"],
            ["admin", "view profile", "see my details"],
            ["user", "reset password", "regain access"],
        ]
        payload = csv_bytes(["actor", "feature", "benefit"], rows)

        first = await _import_file(authed_client, seeded.workspace_id, seeded.project_id, payload)
        assert first.status_code == 201
        assert first.json()["created"] == 3

        second = await _import_file(authed_client, seeded.workspace_id, seeded.project_id, payload)
        assert second.status_code == 201
        assert second.json()["created"] == 0
        assert second.json()["skipped"] == 3

        items = await _list_project_stories(authed_client, seeded.project_id)
        assert len(items) == 3


class TestImportRejectedFiles:
    """Files that cannot be read at all are rejected with a typed 422."""

    async def test_unknown_header_is_rejected(self, authed_client, seed_workspace):
        """A header matching neither mode is rejected as header_unrecognized."""
        seeded = await seed_workspace(stories=0)
        response = await _import_file(
            authed_client,
            seeded.workspace_id,
            seeded.project_id,
            csv_bytes(["foo", "bar"], [["a", "b"]]),
        )

        assert response.status_code == 422
        data = _error_envelope(response)
        assert data["error_code"] == "IMPORT_FILE_REJECTED"
        assert data["reason"] == "header_unrecognized"

    async def test_invalid_utf8_is_rejected(self, authed_client, seed_workspace):
        """Bytes that are not valid UTF-8 are rejected as invalid_encoding."""
        seeded = await seed_workspace(stories=0)
        response = await _import_file(
            authed_client, seeded.workspace_id, seeded.project_id, b"story\n\xff\xfe invalid bytes"
        )

        assert response.status_code == 422
        data = _error_envelope(response)
        assert data["error_code"] == "IMPORT_FILE_REJECTED"
        assert data["reason"] == "invalid_encoding"

    async def test_empty_file_is_rejected(self, authed_client, seed_workspace):
        """An empty upload is rejected as empty_file."""
        seeded = await seed_workspace(stories=0)
        response = await _import_file(authed_client, seeded.workspace_id, seeded.project_id, b"")

        assert response.status_code == 422
        data = _error_envelope(response)
        assert data["error_code"] == "IMPORT_FILE_REJECTED"
        assert data["reason"] == "empty_file"


class TestImportHostileInput:
    """Inputs that used to escape the parser as an unhandled 500.

    Both were real: the route returned ``500 Internal server error`` rather than any contract
    status, so a malformed upload looked like a server fault. They are pinned here, at the
    HTTP layer, because that is where the failure was observed — a parser-level assertion
    alone would not have caught it.
    """

    async def test_cr_only_line_endings_are_accepted(self, authed_client, seed_workspace):
        """A classic-Mac file parses instead of raising: the reader needs ``newline=""``."""
        seeded = await seed_workspace(stories=0)

        response = await _import_file(
            authed_client,
            seeded.workspace_id,
            seeded.project_id,
            b"actor,feature,benefit\ruser,log in,access\r",
        )

        assert response.status_code == 201
        assert response.json()["created"] == 1

    async def test_a_very_long_field_is_reported_not_a_server_error(
        self, authed_client, seed_workspace
    ):
        """A field past csv's own 131072 limit is read and reported as ``too_long``.

        The field-size limit is raised to the byte cap at import, so the row is read and the
        normal length rule answers with the exact numbers instead of the file failing to
        parse at all.
        """
        seeded = await seed_workspace(stories=0)
        payload = b"story\n" + b"x" * 200_000 + b"\n"

        response = await _import_file(
            authed_client, seeded.workspace_id, seeded.project_id, payload
        )

        assert response.status_code == 422
        error = _error_envelope(response)["errors"][0]
        assert error["reason"] == "too_long"
        assert error["field"] == "raw_text"
        assert error["length"] == 200_000
        assert error["max"] == 2000


class TestImportSizeLimit:
    """The 2 MiB byte cap is enforced before parsing."""

    async def test_oversized_payload_returns_413(self, authed_client, seed_workspace):
        """A payload over 2 MiB is rejected with the cap in the body."""
        seeded = await seed_workspace(stories=0)
        payload = b"actor,feature,benefit\n" + b"a" * (3 * 1024 * 1024)

        response = await _import_file(
            authed_client, seeded.workspace_id, seeded.project_id, payload
        )

        assert response.status_code == 413
        data = _error_envelope(response)
        assert data["error_code"] == "IMPORT_FILE_TOO_LARGE"
        assert data["size"] == len(payload)
        assert data["max"] == 2097152

    async def test_an_oversized_upload_is_refused_without_being_read(
        self, authed_client, seed_workspace, monkeypatch
    ):
        """The cap is decided from ``UploadFile.size``, so the bytes are never pulled in.

        This pins the honest half of the claim. Starlette has already parsed the request body
        by the time the handler runs, so what is testable — and what matters for this process —
        is that this code refuses the upload without taking a second full copy of it. Making
        ``read`` explode is what turns that into an observation.
        """
        seeded = await seed_workspace(stories=0)
        payload = b"actor,feature,benefit\n" + b"a" * (3 * 1024 * 1024)

        async def _explode(self):
            raise AssertionError("UploadFile.read must not be called for an oversized upload")

        monkeypatch.setattr(StarletteUploadFile, "read", _explode)
        response = await _import_file(
            authed_client, seeded.workspace_id, seeded.project_id, payload
        )

        assert response.status_code == 413
        assert _error_envelope(response)["size"] == len(payload)


class TestImportAuthorization:
    """Membership, existence and containment are checked before any row is read."""

    async def test_non_member_gets_403(self, authed_client, seed_workspace):
        """A workspace the caller does not belong to returns 403 on its own path."""
        seeded = await seed_workspace(member=False)
        payload = csv_bytes(["actor", "feature", "benefit"], [["user", "f", "b"]])

        response = await _import_file(
            authed_client, seeded.workspace_id, seeded.project_id, payload
        )

        assert response.status_code == 403
        assert isinstance(response.json()["detail"], str)

    async def test_an_unknown_workspace_gets_404(self, authed_client):
        """An unknown workspace id returns 404 while resolving membership."""
        payload = csv_bytes(["actor", "feature", "benefit"], [["user", "f", "b"]])

        response = await _import_file(authed_client, uuid4(), uuid4(), payload)

        assert response.status_code == 404
        assert isinstance(response.json()["detail"], str)

    async def test_an_unknown_project_in_a_known_workspace_gets_404(
        self, authed_client, seed_workspace
    ):
        """A project that does not exist returns 404 from the containment check.

        Deliberately separate from the unknown-workspace case above: that one answers 404
        before the project is ever looked at, so on its own it cannot show that this branch
        works at all. Reaching it needs a workspace the caller belongs to plus a project id
        that is not in it.
        """
        seeded = await seed_workspace(stories=0)
        payload = csv_bytes(["actor", "feature", "benefit"], [["user", "f", "b"]])

        response = await _import_file(authed_client, seeded.workspace_id, uuid4(), payload)

        assert response.status_code == 404
        assert isinstance(response.json()["detail"], str)

    async def test_unauthenticated_gets_401(self, async_client, seed_workspace):
        """The import without a token returns 401."""
        seeded = await seed_workspace(stories=0)
        payload = csv_bytes(["actor", "feature", "benefit"], [["user", "f", "b"]])

        response = await _import_file(async_client, seeded.workspace_id, seeded.project_id, payload)

        assert response.status_code == 401


class TestImportContainment:
    """The path workspace does not authorize projects of another workspace."""

    async def test_a_member_of_workspace_a_cannot_import_into_workspace_bs_project(
        self, authed_client, seed_workspace
    ):
        """Naming workspace A in the URL cannot unlock workspace B's project."""
        seeded = await seed_workspace(stories=0)
        other = await seed_workspace(stories=0)
        payload = csv_bytes(["actor", "feature", "benefit"], [["user", "f", "b"]])

        response = await _import_file(authed_client, seeded.workspace_id, other.project_id, payload)

        assert response.status_code == 403

        items = await _list_project_stories(authed_client, other.project_id)
        assert items == []
