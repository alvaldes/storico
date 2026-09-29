# Design: Extraction Versioning — HTTP Contract, Permission Gate and UI

> **Change**: `extraction-versioning-api`
> **Status**: `design`
> **Based on**: `proposal.md`, the seven `specs/` deltas, `explore.md`, and slice (a)'s artifacts
> (`../extraction-versioning-schema/explore.md`, `../extraction-versioning-schema/design.md`)
> **Created**: 2026-09-28

Slice (b) of three. It gives the storage slice (a) built its HTTP contract: the current-version
filter on every read, the field matrix D5/D21 on `PUT /tasks/{task_id}`, the marks endpoints D6/D7,
the owner-or-`ADMIN` gate D13, D15's story deletion with its record and its vector cleanup, both
`410 Gone` retirements D17, D16's repetition read, and the version selector the UI renders from.

Measured starting point: `main` `ecea3e2`. Slice (a) is **artifacts only** — no migration `0028`, no
`TaskInvalidationModel`, no `find_current_version` in the port, no `VersionAllocationConflictError`
in `domain/entities/exceptions.py`. `alembic/versions/` tops out at `0027` with no revision
declaring `down_revision = "0027"`, so this slice claims `0029` behind (a)'s `0028`. Every (a)
mechanism this slice consumes is therefore cited to
`openspec/changes/extraction-versioning-schema/design.md`, not to code, and the two slices ship in
one release (proposal, *Sequencing*).

The spine of the design is three sentences. **"Frozen" is derived by comparing the task's
`extraction_id` with the story's current version, never stored.** **The current-version filter is a
SQL predicate that the page and its fallback count share, so `total` cannot disagree with the rows.**
**Story deletion runs vector cleanup first and the relational delete plus its record second, in one
transaction, because the failure D15 warns about only happens if the relational delete lands
first.**

## Technical Approach

Ordered work, from the HTTP contract outward. Work units (WU1–WU4) are the review slices the tasks
phase should keep together — the proposal's own four candidate units (proposal step 16), each
ending on a green suite. WU4 follows WU3 because the marks endpoints consume the gate WU3 adds.

**WU1 — The write contract and the two retirements.** `UpdateTaskRequest` shrinks to
`status`/`labels`/`dependencies`; the field matrix and the frozen-version check land in
`PUT /api/v1/tasks/{task_id}`; `DELETE /api/v1/tasks/{task_id}` and `POST /api/v1/tasks/` become
`410` handlers; `CreateTaskRequest` is deleted; `lib/tasks-api.ts` and `TaskEditor` stop sending the
removed fields **in the same unit**, or every editor save 422s (proposal *Risks*, first row).

**WU2 — The reads.** The current-version predicate in `SQLAlchemyTaskRepository` for all three page
scopes plus `list_current_by_workspace` for the export; the `extraction_id` read parameter and its
refusal; `list_versions` on the extraction port and `GET /api/v1/stories/{story_id}/versions`; the
three response scalars on `ExtractionResponse`/`ExtractResponse`.

**WU3 — The gate and the delete.** `_is_owner_or_admin` plus its three wrappers in
`api/dependencies.py`; extract gated; `0029_story_deletions.py`; `domain/entities/story_deletion.py`
and `delete_with_record` on the story port; `VectorStorePort.delete_by_story` + its adapter;
`StoryDeletionService`; the `VersionAllocationConflictError` handler.

**WU4 — The marks and the UI.** The mark entity, port and repository; the three mark endpoints and
the D16 read; the title normalizer; `VersionSelector.tsx`; the recut `TaskEditor`; the two
confirmation dialogs; the failed-version "no output" state; the version count in the delete dialog;
`lib/versioning-api.ts`, `lib/workspace-role.ts`, the six-plus-one new codes and all copy in both
locales, including the `landing.faq.a4` correction.

## Architecture Decisions

### Decision: the gate is one predicate plus three wrappers, over a shared walk that returns the role

`api/dependencies.py` gains the rule and the wrappers:

```python
def _is_owner_or_admin(workspace: Workspace, role: WorkspaceRole, user: User) -> bool:
    return role == WorkspaceRole.ADMIN or workspace.owner_id == user.id

async def require_owner_or_admin(
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
    current_user: User = Depends(get_current_user),
) -> tuple[Workspace, WorkspaceRole]: ...          # extract: workspace_id is in the path

async def require_story_owner_or_admin(
    story_id: UUID, current_user: User, *, story_repo, project_repo, member_repo, ws_repo,
    reported_as: tuple[str, UUID] | None = None,
) -> UserStory: ...                                 # D15

async def require_task_owner_or_admin(
    task_id: UUID, current_user: User, *, task_repo, story_repo, project_repo, member_repo, ws_repo,
) -> Task: ...                                      # the three marks endpoints
```

None of the three existing dependencies expresses the rule: `get_workspace_for_user`
(`api/dependencies.py:209`) is membership-only and returns the role, `require_admin` (`:243`)
refuses anyone who is not `ADMIN`, and `require_owner` (`:261`) chains `require_admin` and then
compares `owner_id`, so it is `ADMIN` **and** owner — narrower than D13's rule, not a synonym. D13's
rule is a disjunction.

The gate needs the role (from the membership row) and `workspace.owner_id` (a second row the read
paths never fetch). To keep the reads paying no extra statement, `require_story_workspace_access`
(`:280`) is refactored into a shared walk whose result carries everything the gate needs:

```python
@dataclass(frozen=True, slots=True)
class StoryAccess:
    story: UserStory
    workspace_id: UUID
    role: WorkspaceRole

async def resolve_story_access(
    story_id, current_user, *, story_repo, project_repo, member_repo, reported_as
) -> StoryAccess: ...

async def require_story_workspace_access(...) -> UserStory:      # returns .story; refusals unchanged
```

The walk keeps its three statements (story, project, membership) and its refusals byte-for-byte:
`EntityNotFound` reported as the caller's head entity, then `ApiError(403, NOT_A_WORKSPACE_MEMBER)`
for a missing membership. `resolve_task_access` is the same shape with a leading
`task_repo.find_by_id`, reported as `("Task", task_id)` — the walk `_validate_task_workspace_access`
(`api/routes/tasks.py:60`) already performs, and `_validate_task_workspace_access` becomes a thin
caller of it. Only the gated wrappers fetch the workspace row, and only to read `owner_id`.

Ordering inside each wrapper is the requirement behind "a non-member keeps today's refusal and
learns nothing new": the membership refusal fires **first**, in the shared walk, and the
`403 WORKSPACE_OWNER_OR_ADMIN_REQUIRED` is raised only for a caller that is a member and is neither
the owner nor an `ADMIN`.

**Why**: a new predicate, not a combination of two existing ones, is what the spec asks for and what
the rules actually are. Putting the rule in one function makes "owner or `ADMIN`" appear once in the
codebase; the three wrappers exist only because the three routes reach the workspace by three
different walks.

**Tradeoff**: `require_story_workspace_access` gains a dataclass and a rename of its body (its
signature and refusals do not move), and `api/dependencies.py` grows a second workspace-fetching
shape. The rejected alternatives cost more: a boolean `require_owner_or_admin` chained on
`require_admin` would make `MEMBER` and "neither owner nor admin" the same refusal and lose the
owner arm; giving the gate its own three walks duplicates the reporter logic that
`reported_as` exists to centralise, and a duplicated walk is exactly how one route starts leaking
whether a story exists.

### Decision: the field matrix keys on `model_fields_set`, and rejection is a field removal

`UpdateTaskRequest` (`api/schemas/task.py:25-35`) becomes:

```python
class UpdateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: TaskStatus | None = None
    labels: list[str] | None = None
    dependencies: list[str] | None = None
```

`title`, `description` and `priority` are **deleted**, not ignored. `extra="forbid"` is already in
force, so a client that still sends any of the three is refused by Pydantic during dependency
resolution, before the handler body runs, and the app's `RequestValidationError` handler maps it to
422 `REQUEST_VALIDATION_FAILED` (`api/error_codes.py:144`) — the observable C10 contract change,
stated by the spec as "the observable failure of the `extra="forbid"` schema, not a silent ignore".

The frozen check is a separate, later step:

```python
current = await extraction_repo.find_current_version(existing.user_story_id)
frozen = current is None or existing.extraction_id != current.id
if "dependencies" in body.model_fields_set and frozen:
    raise ApiError(409, TASK_VERSION_FROZEN, detail={"current_version": current.version_number if current else None, ...})
if body.status is not None:
    ... existing state-machine check, unchanged ...
```

Three properties this placement buys, each of which the spec pins:

- **Presence, not value.** `{"dependencies": []}` carries the key, so it is refused on a frozen
  version; `{"status": "done"}` does not carry it, so it passes. `model_fields_set` is populated by
  explicit presence even when the value is `None`, so `{"dependencies": null}` is *also* refused on a
  frozen version — while on the current version it stays what it always was, a no-op (`if body.dependencies
  is not None`). The two rules are deliberately different keys: presence decides the refusal, non-`None`
  decides the write.
- **Refusal before the state machine.** A body carrying both an illegal `status` transition and a
  `dependencies` write on a frozen version is answered 409 for the frozen field, not 400 for the
  transition. Neither path writes, so nothing partial can land; the order only decides which reason
  the user sees, and the version-level reason is the one that will not be there tomorrow.
- **`current is None` means frozen.** A story with no `completed` version has no current version, so
  every one of its tasks is off-current by definition. That arm is nearly unreachable (tasks are only
  written by a run that completed), but defining it as "frozen" is the conservative reading; the
  detail names the story and says there is no current version rather than inventing number `0`.

**Why**: the check keys on what the client sent because D5's whole point is that a `MEMBER` keeping
the board alive must not be blocked, and the board sends exactly `{"status": …}`. Keying on `None`
would make `{"dependencies": []}` on a frozen version pass and silently clear a frozen task's
dependencies — a data loss reachable from a normal-looking payload.

**Tradeoff**: `frozen` costs one extra statement (`find_current_version`) before a dependency write,
against a pooler where a statement is ~2s. The rejected alternative — resolving the current version
inside the same statement that loads the task — buys nothing back, because the task is loaded by
`find_by_id` under the repository's existing contract and a join would change every caller. The
alternative for the rejection mechanism (validate in the handler and raise 422 by hand) would have
left `extra="forbid"` in place while the removed fields silently passed validation, which is the
C10 lie the proposal rules out.

### Decision: the two retirements are precise `410` handlers, and only one of them has a resource to walk

Both handlers copy the shape already in the tree twice — `api/routes/extraction.py:68-91`
(`deprecated_extract`) and `api/routes/projects.py:35-59` (`deprecated_projects`): a decorator of
`@router.api_route(..., methods=[...], status_code=410, include_in_schema=False)` whose body raises
`ApiError(status_code=410, error_code=…, detail=…)`, which the envelope in `api/errors.py` renders as
`{detail, error_code}`.

```python
@router.api_route("/{task_id}", methods=["DELETE"], status_code=410, include_in_schema=False)
async def deprecated_delete_task(task_id: UUID, current_user=..., repo=..., story_repo=..., ...) -> NoReturn:
    await _validate_task_workspace_access(task_id, current_user, repo, story_repo, project_repo, member_repo)
    raise ApiError(410, TASK_DELETE_ENDPOINT_REMOVED, detail="…D12: no product path deletes a single task…")

@router.api_route("/", methods=["POST"], status_code=410, include_in_schema=False)
async def deprecated_create_task() -> NoReturn:
    raise ApiError(410, TASK_CREATION_ENDPOINT_REMOVED, detail="…D3: a task is only born from an extraction run…")
```

The delete handler keeps the same walk it has today and drops only the `repo.delete(task_id)` line,
so a missing task still answers the same 404 and a non-member the same `NOT_A_WORKSPACE_MEMBER`, and
a member learns the endpoint is retired. The create handler has no resource to authorize: the story
id it used to authorize against lived in the request **body**, and `CreateTaskRequest` is deleted with
the route, so the handler reads no body at all and answers 410 before any parsing. That is the one
place this design does not carry the requirement's "both handlers keep membership-only access"
sentence, and it is recorded rather than papered over: the only information the 410 discloses is
that the endpoint is retired, which `include_in_schema=False` and the error code already state.

The paths are `"/{task_id}"` and `"/"`, not the greedy `"/{path:path}"` the two precedents use. The
precedents retire *every* path under a dead prefix; here exactly two published methods die, and a
catch-all in this router would sit in the same router as `DELETE /{task_id}/invalidations/current`
(WU4) and swallow it unless registered last — an ordering coupling inside one file that a reviewer
cannot see from the decorator. Greediness also breaks `DELETE /api/v1/tasks/`, which answers 405
today and would start answering 410.

**Why**: `410 Gone` with a reason keeps the release at MINOR (proposal step 7) while making the
product honest about two promises it already publishes — `POST /tasks/` has no product path, and
`landing.faq.a4` (`frontend/src/i18n/en.json:132`, `es.json:132`) already tells users Storico does
not delete a single task.

**Tradeoff**: the deleted routes leave the OpenAPI schema, so a client generated from it loses the
methods instead of seeing them marked deprecated; the `include_in_schema=False` flag is what keeps
the shape identical to the two precedents, and `frontend/src/i18n/__tests__/api-docs-copy.test.ts`
derives declared paths from decorators (including `api_route`), so the removed methods are still
visible to that guard and nothing it asserts changes. The rejected alternative — deleting the
methods outright — is a `BREAKING CHANGE` and hands 0.9.0 a MAJOR bump, and it would answer 405,
which says "you used the wrong method" about a rule rather than about HTTP.

### Decision: the current-version filter is a SQL predicate shared by the page and its fallback count

`SQLAlchemyTaskRepository.list_page` already builds a `scope` clause and applies the same one to
`stmt` and to `count_stmt`, and `fetch_page` runs `count_stmt` only when a page falls past the end
(`infrastructure/database/pagination.py`). The filter joins `scope`, so both halves carry it and the
fallback count cannot disagree with the rows:

- **Story scope, no `extraction_id`**: `TaskModel.extraction_id == select(ExtractionModel.id).where(
  ExtractionModel.user_story_id == user_story_id, ExtractionModel.status == "completed"
  ).order_by(ExtractionModel.version_number.desc()).limit(1).scalar_subquery()`.
- **Story scope with `extraction_id`**: `TaskModel.extraction_id == extraction_id` — no currency
  predicate, because reading a named version is the point.
- **Workspace scope and the unfiltered `workspace_ids` scope**: the "no higher-numbered completed
  version of this story" form, which needs no `MAX` and is served by `uq_extractions_story_version`:

  ```python
  e = aliased(ExtractionModel)
  TaskModel.extraction_id == e.id
  and e.status == "completed"
  and ~exists(select(1).where(ExtractionModel.user_story_id == e.user_story_id,
                              ExtractionModel.status == "completed",
                              ExtractionModel.version_number > e.version_number))
  ```

One scope is easy to forget: `GET /api/v1/tasks/` with no
query parameter is a read of tasks too, and `tests/test_api/test_unfiltered_list_queries.py` exists
and will notice. The same predicate is exposed as `list_current_by_workspace(workspace_id)` for the
export, which reads unpaginated and so does not go through `list_page` at all.

**Why**: the filter belongs in SQL because `total` rides on the rows' own statement. Filtering in
Python after a paginated query drops rows while `total` keeps counting them — the silent truncation
the proposal's *Risks* row 6 names, made worse because the board and the export both cap their
window (the board reads `size=100`). The correlated subquery rather than an extra
`find_current_version` call keeps the story-scoped read at one statement.

**Tradeoff**: the predicate is duplicated between the story form and the workspace form (two
expression shapes, one meaning), and both are only as correct as their tests. The rejected
alternatives: `find_current_version` followed by `tasks.extraction_id == current.id` costs a second
statement per read and admits a race in which the current version moves between the two statements
(harmless for correctness of the page, which still carries its own `total`, but it means the read
does not answer a single question); a materialised `is_current` column is forbidden by D4 (a slice
(a) requirement pins that no flag, trigger or matview exists).

### Decision: the selector is one unpaginated story-scoped read, and `is_current`/`has_output` are computed from its own payload

`GET /api/v1/stories/{story_id}/versions` is served by a new port method rather than by
`list_page`:

```python
# domain/ports/extraction_repository.py
async def list_versions(self, user_story_id: UUID) -> list[Extraction]:
    """Every version of one story, ordered ``version_number DESC``. Deliberately unbounded:
    a story's version count is bounded by hand-run extractions, and the paginator's 20/100
    window would truncate it silently — which is the failure this endpoint exists to avoid."""
```

It returns `list[StoryVersionResponse]` — a bare array, like the marks read the spec describes as
"an empty list" — with `id`, `version_number`, `status`, `model_used`, `provider`, `temperature`,
`created_at`, `completed_at`, `error_info`, `is_current`, `has_output`. The two computed fields come
from the list itself, in the route:

- `is_current = (version.id == next((v for v in versions if v.status is ExtractionStatus.COMPLETED), None)?.id)`
  — the first `completed` entry in a list already ordered `version_number DESC` **is** the highest
  completed version, which is slice (a)'s definition of current, so a `pending` top version cannot
  displace it and the reference used to decorate the payload cannot disagree with the payload.
- `has_output = (version.status is ExtractionStatus.COMPLETED)` — "this version's output is
  readable". A `failed` or `pending` version has none; a completed run that legitimately produced
  zero tasks still has output (an empty task list), and the UI renders an empty board for it, which
  is honest.

Authorization is the **unchanged** `require_story_workspace_access`: a missing story or project is
`EntityNotFound` (404) and a non-member is 403 `NOT_A_WORKSPACE_MEMBER`, byte-for-byte what
`GET /stories/{id}` answers today (`api/dependencies.py:296-312`). The requirement that a story the
caller cannot access is a *visible error*, never a silent empty 200, is satisfied by that walk
without adding anything to it.

Rejected alternative: a `hide_membership: bool` keyword on `resolve_story_access` that folded the
non-member refusal into the same `EntityNotFound("UserStory", story_id)` a missing story produces,
so the selector alone would answer 404 to a non-member. It invented a new concept in
`api/dependencies.py` to disclose nothing new: every other story read already distinguishes "not
found" from "not a member", so a fourth shape for one route is inconsistency dressed as a privacy
fix, and correcting it later means changing a published refusal.

**Why**: a second, unbounded read is the only shape that answers the requirement ("contains every
version of the story in one payload, no entry is silently truncated") without `LIMIT (SELECT
count(*))` nonsense. Computing `is_current` from the ordered list costs no statement and cannot
contradict the rows it decorates.

**Tradeoff**: "current" is now derived in two places — `find_current_version` (slice (a), used by the
frozen check and the marks endpoints) and this in-payload first-completed rule. They agree by
construction because both are "highest completed", and one repository test asserts that
`find_current_version(story_id)` equals the selector's first `completed` entry for a three-version
story, which is what keeps the two in step. The rejected alternative — calling `find_current_version`
and comparing ids — costs a statement per selector load for a value already in hand. The second
decision is the one this paragraph used to record as a deviation: the selector keeps the repository's
existing posture (403 for a non-member) instead of hiding membership, so it inherits the disclosure
that every story read already makes. The cost of *not* hiding it is honest and pre-existing; the
cost of hiding it only here would have been a refusal shape no other route shares.

### Decision: the mark gets an entity, a port and a repository; the blank-reason rule lives in a Pydantic validator

```python
# domain/entities/task_invalidation.py
@dataclass(frozen=True, slots=True)
class TaskInvalidation:
    task_id: UUID
    reason: str
    marked_by: UUID | None = None       # nullable: the column is ON DELETE SET NULL
    marked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: UUID = field(default_factory=uuid7)
    revoked_by: UUID | None = None
    revoked_at: datetime | None = None
```

```python
# domain/ports/task_invalidation_repository.py
async def create(self, mark: TaskInvalidation) -> TaskInvalidation
async def find_active_by_task(self, task_id: UUID) -> TaskInvalidation | None
async def list_by_task(self, task_id: UUID) -> list[TaskInvalidation]      # marked_at DESC, active first
async def revoke(self, mark_id: UUID, *, revoked_by: UUID, revoked_at: datetime) -> None
async def list_active_on_other_versions(
    self, *, user_story_id: UUID, exclude_extraction_id: UUID | None
) -> list[TaskInvalidationCandidate]                                        # carries version_number + title
```

`TaskInvalidationCandidate` is a frozen slotted dataclass of `(version_number, title, reason,
marked_at)`, an internal read model rather than an entity, because the D16 join's rows are not
`TaskInvalidation` rows (they belong to another task) and pretending otherwise would make the
repository return an entity with a wrong `task_id`. The join is
`task_invalidations JOIN tasks ON tasks.id = task_invalidations.task_id JOIN extractions ON
extractions.id = tasks.extraction_id`, filtered by `tasks.user_story_id = :story_id`,
`tasks.extraction_id IS DISTINCT FROM :exclude_extraction_id`, `task_invalidations.revoked_at IS
NULL`, and ordered `version_number DESC, marked_at DESC`.

The request schema carries the residual of slice (a)'s database `CHECK`:

```python
class CreateInvalidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("reason")
    @classmethod
    def _reason_not_blank(cls, value: str) -> str:
        if not value.strip():                       # Python whitespace: tabs and newlines too
            raise ValueError("reason must not be blank")
        return value

    reason: str = Field(..., max_length=500)        # the column's bound
```

A blank reason therefore never reaches the route: Pydantic refuses it during dependency resolution
and the app's handler answers 422 `REQUEST_VALIDATION_FAILED` — the code the proposal names for it
("The empty-reason rule needs **no** new code"), and exactly the residual slice (a) recorded, since
`length(trim(reason)) > 0` on the column covers spaces but not tabs and newlines while
`str.strip()` covers both.

The other three refusals are handler-body code, in this order: the gate (in the walker), the frozen
check (§ the field-matrix decision's mechanism, reused verbatim), then
`find_active_by_task` for the `409 TASK_ALREADY_MARKED` whose detail carries the active reason. The
revoke path is `UPDATE`, never `DELETE` (D12): `revoke(mark_id, revoked_by=…, revoked_at=…)` sets
exactly those two columns on the row `find_active_by_task` resolved, and `404` when that read finds
nothing. A note on sessions: `get_repository` injects the same request-scoped `AsyncSession` into
every repository (`api/dependencies.py:51`), but each repository method commits its own, so
"create then read back" is two commits — which is fine here because nothing about the mark needs one
transaction.

**Why**: (a) deliberately shipped storage with no door. The entity/port/repository trio is the
repo's ordinary hexagonal shape for a new aggregate, and the validator is the only place a rule
about *input text* can live — the database `CHECK` cannot see tabs, and the UI's client-side check is
declared a convenience by the spec.

**Tradeoff**: the reason rule now exists in three places (validator, database `CHECK`, editor) with
three different whitespace vocabularies, and only a test table keeps them honest — the spec's own
"the server's 422 refusal is the backstop" is what makes that acceptable. The rejected alternative —
validating in the route with a bare `if not reason.strip()` — cannot answer 422
`REQUEST_VALIDATION_FAILED` through the framework handler without hand-building the error body, and
it would run *after* the gate, so a blank reason from a `MEMBER` would answer 403 about a request
body that never had a chance.

### Decision: D16's match is computed in Python from a story-scoped candidate read

The normalizer is one new helper, `normalize_task_title(text) -> str` in
`domain/services/task_title_normalizer.py` (casefold + collapse runs of whitespace to one space +
strip), and the route is:

```
GET /api/v1/tasks/{task_id}/invalidations/repetition   members only (the same walk as GET marks)
  → task = await _validate_task_workspace_access(...)          # title resolved server-side
  → candidates = await invalidation_repo.list_active_on_other_versions(
        user_story_id=task.user_story_id, exclude_extraction_id=task.extraction_id)
  → matches = [c for c in candidates if normalize_task_title(c.title) == normalize_task_title(task.title)]
  → {"matches": [{"version_number": c.version_number, "reason": c.reason, "marked_at": c.marked_at}]}
```

The SQL narrows to the story and to the other versions; the equality test runs in Python because
`casefold` has no SQL equivalent (Postgres `lower` is not `casefold` for `ß`, `İ` and friends) and
because a whitespace-collapsing `regexp_replace` would not build against the SQLite unit schema.
Taking only the task id — never a title — from the client is what makes the normalizer live in one
place and keeps the endpoint from becoming a free-text probe of other people's marks.

**Why**: `casefold` is a Python operation, so a SQL-only match would silently answer a different
question than the spec's `casefold` plus whitespace collapse. The candidate set is small by
construction (the marks of one story's other versions), so the Python pass has nothing to optimise.

**Tradeoff**: the read fetches candidates it usually discards, and its cost scales with the story's
history rather than with the answer. The rejected alternatives: a `normalized_title` column written
on every task (storage and a second source of truth for a value the write path does not otherwise
need, and it would have to backfill); `LOWER()` in SQL (an approximation of `casefold` that the spec
would call a different rule — the same reason the `0044`-era version-cache ideas were dropped);
fuzzy or vector similarity (explicitly out of scope by D16).

### Decision: story deletion is snapshot → vector cleanup → delete-with-record, in one transaction

`DELETE /api/v1/stories/{story_id}` becomes:

```
1. gate:            require_story_owner_or_admin(...)            # 404 / NOT_A_WORKSPACE_MEMBER / 403 WORKSPACE_OWNER_OR_ADMIN_REQUIRED
2. snapshot:        versions = await extraction_repo.list_versions(story_id)
                    record = StoryDeletion(story_id=…, project_id=…, workspace_id=…,
                                           actor=…, feature=…, benefit=…,
                                           version_numbers=[v.version_number for v in versions],
                                           deleted_by=current_user.id, deleted_at=now)
3. vector cleanup:  if vector_store is not None:
                        await vector_store.delete_by_story(workspace_id=…, user_story_id=str(story_id))
4. relational:      await story_repo.delete_with_record(story_id, record)
```

Step 4 is one repository method because one transaction is the requirement and the existing
`SQLAlchemyUserStoryRepository.delete` commits on its own
(`infrastructure/database/repositories/user_story_repository.py:118-123`), so two calls are two
transactions and a crash between them loses the record of a delete that happened:

```python
async def delete_with_record(self, user_story_id: UUID, record: StoryDeletion) -> None:
    """Delete the story and write its deletion record in one transaction."""
    try:
        result = await self._session.execute(delete(UserStoryModel).where(UserStoryModel.id == user_story_id))
        if result.rowcount == 0:
            await self._session.rollback()
            raise EntityNotFound("UserStory", str(user_story_id))
        self._session.add(StoryDeletionModel(**self._to_record_kwargs(record)))
        await self._session.commit()
    except SQLAlchemyError as e:
        await self._session.rollback()
        raise RepositoryError("Database error deleting user story") from e
```

The story's versions and their tasks disappear through the database cascade migration `0014`
established (`tasks.user_story_id` and `extractions.user_story_id` are `ON DELETE CASCADE`), and
`task_invalidations.task_id` cascades from `tasks` (slice (a)), so the marks of those versions die
with them. Nothing in step 4 names them.

Migration `0029_story_deletions.py` stores the record as **values**:

```
story_deletions: id (pk), story_id UUID, project_id UUID, workspace_id UUID,
                 actor / feature / benefit TEXT, version_numbers JSON,
                 deleted_by UUID NULL FK -> users.id ON DELETE SET NULL,
                 deleted_at TIMESTAMPTZ NOT NULL
```

There is deliberately **no foreign key** to `stories`, `projects` or `extractions`: a record
referencing the story it records would be destroyed by the very delete it records (proposal step 6).
`deleted_by` follows the repo's convention for `projects.created_by` (`0014_add_cascade_deletes.py`,
`ON DELETE SET NULL`), so the record survives an account deletion with the actor reference nulled.
`version_numbers` is `sa.JSON` rather than a Postgres `ARRAY` so the model builds in the SQLite unit
schema (`Base.metadata.create_all` in `tests/conftest.py:149`) and the write path is unit-testable;
slice (a) chose portability over Postgres-only types for the same reason. The story's identity is the
`(actor, feature, benefit)` trio the app already treats as a story's identity — the dedupe rule in
`domain/services/story_import.py` / `find_by_parts` — so the record is readable by a human who can no
longer look the story up.

**Why**: the order is the failure D15 names. Orphan points that survive the story stay retrievable as
few-shots for *other* stories (D10), and that only becomes possible if the relational delete lands
first; running the cleanup first turns "the points are stale" into "the delete did not happen", which
the user can retry. `wait=True` is passed to the Qdrant delete so that "no points remain retrievable"
is true when the response returns rather than eventually.

**Tradeoff**: the delete is now two systems with no distributed transaction — the vector store can
succeed while the relational delete fails, leaving zero points and a live story, which is a
degraded-but-consistent state (the story's next run re-stores its points) and is not the dangerous
direction. The record adds a table whose only reader is an operator, and it leaks the story's text
into a table with no FK, i.e. a copy that no delete cleans up; accepted because the record is the
only artefact that outlives the deletion, and because `version_numbers` as `JSON` cannot be queried
relationally. The rejected alternative — `delete_with_record` split across a `StoryDeletionRepository`
and the story repository — cannot be one transaction, since both methods commit.

### Decision: the vector cleanup gets a port method that raises, and its failure is a declared 503

```python
# domain/ports/vector_store_port.py
@abstractmethod
async def delete_by_story(self, *, workspace_id: UUID, user_story_id: str) -> None:
    """Delete every point of one story in one workspace. Raises ``VectorStoreError`` on failure.

    Unlike ``search_similar``/``store_extraction``, this method does not degrade silently: the
    caller is a destructive operation that must not proceed on an unverified cleanup.
    """
```

The adapter implementation reuses the existing payload filter idiom
(`_build_workspace_filter`, `infrastructure/vector/qdrant_adapter.py:125-138`) with the story
condition added, on the two payload keys that already exist — `workspace_id` and `user_story_id`
(`:257-265`) — so it does not wait on slice (c)'s new keys:

```python
await client.delete(
    collection_name=self._collection_name,
    points_selector=qdrant_models.FilterSelector(filter=qdrant_models.Filter(must=[
        qdrant_models.FieldCondition(key="workspace_id", match=qdrant_models.MatchValue(value=str(workspace_id))),
        qdrant_models.FieldCondition(key="user_story_id", match=qdrant_models.MatchValue(value=user_story_id)),
    ])),
    wait=True,
)
```

No payload index is created for `user_story_id`: a filtered delete is correct without one, and
payload indexes are a collection-schema concern slice (c) owns. A driver failure is wrapped into a
new `VectorStoreError(Exception)` in `domain/entities/exceptions.py`, next to the `LLMError` family
that file already groups (`:42-88`), and `register_exception_handlers` gets
`vector_store_error_handler → 503 {detail, error_code: VECTOR_STORE_UNAVAILABLE}` — the exact shape
`llm_connection_error_handler` uses for a dependency that is down (`api/errors.py`).

This is the **seventh** registry entry, one more than the proposal's table of six. The proposal's
Approach step 5 requires the cleanup failure to answer "a 502/503" and its own code list has no code
for it, so the design reconciles the two in favour of the status: a `503` is the house convention for
a down dependency (`LLM_CONNECTION_ERROR`), and 409/500 would both misdescribe a retryable
infrastructure outage. The cost is mechanical and recorded below: the frontend mirror test's
`EXPECTED_REGISTRY_COUNT` and the `errorCodes` map in both locales move from six new codes to seven.

**Why**: the adapter's existing style is degrade-and-return (`search_similar` returns `[]`,
`store_extraction` returns `bool` and logs at ERROR), which is right when the caller can lose the
work. Here the caller cannot: a swallowed cleanup failure would run the relational delete and leave
exactly the orphan points D15 exists to prevent — a silent version of the failure the requirement
forbids.

**Tradeoff**: the port now has two failure doctrines (two methods degrade, one raises), which is a
real inconsistency to remember; the docstring states it in one sentence and the caller's own
requirement is the reason. The rejected alternatives: reusing `RepositoryError` (500
`REPOSITORY_ERROR`) needs no new code, no new handler and no mirror-test count change, but reports a
retryable outage as an internal error and contradicts the proposal's own 502/503; swallowing the
failure with a log would satisfy the letter of "the story survives" only by accident, since the next
step deletes it.

### Decision: `VersionAllocationConflictError` gets its own handler, and registration order is not what makes it win

```python
async def version_allocation_conflict_handler(request: Request, exc: VersionAllocationConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc), "error_code": VERSION_ALLOCATION_CONFLICT})
```

registered once in `register_exception_handlers` alongside the others. Starlette's
`ExceptionMiddleware` resolves a handler by walking `type(exc).__mro__` and taking the first class it
has a handler for, so a handler registered for the subclass is found before
`repository_error_handler`'s entry for `RepositoryError` regardless of the order the two
`app.add_exception_handler` calls run in (`api/app.py:150-155`). Slice (a)'s seam phrases this as
"registers its own handler before that one"; what is load-bearing is *which class* is registered, not
when.

409 over 503 because the database is healthy and the request lost a race it may re-run; 503 plus
`Retry-After` would advertise an infrastructure outage. The `detail` comes from `str(exc)`, which
slice (a)'s raise site composes with the story known (a's Data Flow: the conflict is raised from the
allocation path, after the story resolved). If the implementation finds `str(exc)` silent on the
story, the detail is composed from the exception's own `user_story_id` attribute — added when this
slice implements (a)'s exception — and never from a second lookup.

**Why**: `VersionAllocationConflictError` subclasses `RepositoryError` (a) so that a caller that
forgets it still gets a logged 500 rather than a crash; the subclass handler is what turns a
known case into a contract. The frontend depends on it: `categorizeExtractionError`
(`frontend/src/stores/taskStore.ts:99-121`) gains a `'version-conflict'` category whose check runs
before the status codes, exactly as the existing `LLM_CONFIG_INCOMPLETE` check does and for the same
stated reason ("the refusal carries the code, not the status"), and the extraction toast renders
`errorCodeHeadline('VERSION_ALLOCATION_CONFLICT', locale)`.

**Tradeoff**: two handlers now answer for one exception hierarchy, so a reader must know that MRO
decides; the alternative — mapping it inside `repository_error_handler` with an `isinstance` test —
puts one exception's contract inside another's handler and makes the 500 arm depend on the branch
being reached. The `'version-conflict'` category widens `ExtractionErrorCode`, whose union is
consumed by the extraction toast and its tests.

### Decision: the editor owns the field policy, the mark controls and both confirmations

`TaskEditor.tsx` keeps its shadcn `Dialog` shape and changes five things:

- `title` and `description` render as read-only text (no input, no textarea) — the write contract no
  longer accepts them, so an editable control would be a control that cannot save.
- No `priority` control at all (D21); `priority` stays in `TaskResponse` and in the JSON export.
- `dependencies` is disabled while `frozen`, where `frozen` is a prop the page computes from the
  selector's `is_current` for the task's version. The payload then cannot contain the key, so the
  editor can never trigger `TASK_VERSION_FROZEN` (proposal step 12, spec scenario "A frozen version
  offers no dependency edit to send").
- `status` and `labels` stay live in every state, including frozen — that is what keeps a `MEMBER`'s
  board working and what the kanban spec's drag-on-a-frozen-version scenario asserts.
- The mark controls: an "Inválida" checkbox, a mandatory reason textarea shown when it is checked,
  the D16 notice, and the two confirmation dialogs.

The submission sequence is the part worth naming, because it has three writes with different homes
and only one of them is the `PUT`:

```
onSubmit:
  if markChecked and reason.trim() === ''      → mark the field missing, return (no request)
  if markChecked and !wasMarked                → confirm dialog ("marca viaja al prompt…", cancel = no request)
                                                  → POST   /tasks/{id}/invalidations
  if !markChecked and wasMarked                → confirm dialog (cancel = no request)
                                                  → DELETE /tasks/{id}/invalidations/current
  always (when status/labels/dependencies changed)
                                               → PUT    /tasks/{id}   {status, labels[, dependencies]}
  optimistic taskStore update → rollback on any failure, dialog stays open with the edits
```

The "Marcar como inválida" button on the task card opens the same editor with the checkbox checked
and the focus in the reason field; nothing is applied until save, and cancel issues no request. The
D16 notice is fetched when the mark controls render (`GET …/invalidations/repetition`), shows the
earlier version and reason, and offers one action that copies that reason into the textarea — a
client-side fill and nothing else.

**Why**: D5's field policy is enforced in the backend, but the editor is where a user meets it, and a
read-only field that still looks editable would produce 422s on save. Owning the mark controls in the
editor (rather than a second dialog) is what the spec's trigger requirement describes: one surface,
three entry points, and the confirmation is a property of the *save*, not of the button.

**Tradeoff**: `TaskEditor` grows from a five-field form into a component with three optional writes
and two dialogs, and its props grow a `frozen` flag plus the current mark — the component's test
matrix roughly doubles. The rejected alternatives: a separate `MarkTaskDialog` (two surfaces editing
one task, and the "already marked → open with the reason populated" requirement would have to be
implemented twice); letting the editor send `dependencies` on a frozen version and relying on the
409 (the user meets a server refusal that the client already knew, and the spec asks for no
dependency edit to be sendable).

### Decision: the client mirrors the gate in one helper, and the controls are hidden rather than authoritative

`frontend/src/lib/workspace-role.ts` exports the predicate the UI needs, mirroring
`_is_owner_or_admin`:

```ts
export function canManageVersions(workspace: Workspace | null | undefined, userId: string | undefined): boolean {
  return !!workspace && !!userId && (workspace.role === 'admin' || workspace.ownerId === userId);
}
```

The `Workspace` type already carries both inputs (`frontend/src/types/workspace.ts:6-7`) and the
derivation already exists inline in `MemberManagement.tsx:109-111`, so the helper is a move, not an
invention. It drives: the disabled "Extract" button, the hidden/disabled "Marcar como inválida"
button, the hidden delete control in `StoryDetail.tsx` and `StoriesList.tsx`, and the disabled
confirm in the delete dialog. The server remains the authority in every case, and a refusal renders
`WORKSPACE_OWNER_OR_ADMIN_REQUIRED`'s localized copy rather than a raw 403.

**Why**: the spec asks for the refusal to be surfaced as explicit localized copy and for controls to
be hidden or disabled; hiding a control the server would refuse is courtesy, but the code path that
matters is the 403 copy, and both come from the same helper plus the `errorCodes` map.

**Tradeoff**: one more mirrored rule to keep in step with the backend, with no source-reading guard
(the repo's existing `*-mirror.test.ts` files read backend source; a truth table for
`canManageVersions` is the honest guard here, and the backend predicate gets its own unit test).
The rejected alternative — deriving "is owner or admin" inline in each of the four components — is
how the two drifts happen.

### Decision: the delete confirmation reads the version count, and a failed read does not block the delete

`StoryDetail.tsx` already has the versions (the selector read). `StoriesList.tsx` does not, so its
delete `AlertDialog` fetches `GET /stories/{id}/versions` on open and renders "…and its 2 versions
will be destroyed with it". If that read fails, the dialog keeps the confirmation enabled, drops the
count line, and shows a neutral fallback sentence instead.

**Why**: the dialog's count is a fact about the destructive action the user is confirming, and the
spec pins the copy ("the dialog says the story's 2 versions are destroyed with it"). Cancelling must
issue no HTTP request and delete nothing, which the dialog's existing `AlertDialog` shape already
gives.

**Tradeoff**: a failed metadata read produces a slightly less informative dialog instead of blocking
a destructive action. The rejected alternative — disabling the confirm until the count loads — turns
a transient read failure into "you cannot delete this story", and the count is informational rather
than a safety interlock: the gate, the record and the cleanup are the interlocks.

### Decision: the copy is corrected in both locales, and every new code gets neutral-Spanish copy

`landing.faq.a4` (`frontend/src/i18n/en.json:132`, `es.json:132`) currently promises "edit any of
them — title, description, labels, or dependencies". After D5/D21 the editable set is `status`,
`labels` and (while current) `dependencies`, so the sentence is rewritten in both locales. The
`errorCodes` family learns the seven new codes and the `taskEditor` family learns the mark controls,
the confirmations, the D16 notice, the "no output" state and the version selector's labels — all of
it neutral international Spanish (`tú`, no voseo) with identical key sets, which
`frontend/src/i18n/__tests__/neutral-spanish.test.ts` enforces for the variant and the key parity.

`frontend/src/lib/__tests__/error-codes.test.ts` pins the registry mirror three ways — every
`__all__` name mapped, no mapped code the backend does not emit, and
`EXPECTED_REGISTRY_COUNT` + `ROUTE_ERROR_CODES.length` as the exact sizes — so the seven new
registry entries move it from `36` to `43` and both locales from `41` to `48` keys. That change is
part of WU4, not an afterthought: the test is what makes a missing translation loud instead of a
silent fallback.

**Why**: the landing copy is a published promise the same change breaks (proposal step 14), and the
error-code mirror is the reason a new code is never a one-line server change in this repo.

**Tradeoff**: seven new copy keys per locale plus the corrected FAQ answer, and the two count
constants in the mirror test must move in the same commit; the alternative (mapping the new codes
lazily as surfaces happen to need them) is the drift the mirror test exists to catch, and it would
leave a `MEMBER`'s 403 showing generic copy.

## Data Flow

**Task read (story).** `GET /api/v1/tasks/?user_story_id=S[&extraction_id=X]` → membership walk → if
`X`: `find_by_id(X)` and refuse a foreign/nonexistent one with 422 `REQUEST_VALIDATION_FAILED` →
`list_page(user_story_id=S, extraction_id=X | CURRENT)`, where `CURRENT` is the correlated
highest-`completed`-version subquery → one statement carries `count(*) OVER ()` → the same
predicate rides the fallback `count_stmt` when the page falls past the end.

**Task read (workspace / unfiltered).** Same, with the `NOT EXISTS` predicate that needs no
subquery per story.

**Selector.** `GET /api/v1/stories/S/versions` → the unchanged membership walk (404 missing story /
403 non-member) →
`list_versions(S)` ordered `version_number DESC` → each entry decorated with `is_current` (first
`completed` in the list) and `has_output` (`status == completed`) → bare array.

**Extract.** `POST /api/v1/workspaces/W/extract/` → `require_owner_or_admin` (403
`WORKSPACE_OWNER_OR_ADMIN_REQUIRED` for a `MEMBER`) → `missing_llm_config_fields(...)` refuses an
incomplete config → `temperature` resolved once → slice (a)'s `create_next_version(...)` mints
`version_number` → 202 `{extraction_id, status, version_number, provider, temperature}` →
`asyncio.create_task(run_background_extraction(...))`. An exhausted allocation retry raises
`VersionAllocationConflictError` → its own handler → 409 `VERSION_ALLOCATION_CONFLICT`.

**Field policy.** `PUT /api/v1/tasks/T` → membership walk (no gate) → schema resolution refuses
`title`/`description`/`priority` with 422 → `find_current_version(T.user_story_id)` → if
`"dependencies" in model_fields_set and (current is None or T.extraction_id != current.id)` → 409
`TASK_VERSION_FROZEN` → else the existing state-machine check → `replace(...)` + `repo.save(...)`.

**Mark.** `POST /api/v1/tasks/T/invalidations` → `require_task_owner_or_admin` → reason validator
(422 if blank) → frozen check (409) → `find_active_by_task` (409 `TASK_ALREADY_MARKED`) →
`create(...)` → 201. `DELETE …/invalidations/current` → gate → frozen check → `find_active_by_task`
(404 if none) → `revoke(...)` → 204. `GET …/invalidations` → membership only → `list_by_task`
(`marked_at DESC`, active first). `GET …/invalidations/repetition` → membership only →
`list_active_on_other_versions` → Python `normalize_task_title` equality → `{"matches": [...]}`.

**Export.** `GET /api/v1/workspaces/W/export/tasks/?format=…` → membership only →
`list_current_by_workspace(W)` (the `NOT EXISTS` predicate in the serializing statement) →
JSON array or grouped Markdown.

**Story delete.** Gate → `list_versions` (snapshot) → `delete_by_story` on the vector store →
`delete_with_record` (one transaction: `DELETE stories` cascading in the database, `INSERT
story_deletions`).

**Frontend.** `StoryDetail` loads the selector and picks the displayed version (current by default) →
passes `frozen` and the task's mark to `TaskEditor` → the editor's three writes as above →
`taskStore.fetchTasksForWorkspace` unchanged, now receiving only current-version tasks.

## Interfaces / Contracts

```
# api/schemas/task.py
UpdateTaskRequest(status?, labels?, dependencies?)         # extra="forbid"; title/description/priority removed
CreateTaskRequest                                          # deleted
InvalidationResponse: {id, reason, marked_by, marked_at, revoked_by, revoked_at}
CreateInvalidationRequest(reason: str = Field(..., max_length=500))   # blank → 422
class RepetitionMatch: {version_number, reason, marked_at}
class RepetitionResponse: {matches: list[RepetitionMatch]}

# api/schemas/story.py
class StoryVersionResponse: {id, version_number, status, model_used, provider, temperature,
                             created_at, completed_at, error_info, is_current, has_output}

# api/schemas/extraction.py
ExtractionResponse / ExtractResponse  +=  version_number: int | None, provider: str, temperature: float

# api/error_codes.py  (alphabetically-sorted __all__, seven additions)
TASK_ALREADY_MARKED, TASK_CREATION_ENDPOINT_REMOVED, TASK_DELETE_ENDPOINT_REMOVED,
TASK_VERSION_FROZEN, VECTOR_STORE_UNAVAILABLE, VERSION_ALLOCATION_CONFLICT,
WORKSPACE_OWNER_OR_ADMIN_REQUIRED

# api/dependencies.py
_is_owner_or_admin(workspace, role, user) -> bool
StoryAccess(story, workspace_id, role); TaskAccess(task, workspace_id, role)
resolve_story_access(...) -> StoryAccess            # unchanged refusals: 404 missing, 403 non-member
resolve_task_access(...) -> TaskAccess
require_story_workspace_access(...) -> UserStory    # unchanged signature and refusals
require_owner_or_admin / require_story_owner_or_admin / require_task_owner_or_admin

# domain/entities/exceptions.py
VectorStoreError(Exception)                         # raised only by VectorStorePort.delete_by_story

# domain/ports/task_invalidation_repository.py
create(mark) / find_active_by_task(task_id) / list_by_task(task_id)
revoke(mark_id, *, revoked_by, revoked_at)
list_active_on_other_versions(*, user_story_id, exclude_extraction_id) -> list[TaskInvalidationCandidate]

# domain/ports/extraction_repository.py
list_versions(user_story_id) -> list[Extraction]    # version_number DESC, deliberately unbounded

# domain/ports/task_repository.py
list_page(..., user_story_id=?, extraction_id=?, workspace_id=?, workspace_ids=?, ...)   # current-version predicate
list_current_by_workspace(workspace_id) -> list[Task]

# domain/ports/user_story_repository.py
delete_with_record(user_story_id, record: StoryDeletion) -> None

# domain/ports/vector_store_port.py
delete_by_story(*, workspace_id: UUID, user_story_id: str) -> None    # raises VectorStoreError

# frontend/src/lib/versioning-api.ts
listVersions(storyId) -> StoryVersion[]
createInvalidation(taskId, reason) -> Invalidation
listInvalidations(taskId) -> Invalidation[]
revokeInvalidation(taskId) -> void
fetchRepetition(taskId) -> {matches: RepetitionMatch[]}

# frontend/src/lib/workspace-role.ts
canManageVersions(workspace, userId) -> boolean
```

## File Changes

| Path | WU | Change |
| --- | --- | --- |
| `backend/src/storico/api/schemas/task.py` | 1, 4 | `UpdateTaskRequest` shrinks; `CreateTaskRequest` deleted; mark schemas |
| `backend/src/storico/api/schemas/story.py` | 2, 3 | `StoryVersionResponse` |
| `backend/src/storico/api/schemas/extraction.py` | 2 | `version_number`, `provider`, `temperature` |
| `backend/src/storico/api/routes/tasks.py` | 1, 2, 4 | Field matrix; two `410` handlers; `extraction_id` read param; three mark endpoints + repetition |
| `backend/src/storico/api/routes/stories.py` | 2, 3 | `GET /{story_id}/versions`; gated `DELETE` with snapshot, cleanup and record |
| `backend/src/storico/api/routes/extraction.py` | 3 | `require_owner_or_admin`; `version_number` in the 202 body |
| `backend/src/storico/api/routes/export.py` | 2 | `list_current_by_workspace` |
| `backend/src/storico/api/dependencies.py` | 3 | `_is_owner_or_admin`, `StoryAccess`/`TaskAccess`, the shared walk, three wrappers — the walk's own refusals stay unchanged (404 missing, 403 non-member) |
| `backend/src/storico/api/error_codes.py` | 1, 3, 4 | Seven entries in the sorted `__all__` + their comment blocks |
| `backend/src/storico/api/errors.py` | 3 | `version_allocation_conflict_handler` (409), `vector_store_error_handler` (503) |
| `backend/src/storico/domain/entities/task_invalidation.py` | 4 | New entity |
| `backend/src/storico/domain/entities/story_deletion.py` | 3 | New entity |
| `backend/src/storico/domain/entities/exceptions.py` | 3 | `VectorStoreError` |
| `backend/src/storico/domain/ports/task_invalidation_repository.py` | 4 | New port + `TaskInvalidationCandidate` |
| `backend/src/storico/domain/ports/{extraction_repository,task_repository,user_story_repository,vector_store_port}.py` | 2, 3 | `list_versions`; the page/current reads; `delete_with_record`; `delete_by_story` |
| `backend/src/storico/domain/services/task_title_normalizer.py` | 4 | New: `normalize_task_title` |
| `backend/src/storico/application/services/story_deletion_service.py` | 3 | New: snapshot ordering, cleanup-before-delete |
| `backend/src/storico/infrastructure/database/models/story_deletion.py` | 3 | New model (no FK to `stories`/`extractions`) |
| `backend/src/storico/infrastructure/database/models/__init__.py` | 3 | Register the model (the drift gate compares models to the migrated schema) |
| `backend/src/storico/infrastructure/database/alembic/versions/0029_story_deletions.py` | 3 | New revision (`down_revision = "0028"`) + `downgrade()` |
| `backend/src/storico/infrastructure/database/repositories/task_invalidation_repository.py` | 4 | New |
| `backend/src/storico/infrastructure/database/repositories/task_repository.py` | 2 | Current-version predicate per scope; `list_current_by_workspace` |
| `backend/src/storico/infrastructure/database/repositories/user_story_repository.py` | 3 | `delete_with_record` |
| `backend/src/storico/infrastructure/database/repositories/extraction_repository.py` | 2 | `list_versions` |
| `backend/src/storico/infrastructure/vector/qdrant_adapter.py` | 3 | `delete_by_story` (`FilterSelector`, `wait=True`, raises `VectorStoreError`) |
| `backend/tests/**` | 1–4 | See the testing table below |
| `frontend/src/components/react/VersionSelector.tsx` | 4 | New |
| `frontend/src/components/react/TaskEditor.tsx` | 1, 4 | Read-only fields, no `priority`, frozen `dependencies`, mark controls, confirmations, D16 notice |
| `frontend/src/components/react/{StoryDetail,StoriesList}.tsx` | 3, 4 | Version state, mark button, extract confirmation, version count in the delete dialog, MEMBER-hidden controls |
| `frontend/src/components/react/{KanbanBoard,ExportPanel}.tsx` | 2 | Consume the filtered reads; frozen cards stay draggable |
| `frontend/src/lib/versioning-api.ts` | 4 | New |
| `frontend/src/lib/workspace-role.ts` | 4 | New |
| `frontend/src/lib/tasks-api.ts` | 1 | Stop sending `title`/`description`; drop `priority` |
| `frontend/src/stores/taskStore.ts` | 2, 4 | Version selection slice; `'version-conflict'` category |
| `frontend/src/stores/storyStore.ts` | 3, 4 | Version count for the delete dialog |
| `frontend/src/types/{task,story,workspace}.ts` | 4 | Version and mark types |
| `frontend/src/i18n/{en,es}.json` | 1, 3, 4 | Seven new codes, mark/selector/no-output copy, corrected `landing.faq.a4` |

## Testing Strategy

STRICT TDD, in the config's order (RED → GREEN → TRIANGULATE → REFACTOR). Every scenario below gets
its failing test first; a work unit does not close until the whole suite is green. Backend:
`cd backend && conda run -n storico python -m pytest`, with the unit schema built from the models
(`Base.metadata.create_all`, `tests/conftest.py:149`, `sqlite+aiosqlite://`) and
`cd backend && conda run -n storico python -m pytest -m integration` for the Postgres-only
invariants (testcontainers, skipped without a Docker daemon). Frontend: `cd frontend && pnpm test`.
No E2E is runnable (`@playwright/test` is not a devDependency), so every UI scenario is a component
test against `@testing-library/react` with mocked `fetch`.

Two facts the table depends on. **SQLite does not enforce foreign keys in this suite** (no
`PRAGMA foreign_keys=ON`), so the delete's cascade and the record's survival are integration tests,
placed beside slice (a)'s. **Sessions**: nothing here assumes two repository calls share a
transaction. The transaction case asserts the opposite direction — a failing record insert leaves the
story present — by forcing the insert to raise.

The seven deltas carry **25** `### Requirement:` headings (the proposal's prose says 21; the table
covers all 25 — 7 `extraction-versioning`, 4 `task-invalidation`, 3 `workspace-permissions`, 6
`task-editor`, 2 `extraction-workflow`, 2 `kanban-board`, 1 `export-download`).

| Requirement (spec scenario) | Test | Home | Layer |
| --- | --- | --- | --- |
| Task Reads Return the Current Version Only — v1+v2 completed, only v2's 4 tasks, `total` 4 | Story-scoped read with two completed versions | `test_repositories/test_task_repo.py` + `test_api/test_tasks.py` | Unit |
| … — workspace page and total agree on the filtered set | `total` equals `len(items)` for a workspace with a superseded earlier version | `test_repositories/test_task_repo.py` | Unit |
| … — a page past the end still carries the filtered total | Fallback `count_stmt` path with the superseded version present | `test_repositories/test_task_repo.py` | Unit |
| … — the unfiltered read is filtered too | No-parameter `GET /api/v1/tasks/` shows no superseded tasks | `test_api/test_unfiltered_list_queries.py` | Unit |
| … — a specific version through `extraction_id` | `?user_story_id=&extraction_id=<v1>` returns v1's tasks | `test_api/test_tasks.py` | Unit |
| … — a foreign `extraction_id` is refused | 422 `REQUEST_VALIDATION_FAILED`, no task of story B | `test_api/test_tasks.py` | Unit |
| … — `extraction_id` without `user_story_id` is refused | 422 `REQUEST_VALIDATION_FAILED` | `test_api/test_tasks.py` | Unit |
| … — a story with no completed version reads empty | 200 `[]` for a failed-only story | `test_api/test_tasks.py` | Unit |
| The Story's Versions Are Readable Through One Selector Endpoint — lists all, marks current | Three versions, exactly v3 `is_current` | `test_api/test_stories.py` | Unit |
| … — a pending top version does not displace the current one | v2 completed + v3 pending → v2 current | `test_api/test_stories.py` | Unit |
| … — unpaginated by design | 25 versions in one payload | `test_api/test_stories.py` | Unit |
| … — an inaccessible story is a visible error | Missing story 404, non-member 403 — never a silent empty 200 | `test_api/test_stories.py` | Unit |
| … — `is_current` agrees with `find_current_version` | Repository cross-check on one story | `test_repositories/test_extraction_repo.py` | Unit |
| … — `list_versions` ordering | `version_number DESC` | `test_repositories/test_extraction_repo.py` | Unit |
| A Failed Version Is Surfaced Honestly — selector offers it with `error_info`, no output | Failed version row carries `status`, `error_info`, model, provider, temperature, `has_output=false` | `test_api/test_stories.py` | Unit |
| … — the absence of output is rendered, not implied | Localized "no output" state, never an empty board | `frontend/src/components/react/__tests__/StoryDetail.test.tsx` | Frontend |
| Task Creation and Single-Task Deletion Are Retired with 410 Gone — create writes nothing | 410 `TASK_CREATION_ENDPOINT_REMOVED`, `detail` names D3, no row added | `test_api/test_tasks.py` | Unit |
| … — delete deletes nothing | 410 `TASK_DELETE_ENDPOINT_REMOVED`, task still linked to its version | `test_api/test_tasks.py` | Unit |
| … — a non-member learns nothing new | Same 404/403 shape as the membership walk gives today | `test_api/test_tasks.py` | Unit |
| … — slice (a)'s pinned refusal flips to the 410 | `TestCreateTask::test_create_task` and `::test_create_task_with_labels` — the two cases (a) rewrote to pin the 500 — now pin the 410 | `test_api/test_tasks.py` | Unit |
| The Task Write Contract Enforces the Field Matrix — status on frozen | 200 + persisted | `test_api/test_tasks.py` | Unit |
| … — labels on frozen | 200 + persisted | `test_api/test_tasks.py` | Unit |
| … — dependencies on frozen | 409 `TASK_VERSION_FROZEN`, detail carries the current number, unchanged | `test_api/test_tasks.py` | Unit |
| … — explicit `[]` on frozen | 409, nothing cleared | `test_api/test_tasks.py` | Unit |
| … — `null` on frozen | 409 (presence is the write) | `test_api/test_tasks.py` | Unit |
| … — no key keeps working on frozen | `{"status": "review"}` → 200 | `test_api/test_tasks.py` | Unit |
| … — `title`/`description`/`priority` in every state | 422 `REQUEST_VALIDATION_FAILED` on both a frozen and a current task, no field changed | `test_api/test_tasks.py` | Unit |
| … — dependencies on the current version | 200 + persisted | `test_api/test_tasks.py` | Unit |
| … — frozen and illegal transition together | 409 wins over the state machine, nothing written | `test_api/test_tasks.py` | Unit |
| … — story with no completed version | 409 with "no current version" in the detail | `test_api/test_tasks.py` | Unit |
| An Exhausted Version Allocation Surfaces as an Explicit Conflict — 409 + hint | Forced `VersionAllocationConflictError` → 409 `VERSION_ALLOCATION_CONFLICT` | `test_api/test_extraction.py` | Unit |
| … — never 500, never a silent success | Status pinned at 409; no extraction row written | `test_api/test_extraction.py` | Unit |
| … — the client distinguishes it | `'version-conflict'` category + localized headline | `frontend/src/stores/__tests__/taskStore.unit.test.ts` | Frontend |
| Story Deletion Is the Only Sanctioned Deletion of Versions — owner deletes, record written | Story, versions, tasks gone; record carries actor, timestamp, `[1, 2]`; points gone | `test_api/test_stories.py` (+ integration for the cascade) | Unit + Integration |
| … — cleanup is part of the operation | Recording fake vector store receives one `delete_by_story` for the story | `test_api/test_stories.py` | Unit |
| … — a vector failure aborts and preserves | Fake store raises → 503 `VECTOR_STORE_UNAVAILABLE`; story, versions, tasks present; no record, no relational delete | `test_api/test_stories.py` | Unit |
| … — the record survives the story | No FK to `stories`/`extractions`; the row outlives the cascade | `test_integration/test_story_deletion_record.py` | Integration |
| … — `deleted_by` survives account deletion | Deleting the actor nulls `deleted_by` only | `test_integration/test_story_deletion_record.py` | Integration |
| … — a `MEMBER` cannot delete | 403 `WORKSPACE_OWNER_OR_ADMIN_REQUIRED`, everything intact | `test_api/test_stories.py` | Unit |
| … — the dialog names the versions | Copy names the count; cancel issues no request | `frontend/src/components/react/__tests__/{StoryDetail,StoriesList}.test.tsx` | Frontend |
| … — no vector store configured | Delete completes, record written, no vector call | `test_api/test_stories.py` | Unit |
| … — a failing record insert rolls back the delete | Forced repository error leaves the story present | `test_repositories/test_story_repo.py` | Unit |
| … — `0029` reaches the head and the drift gate passes | `alembic upgrade head`; models ↔ migrated schema difference is empty | `test_integration/test_migration_chain.py` (existing) | Integration |
| The Gate Is the Owner-or-Admin Rule — accepts owner and `ADMIN` only | Truth table over `_is_owner_or_admin` | `test_unit/test_workspace_gate.py` | Unit |
| … — a non-member keeps today's refusal | Same 404/403 as the membership walk on each gated route | `test_api/test_tasks.py` + `test_api/test_stories.py` | Unit |
| The Four Version-Mutating Operations Require the Gate — `MEMBER` refused on all four | 403 `WORKSPACE_OWNER_OR_ADMIN_REQUIRED` × 4, no data changed | `test_api/{test_extraction,test_tasks,test_stories}.py` | Unit |
| … — owner and `ADMIN` succeed on all four | Both identities, four operations | `test_api/{test_extraction,test_tasks,test_stories}.py` | Unit |
| … — the refusal is localized, not a raw 403 | `errorCodeHeadline` renders the code's copy | `frontend/src/lib/__tests__/error-codes.test.ts` | Frontend |
| The Member-Accessible Surface Is Stated and Protected — full read-and-edit surface | `MEMBER` reads board, moves a card, edits labels and the story's four fields, reads versions, calls repetition — all 200 | `test_api/test_tasks.py` + `test_api/test_stories.py` | Unit |
| … — a `MEMBER`'s status edit is never gated | `{"status": "in_progress"}` → 200, gate not consulted | `test_api/test_tasks.py` | Unit |
| Creating a Mark Requires a Reason, the Current Version and the Gate — round-trip | 201 with reason, actor, timestamp; one row | `test_api/test_tasks.py` | Unit |
| … — blank reason persists nothing | 422 `REQUEST_VALIDATION_FAILED` for `""`, `"   "`, `"\t\n"`, no row | `test_api/test_tasks.py` + `test_unit/test_invalidation_request.py` | Unit |
| … — a second active mark carries the live reason | 409 `TASK_ALREADY_MARKED`, detail has the reason, still one row | `test_api/test_tasks.py` | Unit |
| … — marking on a frozen version | 409 `TASK_VERSION_FROZEN`, no row | `test_api/test_tasks.py` | Unit |
| … — a `MEMBER` is refused with localized copy | 403, no row; frontend renders the code's copy | `test_api/test_tasks.py` + `frontend/src/lib/__tests__/error-codes.test.ts` | Unit + Frontend |
| The Mark Record Is Readable With Its Full History — active first, full fields | Revoked + active rows ordered, all six fields | `test_api/test_tasks.py` | Unit |
| … — a task with no marks reads empty | 200 `[]` | `test_api/test_tasks.py` | Unit |
| … — readable by every member | `MEMBER` GET → 200 | `test_api/test_tasks.py` | Unit |
| Revoking Updates the Row and Never Deletes It — records who and when | 204; same row, `marked_by`/`marked_at`/`reason` intact | `test_api/test_tasks.py` | Unit |
| … — blocked on a frozen version | 409 `TASK_VERSION_FROZEN`, row unchanged | `test_api/test_tasks.py` | Unit |
| … — no active mark is a 404 | 404 | `test_api/test_tasks.py` | Unit |
| … — re-marking keeps both readable | Second 201, two rows, first still revoked | `test_api/test_tasks.py` | Unit |
| The Repetition Read Warns on an Exact Normalized-Title Match — match offered | `"Implement  Login Retry"` vs `"Implement login retry"` → one match with v1 and reason | `test_api/test_tasks.py` | Unit |
| … — nothing similar, no match | `{"matches": []}` | `test_api/test_tasks.py` | Unit |
| … — the task's own version does not match | Same-version sibling → `[]` | `test_api/test_tasks.py` | Unit |
| … — other stories never match | Same title, other story's mark → `[]` | `test_api/test_tasks.py` | Unit |
| … — the read writes nothing | No row created/updated/revoked | `test_api/test_tasks.py` | Unit |
| … — revoked marks do not warn | Revoked mark on another version → `[]` | `test_api/test_tasks.py` | Unit |
| … — the normalizer | `casefold` + whitespace collapse + strip, table-driven | `test_unit/test_task_title_normalizer.py` | Unit |
| Task Editor Component — read-only title/description, live status/labels | Renders `readOnly` text, editable select and tags, no `priority` control | `frontend/.../TaskEditor.test.tsx` | Frontend |
| … — frozen locks dependencies, keeps status/labels live | Disabled multi-select; the mask checkbox disabled | `frontend/.../TaskEditor.test.tsx` | Frontend |
| Task Editor Trigger — edit disabled during extraction | Disabled with a tooltip | `frontend/.../TaskEditor.test.tsx` | Frontend |
| … — mark button opens with the checkbox set and focus in the reason | Checkbox checked, `document.activeElement` is the textarea, zero requests | `frontend/.../StoryDetail.test.tsx` | Frontend |
| … — cancelling leaves no mark | No request, no mark | `frontend/.../StoryDetail.test.tsx` | Frontend |
| … — an already-marked task opens with the reason populated | Reason prefilled from the mark read | `frontend/.../TaskEditor.test.tsx` | Frontend |
| Task Editor Persistence — payload carries no removed fields | `fetch` body has `status`, `labels`, no `title`/`description`/`priority` | `frontend/.../TaskEditor.test.tsx` + `frontend/src/lib/__tests__/tasks-api.test.ts` | Frontend |
| … — empty reason blocks the save | No request, reason field flagged missing | `frontend/.../TaskEditor.test.tsx` | Frontend |
| … — a reason marks the task | `POST` with the reason, success toast, dialog closes | `frontend/.../TaskEditor.test.tsx` | Frontend |
| … — unchecking revokes | `DELETE …/current`, row not deleted | `frontend/.../TaskEditor.test.tsx` | Frontend |
| … — save failure rolls back without data loss | Optimistic value restored, dialog open, edits intact, toast | `frontend/.../TaskEditor.test.tsx` | Frontend |
| Labels and Dependencies Validation — dedupe and empty rejection | Case-insensitive duplicate refused, whitespace-only adds nothing | `frontend/.../TaskEditor.test.tsx` | Frontend |
| … — self-dependency rejected | Localized warning toast | `frontend/.../TaskEditor.test.tsx` | Frontend |
| … — a frozen version offers no dependency edit to send | No `dependencies` key in the payload | `frontend/.../TaskEditor.test.tsx` | Frontend |
| Marking and Unmarking Ask for Confirmation — mark confirmed | Dialog copy names the prompt travel and the freeze; confirm applies, cancel writes nothing | `frontend/.../TaskEditor.test.tsx` | Frontend |
| … — unmark confirmed | Same, for the revoke | `frontend/.../TaskEditor.test.tsx` | Frontend |
| The Editor Warns on a Repetition of a Marked Title — notice with version and reason | Notice text with v1 and the reason, localized in both locales | `frontend/.../TaskEditor.test.tsx` | Frontend |
| … — one action copies the reason | Textarea filled, nothing persisted | `frontend/.../TaskEditor.test.tsx` | Frontend |
| … — the notice writes nothing | No request of any kind from rendering or dismissing | `frontend/.../TaskEditor.test.tsx` | Frontend |
| … — a near-identical title does not trigger it | One-character difference → no notice, no similarity call | `frontend/.../TaskEditor.test.tsx` | Frontend |
| Workspace-Scoped Extraction Client — happy path after confirmation | Confirmation dialog, `POST /workspaces/{id}/extract/`, `versionNumber` stored | `frontend/.../StoryDetail.test.tsx` | Frontend |
| … — cancelling performs no request | No fetch | `frontend/.../StoryDetail.test.tsx` | Frontend |
| … — the confirmation names v2 frozen and v3 created | Copy names both numbers | `frontend/.../StoryDetail.test.tsx` | Frontend |
| … — no workspace selected | Localized toast, no request | `frontend/.../StoryDetail.test.tsx` | Frontend |
| … — a `MEMBER` is refused with localized copy | 403 code's copy, no version created | `frontend/.../StoryDetail.test.tsx` | Frontend |
| … — the 202 gains `version_number` | Route test on the response body | `test_api/test_extraction.py` | Unit |
| Extraction Error Surfacing — status `failed` | Store sets the error, clears the flag, keeps `tasks[storyId]` | `frontend/src/stores/__tests__/taskStore.unit.test.ts` | Frontend |
| … — HTTP/network error | Same, from the thrown error | `frontend/src/stores/__tests__/taskStore.unit.test.ts` | Frontend |
| … — 401 / 403 / 409 distinguished | `unauthorized`, `WORKSPACE_OWNER_OR_ADMIN_REQUIRED`, `VERSION_ALLOCATION_CONFLICT` each categorized | `frontend/src/stores/__tests__/taskStore.unit.test.ts` | Frontend |
| Kanban Task Fetching — no workspace selected | Localized prompt, no HTTP request | `frontend/.../KanbanBoard.test.tsx` | Frontend |
| … — two completed runs show only the current version | 4 cards, none from v1 | `frontend/.../KanbanBoard.test.tsx` (+ the repository test proves the server half) | Frontend |
| … — a failed-only story contributes nothing and no error | Fetch succeeds, no cards | `frontend/.../KanbanBoard.test.tsx` | Frontend |
| Kanban Drag-and-Drop Status Update — drag updates status | `PUT` with `{status: "todo"}`, optimistic, rollback on failure | `frontend/.../KanbanBoard.test.tsx` | Frontend |
| … — drag in flight blocks re-drag | Card not draggable, spinner | `frontend/.../KanbanBoard.test.tsx` | Frontend |
| … — a status change on a frozen version succeeds | No block, no warning; server half in `test_api/test_tasks.py` | `frontend/.../KanbanBoard.test.tsx` | Frontend |
| Backend Export Endpoint — JSON and Markdown happy paths | Content type, filename, valid JSON / grouped Markdown | `test_api/test_export.py` | Unit |
| … — only the current version's tasks | 4 tasks of v2, none of v1, in both formats | `test_api/test_export.py` | Unit |
| … — a failed-only story contributes nothing and breaks nothing | Valid file, no tasks for that story | `test_api/test_export.py` | Unit |
| The current-version filter on reads (cross-cutting) | The four surfaces above agree on the same story: `GET /tasks` (story, workspace, unfiltered), the export and the board | `test_api/test_tasks.py` + `test_api/test_export.py` | Unit |
| The error-code mirror and the copy | `EXPECTED_REGISTRY_COUNT` 36 → 43; both locales 41 → 48; every new code mapped; `landing.faq.a4` rewritten | `frontend/src/lib/__tests__/error-codes.test.ts` + `neutral-spanish.test.ts` | Frontend |

## Threat Matrix

| Threat | Mitigation | Pinned by |
| --- | --- | --- |
| The editor 422s on every save because the schema shrank first | Schema and client change in one work unit (WU1) | `TaskEditor` payload test + `tasks-api` test |
| `dependencies` presence misread, so a frozen version accepts a write | Key on `model_fields_set`, never on `None`; `[]` and `null` cases both pinned | Field-matrix cases in `test_api/test_tasks.py` |
| A `MEMBER`'s status edit refused by an over-broad gate | `PUT /tasks/{id}` keeps its membership walk; the gate is three named wrappers, none of them on `PUT` | Gate surface test |
| `total` counts rows the page does not return | The predicate joins the same `scope` as the page, so the window count and the fallback count share it | Repository page/total case |
| The unfiltered `GET /tasks/` keeps leaking superseded tasks | The predicate is applied to all three scopes | `test_api/test_unfiltered_list_queries.py` |
| A selector read silently truncates a long history | `list_versions` is unbounded by signature and documented as such | 25-version case |
| A selector read discloses more than today's story read does | It does not: the selector reuses the unchanged walk, so 403-for-non-member is the posture `GET /stories/{id}` already has | Selector refusal case |
| `casefold` approximated in SQL, answering a different question | The match runs in Python; SQL only narrows the story and the version | Normalizer table + repetition cases |
| Orphan Qdrant points outlive the story (D15 + D10) | Cleanup runs before the relational delete and aborts it on failure | Vector-failure case |
| A swallowed Qdrant failure deletes the story anyway | `delete_by_story` raises instead of degrading; `wait=True` | Vector-failure case + the port docstring |
| The deletion record dies with the story | `0029` has no FK to `stories`/`extractions`; identity copied as values | Integration record case |
| A crash between the record and the delete loses the audit trail | Both statements in one transaction inside `delete_with_record` | Rollback case |
| An operator cannot tell who deleted | `deleted_by` + `deleted_at` + `version_numbers` on the record | Record case + integration |
| `VersionAllocationConflictError` still answers 500 | A handler registered for its own class; MRO decides, not registration order | 409 case |
| A `MEMBER` meets a raw 403 | `WORKSPACE_OWNER_OR_ADMIN_REQUIRED` mapped in `lib/error-codes.ts` and both locales; controls hidden/disabled | Mirror test + component tests |
| A new code ships without copy | The mirror test fails on a missing key and on an invented one | `error-codes.test.ts` |
| The revoke `DELETE` reads as a contradiction of D12 | The endpoint updates the row; the record survives; the spec's own scenario pins that `marked_by`/`marked_at` stay | Revoke case |
| The retired `410`s still delete or insert | The handlers contain no write statement at all | 410 cases assert the row count |
| A `410` catch-all swallows the revoke route | Both retirements use exact paths, not `/{path:path}` | Route shape test (declared paths) |
| The corrected FAQ copy re-broken by a later revert | The copy is part of the change and is re-broken only deliberately | `api-docs-copy`/i18n guards + the FAQ key assertion |
| Review budget exceeded without a delivery decision | Four work units; `ask-on-risk` pauses on budget risk | Not testable — a process control |

## Migration / Rollout

1. Slice (a)'s D11 wipe (relational data plus `storico_extractions_dev` / `storico_extractions_prod`)
   runs before the deploy that carries `0028`, as (a) states. This slice adds no data step.
2. `0029_story_deletions.py` continues the chain from `0028` (`down_revision = "0028"`), creates one
   table with one index and one FK and nothing else, and its `downgrade()` drops that table. It is
   additive and safe on a populated database, so unlike `0028` it needs no empty-database guard.
3. Deploy runs `alembic upgrade head` inside ADR-005's maintenance window between `docker stop` and
   `docker run`. `0029` is a fast DDL step; the window's cost is unchanged.
4. **(a) and (b) ship in one release.** (a) alone shows two task sets per story (its own note), and
   (b) alone does not run at all: it consumes `version_number`, `tasks.extraction_id`,
   `task_invalidations`, `find_current_version` and `VersionAllocationConflictError` from (a).
5. Rollback: restore `title`/`description`/`priority` in `UpdateTaskRequest` and the frozen guard
   goes with them; restore the `DELETE` and `POST` task handlers; drop the mark endpoints; restore
   the membership-only gates on extract and story delete; remove the current-version predicates;
   revert the three response scalars; `alembic downgrade 0028`. Losing `story_deletions` loses the
   audit trail of deletes performed while the release was live.
6. **Not reversible:** a story destroyed under D15 and its Qdrant points are gone (C7). A revert must
   not re-break the corrected `landing.faq.a4`, and the `410` paths reverting restores the
   contradiction D17 removed.
7. No new runtime dependency and no new setting.

## Open Questions

None. Every shape the proposal left to this phase is settled above: the gate's predicate and its
three wrappers, the shared walk, the field matrix's presence rule, the two retirement handlers, the
current-version predicate in three scopes, the selector's unbounded read and its two computed fields,
the mark's entity/port/repository and the validator, the normalizer's home, the delete's ordering and
its record, the vector port's raising doctrine, the allocation handler and the client-side gate
mirror. Three items are decided *with a contingency* rather than left open:

- **The seventh error code.** `VECTOR_STORE_UNAVAILABLE` is one more registry entry than the
  proposal's table of six; the proposal's own Approach step 5 requires the cleanup failure to answer
  502/503 and lists no code for it, and the design reconciles that in favour of the status. If the
  review prefers to honour the six-code list literally, the fallback is `RepositoryError` → 500
  `REPOSITORY_ERROR` with no new code and no new handler, at the cost of reporting a retryable
  outage as an internal error.
- **The allocation handler's `detail`.** It uses `str(exc)`; if slice (a)'s exception turns out not to
  name the story, (b) adds a `user_story_id` attribute to that exception when it implements it,
  because (a) is artifacts-only today and no code forecloses the addition.
- **The pinned Qdrant client's delete API.** `FilterSelector` + `wait=True` is the current
  `qdrant_client` shape; WU3's first RED step pins the call against a fake client, and the sanctioned
  fallback is `delete(collection_name, points_selector=filter, wait=True)` if the pinned version
  accepts the bare filter.
