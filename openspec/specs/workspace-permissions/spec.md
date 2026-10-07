# workspace-permissions Specification

## Requirements

### Requirement: The Gate Is the Owner-or-Admin Rule, Expressed as New Code

Version-mutating operations MUST be gated by the rule "workspace owner or member with role
`ADMIN`" — role `ADMIN` or `workspace.owner_id == current_user.id` — implemented as a new
dependency predicate, because no existing dependency expresses it: membership-only resolution,
role-only `ADMIN` and owner-**and**-`ADMIN` are each different rules. The gate MUST preserve each
route's current refusal shape — a resource the caller cannot address stays `EntityNotFound` (404),
and a caller who is not a member of the owning workspace stays 403 `NOT_A_WORKSPACE_MEMBER`, the
shape the existing membership walk already produces (`api/dependencies.py:296-312`) — so the gate
adds no new information about a workspace the caller is not in.

#### Scenario: The rule accepts the owner and any ADMIN, and nobody else

- **GIVEN** a workspace with owner U1, a member U2 with role `ADMIN`, and a member U3 with role
  `MEMBER`
- **WHEN** the gate predicate is evaluated for U1, U2 and U3
- **THEN** U1 and U2 pass and U3 does not
- **AND** no other workspace user passes

#### Scenario: A non-member keeps today's refusal

- **GIVEN** a user who is not a member of the workspace
- **WHEN** the user calls a gated route for a resource of that workspace
- **THEN** the backend answers 403 `NOT_A_WORKSPACE_MEMBER`, the refusal the membership walk gives
  today
- **AND** the response does not reveal that the gated operation exists

### Requirement: The Four Version-Mutating Operations Require the Gate

Extracting a new version, marking a task invalid, revoking a mark and deleting a story MUST each
require the workspace owner or an `ADMIN`. A `MEMBER` calling any of the four MUST receive HTTP
403 with `error_code` `WORKSPACE_OWNER_OR_ADMIN_REQUIRED`, which the client surfaces as an
explicit localized refusal rather than a raw 403. The workspace owner and an `ADMIN` MUST succeed
on all four.

#### Scenario: A MEMBER is refused on every gated operation

- **GIVEN** a workspace `MEMBER`
- **WHEN** the member attempts to extract a version, mark a task invalid, revoke a mark, or delete
  a story with versions
- **THEN** each attempt answers HTTP 403 with `error_code`
  `WORKSPACE_OWNER_OR_ADMIN_REQUIRED`
- **AND** each refusal is rendered with the code's localized copy, not a generic 403 message
- **AND** none of the four attempts changed any data

#### Scenario: The owner and an ADMIN succeed on all four

- **GIVEN** the workspace owner, and separately a member with role `ADMIN`
- **WHEN** each attempts to extract, mark, unmark and delete a story
- **THEN** all attempts succeed for both users

### Requirement: The Member-Accessible Surface Is Stated and Protected

Reading the board, moving a card (changing a task's `status`), editing a task's `labels`, editing
a story's own four fields, reading tasks, reading versions and the repetition read MUST stay
available to every workspace member. The gate MUST NOT be applied to `PUT /api/v1/tasks/{task_id}`
or to any read. The net effect on a `MEMBER` is: they see the board, they move cards, they edit
labels — and nothing else of the new versioning surface.

#### Scenario: A MEMBER keeps the full read-and-edit surface

- **GIVEN** a workspace `MEMBER` and a story with a completed current version
- **WHEN** the member reads the board's tasks, drags a card to a new `status`, edits a task's
  `labels`, edits a story's four fields, reads the story's versions and requests the repetition
  read
- **THEN** every call succeeds with HTTP 200

#### Scenario: A MEMBER's status edit on a task is never gated

- **GIVEN** a workspace `MEMBER` and a task on the current version
- **WHEN** the member calls `PUT /api/v1/tasks/{task_id}` with body `{"status": "in_progress"}`
- **THEN** the backend answers HTTP 200 and the status is persisted
- **AND** the owner-or-`ADMIN` gate was not consulted for this call
