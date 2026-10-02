"""Unit truth table for the owner-or-admin gate (task 4.1 of extraction-versioning).

Pins ``_is_owner_or_admin`` over its full input space. There is no ``OWNER``
role in this codebase: ``WorkspaceRole`` has exactly ``ADMIN`` and ``MEMBER``
(``domain/entities/workspace_member.py``), and ownership is the data fact
``workspace.owner_id == user.id`` — an owner may hold either role in the
member table. The truth table is therefore over two variables (is the caller
the workspace owner, and which role does their membership row carry) and has
exactly four combinations, all of which this file enumerates:

    owner + ADMIN  → True
    owner + MEMBER → True   (ownership is not a role; a plain-role owner passes)
    non-owner + ADMIN → True
    non-owner + MEMBER → False

No other combination exists, because the role enum has two members and the
owner question is boolean; the parametrization below is the exhaustive cross
product, so "no other combination passes" is enforced structurally, not
rhetorically. The gate must not become a louder signal than the access walk:
non-members are refused earlier by the shared walk, never by this predicate.

Pure unit test: no API client, no database, no Docker.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from storico.api.dependencies import _is_owner_or_admin
from storico.domain.entities.user import User
from storico.domain.entities.workspace import Workspace
from storico.domain.entities.workspace_member import WorkspaceRole


def _make_user() -> User:
    return User(email="caller@example.com", name="Caller")


def _make_workspace(owner_id: UUID) -> Workspace:
    return Workspace(name="WS", slug="ws", owner_id=owner_id)


OWNER = _make_user()
NON_OWNER_ADMIN = _make_user()
NON_OWNER_MEMBER = _make_user()
WORKSPACE = _make_workspace(OWNER.id)


@pytest.mark.parametrize(
    ("caller", "role", "expected"),
    [
        # The workspace owner passes with either membership role: ownership
        # is workspace.owner_id == user.id, not a WorkspaceRole.
        (OWNER, WorkspaceRole.ADMIN, True),
        (OWNER, WorkspaceRole.MEMBER, True),
        # A member with role ADMIN passes without owning the workspace.
        (NON_OWNER_ADMIN, WorkspaceRole.ADMIN, True),
        # A member with role MEMBER who is not the owner is the only refusal.
        (NON_OWNER_MEMBER, WorkspaceRole.MEMBER, False),
    ],
    ids=[
        "owner-with-role-admin-passes",
        "owner-with-role-member-passes-ownership-is-not-a-role",
        "non-owner-with-role-admin-passes",
        "non-owner-with-role-member-fails",
    ],
)
def test_is_owner_or_admin_truth_table(caller: User, role: WorkspaceRole, expected: bool) -> None:
    assert _is_owner_or_admin(WORKSPACE, role, caller) is expected


def test_predicate_is_exhaustive_over_the_role_enum() -> None:
    """The truth table above covers every WorkspaceRole and the owner question.

    Guards against a future third role silently joining the gate: the moment
    ``WorkspaceRole`` grows a member, this assertion fails and the truth table
    must be revisited instead of the new role falling through.
    """
    assert {role for role in WorkspaceRole} == {WorkspaceRole.ADMIN, WorkspaceRole.MEMBER}


def test_predicate_refuses_a_user_who_is_neither_owner_nor_admin() -> None:
    """A caller distinct from the owner with role MEMBER fails — pinned alone."""
    stranger = _make_user()
    assert stranger.id != WORKSPACE.owner_id
    assert _is_owner_or_admin(WORKSPACE, WorkspaceRole.MEMBER, stranger) is False
