# Design: Extraction Versioning — Schema and Version Identity

> **Change**: `extraction-versioning-schema`
> **Based on**: `proposal.md`, `specs/`, `explore.md`
> **Created**: 2026-09-28

Slice (a) of three. It builds the storage and the identity rules the two sibling changes read:
migration `0028`, the per-story version number, the task→run link, the run's snapshot columns, the
invalidation mark table, and the removal of the write paths that could destroy any of it.

Measured starting point: `main` `ecea3e2`, Alembic head `0027`, no migration declares
`down_revision = "0027"`, so this change claims `0028`. The unit suite builds its schema from the
models (`Base.metadata.create_all` in `tests/conftest.py`), and only `tests/test_integration/`
executes the migration chain, against a Postgres 16 container.

The spine of the design is three sentences. **The number is minted by the database inside the
row's own `INSERT`.** **The snapshot is written once, between render and generate, before any
provider is contacted.** **The extraction port loses every method that verbatim-writes a whole
row**, so a later reader cannot silently null a snapshot column.

## Technical Approach

Ordered work, from the schema outward. Work units (WU1–WU4) are the review slices the tasks phase
should keep together; each ends on a green suite.

**WU1 — Schema identity.** `0028_extraction_versioning.py` with the empty-database guard first;
`ExtractionModel` gains `version_number`, `provider`, `temperature`, `prompt_rendered`;
`TaskModel` gains `extraction_id` (FK `ON DELETE CASCADE`) plus `ix_tasks_extraction_id`; the
`TaskInvalidationModel` table with its partial unique index and two `CHECK`s; the domain entities
follow (`Extraction.provider`/`temperature` required, `version_number`/`prompt_rendered` optional,
`Task.extraction_id`); the repository gains `create_next_version` and `find_current_version` and
loses `delete`; the test seeds move to `create_next_version` (see WU1's note below).

**WU2 — Birth through allocation.** `api/routes/extraction.py` creates the pending row with
`create_next_version(...)` instead of `save(...)`, resolves `temperature` once, writes `provider`,
and drops `temperature` from the `prompt_config` literal. `run_background_extraction` /
`_run_extraction` carry a non-optional `float`.

**WU3 — Render-time snapshot and terminal marks.** `ExtractionService.extract()` becomes
`render()` + `generate()`; the runner persists the rendered prompt and the `prompt_config` keys
before calling the provider; `save` and the terminal rebuilds are replaced by `mark_completed` /
`mark_failed`; `_get_created_at` is deleted; tasks are written with `extraction_id`;
`extract_and_persist` and its nine cases are moved onto the live runner path.

**WU4 — Invalidation storage.** The model lands in WU1 (the drift gate demands table *and* model in
one step); WU4 carries the database-level invariant tests for the mark, the `sqlite_where` mirror
of the partial index, and the cascade/attribution behaviours.

**WU1's note, which the tasks phase must not split.** The new `NOT NULL` columns and
`tasks.extraction_id NOT NULL` break every existing test that inserts an extraction or a task
directly — about twenty `Extraction(...)` sites and about a dozen `Task(...)` sites across
`tests/test_repositories/test_extraction_repo.py`, `tests/test_repositories/test_list_by_workspaces.py`,
`tests/test_repositories/test_task_repo.py`, `tests/test_api/test_extractions.py`,
`tests/test_api/test_extraction.py`, `tests/test_api/test_export.py`, `tests/test_api/test_tasks.py`,
`tests/test_api/test_unfiltered_list_queries.py`, `tests/test_unit/test_extraction_failure_paths.py`
and `tests/integration/test_state_machine_scenarios.py`. Because the SQLite schema in the suite
enforces `NOT NULL` exactly as Postgres does, there is no state in which WU1's models can land
without that rewiring: WU1 is atomic, and it is expected to exceed the 400-line review budget on
its own. The delivery decision remains `ask-on-risk`.

## Architecture Decisions

### Decision: the render step is split from the generate step, and the runner — not the service — owns the write between them

`ExtractionService` keeps two methods and loses its repository dependencies:

```
async def render(story, *, system_prompt, instruction_template, workspace_id, few_shot_config) -> RenderedPrompt
async def generate(rendered: RenderedPrompt, config: LLMConfig) -> tuple[list[ParsedTask], str]
```

`RenderedPrompt` is a frozen, slotted dataclass beside `FewShotConfig` in
`domain/services/extraction_service.py` (that module already owns a domain-side value dataclass):

```
instruction: str                       # what the provider receives as `prompt`
system_prompt: str | None              # what it receives as `system_prompt`
template_variables: dict[str, object]  # exactly the kwargs `render_instruction` was called with
@property text -> str                      # system block + "\n\n" + instruction
```

`text` is the one definition of "the composed text the provider received, system block included"
(the proposal's fact table for `prompt_rendered`), so the column and the call it documents cannot
drift. `template_variables` carries `{"user_story": raw_text}` today and gains
`{"examples": ...}` whenever few-shots were retrieved; slice (c) reads it to fill
`prompt_config.few_shots` / `story_text` and never has to widen the render signature.

The runner performs the write between the two calls, because the runner owns the session and the
service must stay repository-free:

```
rendered = await extraction_service.render(...)
await extraction_repo.record_rendered_prompt(
    extraction_id,
    prompt_rendered=rendered.text,
    prompt_config={"validate": validate, "system_prompt": system_prompt},
)
parsed_tasks, raw_response = await extraction_service.generate(rendered, llm_config)
```

**Why**: the ordering is the requirement. A raised `LLMError` from `generate` must still leave a
version whose input is fully readable (D8 for the failed versions D22 creates), and the only
arrangement that makes that true is a write that has already committed before the provider is
asked. Splitting the two methods also makes the ordering *visible at the call site* instead of
hidden inside `extract()`.

**Tradeoff**: the service loses its repository parameters, so every construction site changes
(`infrastructure/tasks/extraction_task.py:372`, `tests/test_extraction_flow_few_shot.py`,
`tests/test_integration/test_few_shot_rag_qdrant.py`), and the runner grows a second write. The
rejected alternatives carry more: returning the rendered prompt from a still-monolithic `extract()`
loses it on exactly the failure this exists for, and a callback hides the ordering that must hold.

### Decision: `prompt_config` is written wholesale at render time, not merged

The render-time write passes the complete dictionary it wants stored (`validate`, `system_prompt`),
restating `validate` even though the birth insert already wrote it.

**Why**: `prompt_config` is `sa.JSON`, and Postgres has no `||` operator for `json` — only `jsonb`
(proposal step 9 keeps the column type). Any writer of a JSON column therefore replaces the whole
value; the choice is between restating the inherited keys and a read-modify-write. Restating is one
statement; the read-modify-write costs a `SELECT` and opens a lost-update window between the two
writers.

**Tradeoff**: `validate` has two writers (birth, render) rather than one, and the render-time
literal must be kept in step with the birth-time literal. Accepted because both write the same
value from the same request, and because the alternative is a merge that the column type cannot
express.

### Decision: the version number is minted in the row's own `INSERT`, with a bounded retry, and the unique violation is discriminated before the generic error wrap

One statement, no round-trip to read a maximum:

```sql
INSERT INTO extractions (id, user_story_id, model_used, provider, temperature, status,
                         user_story_status, error_info, prompt_config, raw_response,
                         confidence_score, created_at, completed_at, prompt_rendered,
                         version_number)
VALUES (:…, (SELECT COALESCE(MAX(version_number), 0) + 1 FROM extractions
             WHERE user_story_id = :user_story_id))
RETURNING version_number;
```

built with SQLAlchemy as `insert(ExtractionModel).values(**insert_kwargs,
version_number=(select(coalesce(func.max(...), 0) + 1).where(...).scalar_subquery()))`, executed
with `.returning(ExtractionModel.version_number)` and committed. The adapter's insert kwargs come
from a `_to_orm_kwargs` that **omits** `version_number` — the entity does not declare a number on
insert, and ignoring any value it carries is what makes "only this method may ever set it"
structural. The returned number is put back on the entity (`replace(...)`, frozen) and returned.

The retry lives in the adapter, so the port never learns the word "retry":

```
for attempt in range(MAX_ALLOCATION_ATTEMPTS):     # 3, adapter constant
    try:    … execute and commit …
    except IntegrityError as exc:
        await session.rollback()
        if not _is_version_conflict(exc): raise RepositoryError(...) from exc   # do not retry
        continue
    else: return extraction_with_number
raise VersionAllocationConflictError(...)
```

`_is_version_conflict(exc)` reads the driver's own identity for the violation: the asyncpg error's
`constraint_name == "uq_extractions_story_version"` when the attribute is present, and otherwise
the message/column pair (`user_story_id` together with `version_number`) that `sqlite3` reports as
`UNIQUE constraint failed: extractions.user_story_id, extractions.version_number`. Both arms are
implemented, so the retry does not depend on an attribute a driver version may or may not expose;
the Postgres integration test proves the real driver's arm, the unit tests prove the fallback arm.
`VersionAllocationConflictError(RepositoryError)` lands in `domain/entities/exceptions.py`.

Ordering matters: `IntegrityError` is a subclass of `SQLAlchemyError`, and the adapter wraps every
`SQLAlchemyError` into `RepositoryError` (`repositories/extraction_repository.py:25-38`). The
conflict arm is tested **before** that wrap, and every other `IntegrityError` (a null `model_used`,
a `NOT NULL` on `provider`) goes straight to `RepositoryError` on the first attempt instead of
burning three attempts and then reporting a conflict that never happened.

**Why**: the unique index is the concurrency mechanism, and the retry is what turns a lost race
into a success. A single statement keeps "read the maximum" and "insert" in one atomic unit, which
is the only version of this operation that cannot be split by `asyncio.create_task` interleaving.

**Tradeoff**: a caller can hold an `Extraction` carrying a number and be silently given a different
one; the port docstring must say so, and the return value is the only source of the minted number.
`RETURNING` requires SQLite ≥ 3.35 in the unit environment (Postgres has had it far longer) — WU1's
first RED step should print `sqlite3.sqlite_version`; if it is older, the sanctioned fallback is one
extra `SELECT version_number WHERE id = :id` (keyed on the primary key, never on `MAX`, so a
concurrent run cannot be mistaken for this one), which changes no contract.

### Decision: `save` and `delete` leave the extraction port; terminal writes are targeted marks

The port becomes:

```
create_next_version(extraction) -> Extraction
record_rendered_prompt(extraction_id, *, prompt_rendered: str, prompt_config: dict | None) -> None
mark_completed(extraction_id, *, raw_response: str, confidence_score: float | None, completed_at: datetime) -> None
mark_failed(extraction_id, *, error_info: str, completed_at: datetime) -> None
find_by_id(extraction_id) -> Extraction | None
find_current_version(user_story_id) -> Extraction | None
list_page(...) / list()
```

`mark_completed` writes exactly `status='completed'`, `user_story_status='extracted'`,
`raw_response`, `confidence_score`, `completed_at`; `mark_failed` writes exactly `status='failed'`,
`user_story_status='failed_extraction'`, `error_info`, `completed_at`. `version_number`, `provider`,
`temperature`, `prompt_rendered`, `prompt_config`, `model_used`, `created_at`, `raw_response` (in
the failure arm) and the id are **absent from those statements** — not preserved by convention, but
unreachable, because no statement names them. The status pair is hardcoded in the adapter because
`ExtractionStatus.COMPLETED` and `UserStoryStatus.EXTRACTED` move together and no caller may pair
them differently. Both mark methods raise `EntityNotFound` when no row matched, which is the
behaviour `delete` used to carry. `completed_at` is passed in by the call site, keeping the rule the
entity already documents.

**Why**: the failure mode is silent data loss. `save()` reads the row and `setattr`s every field
from the entity (`repositories/extraction_repository.py:25-32,156-165`), and the terminal paths
rebuild a fresh `Extraction(...)` from a partially populated row (`extraction_task.py:429-446`,
`:500-510`, `:594-604`, the recovery sweep at `:194-203`) — so `None` written over
`version_number`, `provider`, `temperature` and `prompt_rendered` would be invisible: no error, no
failed request, just a version that forgot itself. Removing the method removes the possibility, not
just the occurrence.

**Tradeoff**: the test suite loses its `save()`-based seeding and must go through
`create_next_version` (plus a builder in `tests/_helpers.py`, whose docstring already scopes it to
low-level builders); `save()`'s upsert branch was also the only thing that let a test seed an
arbitrary state in one call, so a few seeds become two (`create_next_version` then a mark). The
rejected alternatives — a "whole-snapshot" `save(mutated)` at the call sites, or a
`_SNAPSHOT_FIELDS` allowlist inside the existing upsert — keep a method whose name promises more
than the schema allows, and leave the next writer free to repeat the bug.

### Decision: domain shape — required `provider`/`temperature`, optional `version_number`/`prompt_rendered`, `extraction_id` on tasks

| Field | Domain | Column |
| --- | --- | --- |
| `Extraction.provider: str` | required | `VARCHAR(50) NOT NULL` |
| `Extraction.temperature: float` | required | `DOUBLE PRECISION NOT NULL` |
| `Extraction.version_number: int \| None = None` | optional | `INTEGER NOT NULL` |
| `Extraction.prompt_rendered: str \| None = None` | optional | `TEXT NULL` |
| `Task.extraction_id: UUID \| None = None` | optional | `UUID NOT NULL` |

Required fields are inserted before the defaulted ones in the frozen dataclass (after
`raw_response`), because a field without a default cannot follow one.

`provider` stays a `str`, not an enum: `infrastructure/llm/__init__.py` treats `"ollama"`,
`"gemini"`, `"openai"` and `"anthropic"` as the known adapters and every other name as a
workspace-defined OpenAI-compatible provider, so the vocabulary is open by design. The column is
wide enough by construction: the value is the workspace's own `provider`
(`workspace_llm_configs.provider` is also `String(50)`), so the copy cannot overflow.

`Task.extraction_id` is set at the single construction site inside the runner
(`extraction_task.py:450-456`); `tasks.user_story_id` stays, so the story-level access link is
unchanged.

**Why**: a default for `provider` or `temperature` would let a row be born with a provider nobody
configured, and `NOT NULL` cannot tell that apart from a real value — an empty string is a lie the
database would accept. Making them required puts the failure at the type, at the earliest possible
moment. `version_number` and `prompt_rendered` are optional for reasons the proposal states:
`None` means "not yet minted" and "never rendered" respectively, both honest answers.

**Tradeoff**: ~20 test extraction seeds and the mock-based constructions in
`tests/integration/test_state_machine_scenarios.py` must supply the two new values (one shared
builder absorbs most of it), and the manual `POST /api/v1/tasks/` route can no longer insert: its
`Task(user_story_id=..., title=...)` now reaches a `NOT NULL` column and answers 500 through
`repository_error_handler` (`api/errors.py:143-158`). That is the proposal's own accepted
consequence ("left untouched for (b) to retire, no user is exposed because (a) is not deployed"),
and it is pinned by test rather than left to be discovered; the tests at `tests/test_api/test_tasks.py:42`
and `:67`, which assert 201 today, change to pin the refusal.

> **[Premise of that acceptance expired the day (a) shipped, 2026-09-30.]** The accepted consequence
> relied on "(a) is not deployed". (a) is deployed (`1dcc716`, deploy `36675276096`), so production now
> publishes `POST /api/v1/tasks/` as `201 Successful Response` in its live `openapi.json`, with `/docs`
> answering `200`, while the route itself answers 500 `REPOSITORY_ERROR`. Two accidental facts keep the
> exposure at zero today: no frontend client calls it (`tasks-api.ts` has no create-task function), and
> `users` is empty after the D-a-3 purge. Neither is a design guarantee. Tracked in `prod.todo.md`
> ("Contratos de API que mienten en producción"), to be closed by slice (b) WU1's `410 Gone` retirement
> before any evaluator has an account.

### Decision: the invalidation mark is a table with two `CHECK`s and a partial unique index; blank reasons are a database invariant

`task_invalidations`: `id` (pk), `task_id` (FK → `tasks.id`, `ON DELETE CASCADE`), `reason`
`VARCHAR(500) NOT NULL`, `marked_by` / `revoked_by` (`UUID NULL`, FK → `users.id`,
`ON DELETE SET NULL`), `marked_at` `TIMESTAMPTZ NOT NULL`, `revoked_at` `TIMESTAMPTZ NULL`, plus

> **[Superseded 2026-09-30, task 4.4 / D-a-2, Option A chosen by the owner.]** `revoked_by` ships as
> `ON DELETE RESTRICT`, not `SET NULL`. Postgres re-evaluates `CHECK ((revoked_by IS NULL) =
> (revoked_at IS NULL))` during the referential action, so the `SET NULL` planned here fails anyway
> whenever `revoked_at` is set; `RESTRICT` names the constraint that actually holds the invariant, and
> leaves the equivalence CHECK intact. `marked_by` stays `SET NULL`, as written above. The normative text
> is `specs/task-invalidation/spec.md`, "Actor References Survive Account Deletion".

```
CHECK (length(trim(reason)) > 0)                       -- ck_task_invalidations_reason_not_blank
CHECK ((revoked_by IS NULL) = (revoked_at IS NULL))    -- ck_task_invalidations_revoke_pair
CREATE UNIQUE INDEX uq_task_invalidations_active_task
    ON task_invalidations (task_id) WHERE revoked_at IS NULL
INDEX ix_task_invalidations_task_id (task_id)
```

Both `CHECK` expressions are dialect-portable on purpose: the model declares the same two, and
`create_all` builds the SQLite test schema from them, so the blank-reason and revoke-pair
invariants are testable without Docker. The partial index is declared with `postgresql_where` **and**
`sqlite_where` (`revoked_at IS NULL` in both). The migration creates the Postgres one.

**Why**: the reason rule is not a UI rule — D6 asks for a mark that cannot exist without a reason,
and a `Pydantic` validator on a marks endpoint (slice (b)) cannot protect the table from a psql
session, a script or a future caller. Attributions follow the repo's existing convention for
`projects.created_by` (`0014_add_cascade_deletes.py`), so the mark and its reason survive account
deletion and only the actor reference is nulled. One partial index, not two columns: the revoke
history is the record the requirement asks for. `length(trim(reason)) > 0` is exactly "the trimmed
reason is not empty" and avoids `btrim`, which SQLite does not have — a model-level `CHECK` SQLite
cannot parse would break every `create_all` in the suite.

**Tradeoff**: a reason made only of tabs or newlines satisfies the check (SQL `trim()` strips
spaces), so the database backstop covers the realistic empty case and slice (b)'s validator, which
strips all Python whitespace, covers the rest — recorded rather than papered over. `sqlite_where`
is a test-schema mirror, not a production concern; without it, SQLite would build a *full* unique
index on `task_id` and forbid the revoke-then-re-mark history the table exists for. And because
`task_id` cascades, a revoked row dies with its task when the story-delete gate (D15) removes the
version — the only deletion path, and the one D12 sanctions.

### Decision: `0028` reads row counts through `op.get_bind()` before any DDL, and its whole surface lands in one revision

```python
def upgrade() -> None:
    bind = op.get_bind()
    extractions = bind.execute(sa.text("SELECT count(*) FROM extractions")).scalar_one()
    tasks = bind.execute(sa.text("SELECT count(*) FROM tasks")).scalar_one()
    if extractions or tasks:
        raise RuntimeError(f"0028 refuses to run: …{extractions} extraction row(s), {tasks} task row(s)…")
    # DDL, in this order:
    #   extractions: add version_number, provider, temperature, prompt_rendered
    #                → ck_extractions_version_number_positive
    #                → uq_extractions_story_version
    #   tasks:       add extraction_id → fk_tasks_extraction_id_extractions (CASCADE)
    #                → ix_tasks_extraction_id
    #   task_invalidations: create_table (PK, three FKs, two CHECKs)
    #                → ix_task_invalidations_task_id
    #                → uq_task_invalidations_active_task (partial, postgresql_where)
```

The guard is two plain `SELECT count(*)`s over table names, executed on the migration's own
connection. It imports no ORM model and no metadata, so it can never depend on what the models look
like today — the migration only needs the two tables to exist, which `0001` guarantees at that
point in the chain. Constraint names are written already-expanded and wrapped in `op.f(...)`
(`fk_tasks_extraction_id_extractions`, `ix_tasks_extraction_id`,
`ck_task_invalidations_reason_not_blank`, …) so the naming convention in `models/base.py` cannot
double-expand them; the ORM side declares the short names and lets the convention produce the same
strings, which is what keeps `uq_extractions_story_version` and `ix_tasks_extraction_id`
drift-free.

`downgrade()` reverses exactly that list, in reverse: drop both `task_invalidations` indexes and the
table, then `ix_tasks_extraction_id`, the FK, `tasks.extraction_id`, then
`uq_extractions_story_version`, `ck_extractions_version_number_positive` and the four extraction
columns. Its boundary: it restores the pre-`0028` schema and does **not** re-run the guard (a drop
is safe on a populated database), and it does not attempt to keep data — which is lossless in every
state `0028` can actually be in, since the migration only ever ran on an empty pair of tables. The
`tasks`→`extractions` FK is added after the column and before the index, and no other revision is
in flight to claim `0028`.

**Why**: the guard has to run before the first `add_column`, or the operator meets a Postgres
`NOT NULL` error instead of the sentence naming D11. Reading counts with raw SQL keeps the
migration honest about the schema it faces, and one revision for the whole surface keeps rollback
single-step (the proposal's rollback plan).

**Tradeoff**: `0028` is Postgres-only in the executable sense. SQLite cannot `ADD COLUMN … NOT
NULL` without a default, so the unit suite can prove the *refusal* path (which raises before any
DDL) and nothing after it; the empty-database path, the DDL and the downgrade are proven against the
Postgres container that `tests/test_integration/test_migration_chain.py` already runs. The rejected
alternative — `batch_alter_table` so the whole revision runs on SQLite — buys a portability the
suite does not need and would rebuild `tasks` (recreating its FKs) on the strength of a test-only
convenience.

### Decision: `temperature` has one literal, resolved once by the route

`DEFAULT_TEMPERATURE: float = 0.1` lives in `domain/ports/llm_port.py` beside `LLMConfig`, whose
`temperature` field default becomes that constant. The route resolves
`body.temperature if body.temperature is not None else DEFAULT_TEMPERATURE`, writes it to the new
column and passes the same value to `run_background_extraction`. `_run_extraction`'s parameter
becomes `float` (no `None`, no `if…else`), so `LLMConfig(temperature=temperature)` is
unconditional; the public wrapper's default is the constant.

**Why**: the requirement is that the declared temperature equals the temperature used. Today the
`0.1` fallback exists only inside the runner (`extraction_task.py`'s `LLMConfig(...)` in
`_run_extraction`) while the column would be written from `body.temperature` — two sources for one
fact, which is exactly the drift the requirement forbids.

**Tradeoff**: the wrapper keeps a default for callers that do not pass one (`run_background_extraction`
is called without `temperature=` in tests at `tests/test_api/test_extraction.py:212`, `:274` and
`:339`), so a future internal caller could still run at the default without declaring it. The
literal is single and the product path always passes it explicitly, which is what the requirement
asks for; a required parameter would have forced unrelated test edits for no stronger guarantee.

### Decision: `find_current_version` exists in slice (a), with no product caller yet

`ORDER BY version_number DESC WHERE user_story_id = :id AND status = 'completed' LIMIT 1` on the
port, served by `uq_extractions_story_version`, returning `Extraction | None`.

**Why**: D4's whole content is that "current" is derived rather than stored, and the migration
scenario that checks no flag/trigger/matview exists says nothing about whether derivation *works*.
The read belongs to the slice that owns the rule; slice (b) then only filters HTTP reads with it.

**Tradeoff**: a port method with no production caller in (a) — the kind of surface the repo
otherwise refuses to add. Accepted because the alternative is that D4 ships unproven and (b) writes
the query in a layer that does not own the rule. `list_page` is deliberately **not** filtered by it:
the current-version filter is an HTTP reading decision and stays in (b), as the proposal's
"Not independently deployable" note states.

### Decision: the dead persistence path is deleted, and its cases move to the live runner path

`ExtractionService.extract_and_persist` (`domain/services/extraction_service.py:224`) is deleted.
Its only callers are nine cases in `tests/test_services/test_extraction_service.py`
(`test_extract_and_persist_full_pipeline`, `..._saves_tasks`, `test_extract_llm_error_persists_failed`,
the parse-error case, `..._failed_extraction_still_saved`, `..._with_judge`,
`..._judge_failure_does_not_break`, `..._stores_in_vector_store`, `..._vector_store_fails`). Each
assertion is re-pointed at the live path (`run_background_extraction` with the engine and adapters
monkeypatched, the pattern `tests/test_api/test_extraction.py` already uses for both the failure and
the `completed_at` cases): "persists an extraction" becomes "the row the runner completes carries
these outputs", and the judge/vector-store cases keep their subject by asserting on the row and on
the recording fake. The stale comment in `tests/test_integration/test_few_shot_rag_qdrant.py:222-226`
("``extract`` never touches the repositories — only ``extract_and_persist`` does") is rewritten with
the new shape.

**Why**: it creates a fresh row per call, so a second birth path can mint two numbers for one run —
the ambiguity D22 cannot afford. Teaching it the allocation rule would mean two implementations of
one lifecycle rule.

**Tradeoff**: the cases lose the fast mock-only shape (`extraction_repo`/`task_repo` mocks) and
become runner-level tests with a session, which is slower and touches more of the stack. That is the
cost of asserting on the path production takes; the alternative is coverage of code that no longer
exists.

## Data Flow

**Birth.** `POST /workspaces/{id}/extract/` → authorization, workspace prompt/LLM config resolved →
`missing_llm_config_fields(...)` refuses an incomplete config before anything is created →
`temperature` resolved once → `Extraction(user_story_id, model_used, raw_response="",
provider=<workspace provider>, temperature=<resolved>, status=PENDING,
user_story_status=PENDING_EXTRACTION, prompt_config={"validate": ...})` →
`create_next_version(...)` inserts it and returns it with `version_number` → 202 with the
extraction id → `asyncio.create_task(run_background_extraction(..., temperature=<resolved>, ...))`.

**Run.** The runner (its own session) loads the story, moves it to `EXTRACTING`, builds the adapter
from the workspace config, and then, in order: `render()` (RAG examples retrieved here) →
`record_rendered_prompt(...)` commits `prompt_rendered` + `prompt_config` → `generate()` (the only
provider call) → optional judge → `mark_completed(...)`, or on any failure `mark_failed(...)` — both
single `UPDATE`s that cannot name a snapshot column. Tasks are written once each with
`extraction_id`. `_store_rag` is untouched (slice (c) owns the payload).

**Concurrency.** Two runs on one story both compute the same number; the unique constraint decides,
the loser rolls back, recomputes inside a fresh transaction and inserts `max + 1`. After three
attempts the request fails loudly with `VersionAllocationConflictError`, which currently reaches the
generic `repository_error_handler` (500, `REPOSITORY_ERROR`).

## Interfaces / Contracts

```
# domain/ports/extraction_repository.py  (port — the domain never sees retry, SQL or driver errors)
create_next_version(extraction: Extraction) -> Extraction
record_rendered_prompt(extraction_id, *, prompt_rendered: str, prompt_config: dict | None) -> None
mark_completed(extraction_id, *, raw_response: str, confidence_score: float | None, completed_at: datetime) -> None
mark_failed(extraction_id, *, error_info: str, completed_at: datetime) -> None
find_current_version(user_story_id: UUID) -> Extraction | None
# removed: save(), delete()

# domain/services/extraction_service.py
RenderedPrompt(instruction, system_prompt, template_variables)          # .text = system + "\n\n" + instruction
ExtractionService(...)                                                  # no extraction_repo / task_repo
async render(...) -> RenderedPrompt
async generate(rendered, config) -> tuple[list[ParsedTask], str]

# domain/entities/exceptions.py
VersionAllocationConflictError(RepositoryError)                         # slice (b) maps it to an HTTP status

# api/routes/extraction.py
pending = await extraction_repo.create_next_version(Extraction(..., provider=provider,
                                                    temperature=resolved_temperature, ...))

# infra: the whole column set each writer may name
record_rendered_prompt -> {prompt_rendered, prompt_config}
mark_completed         -> {status, user_story_status, raw_response, confidence_score, completed_at}
mark_failed            -> {status, user_story_status, error_info, completed_at}
create_next_version    -> everything except version_number, which the statement computes
```

## File Changes

| Path | Work unit | Change |
| --- | --- | --- |
| `infrastructure/database/alembic/versions/0028_extraction_versioning.py` | WU1 | New: guard, four columns, unique constraint, CHECK, `tasks.extraction_id` + FK + index, `task_invalidations`, `downgrade()` |
| `infrastructure/database/models/extraction.py` | WU1 | `version_number`, `provider`, `temperature`, `prompt_rendered`, unique constraint, positive-version CHECK |
| `infrastructure/database/models/task.py` | WU1 | `extraction_id` FK + `ix_tasks_extraction_id` |
| `infrastructure/database/models/task_invalidation.py` | WU1 | New model: partial unique index (`postgresql_where` + `sqlite_where`), two CHECKs, three FKs |
| `infrastructure/database/models/__init__.py` | WU1 | Register the new model (the drift test compares models ↔ migrated schema) |
| `domain/entities/extraction.py` | WU1 | Four fields, with the field-order constraint above |
| `domain/entities/task.py` | WU1 | `extraction_id: UUID \| None = None` |
| `domain/ports/extraction_repository.py` | WU1 | New methods; `save`/`delete` removed |
| `infrastructure/database/repositories/extraction_repository.py` | WU1 | Allocation + retry + discrimination, marks, rendered-prompt write, current-version read; `_to_orm_kwargs` stops carrying `version_number`; `save`/`delete` gone |
| `infrastructure/database/repositories/task_repository.py` | WU1 | `extraction_id` through `_to_orm_kwargs`/`_to_domain` |
| `domain/entities/exceptions.py` | WU1 | `VersionAllocationConflictError` |
| `api/routes/extraction.py` | WU2 | Birth via `create_next_version`; `provider` and resolved `temperature` written; `temperature` dropped from `prompt_config` |
| `infrastructure/tasks/extraction_task.py` | WU3 | Render/generate split, render-time write, marks, `_get_created_at` deleted, `extraction_id` on tasks, `extract_and_persist` call sites rewired |
| `domain/services/extraction_service.py` | WU3 | `render`/`generate`, `RenderedPrompt`; `extract_and_persist` deleted; repository parameters removed |
| `tests/_helpers.py` | WU1 | Extraction/task builders that go through `create_next_version` |
| `tests/**` (seeds) | WU1 | ~20 extraction seeds and ~12 task seeds move off `save`/untargeted `Task(...)` |
| `tests/test_unit/test_extraction_versioning_migration.py` | WU1 | New: refusal before DDL, revision metadata |
| `tests/test_repositories/test_extraction_repo.py` | WU1 | Allocation numbering, conflict handling, marks, `find_current_version`, seeds |
| `tests/test_unit/test_extraction_failure_paths.py` | WU3 | Failure keeps the snapshot (the regression test) |
| `tests/test_api/test_extraction.py` | WU2/WU3 | Birth writes the columns; two runs mint 1 and 2; manual-route refusal in `test_tasks.py` |
| `tests/test_integration/test_extraction_versioning_schema.py` | WU1/WU4 | New: Postgres-level invariants (guard with real rows, constraints, partial index, cascades, no flag, real collision) |

## Testing Strategy

STRICT TDD, in the config's order (RED → GREEN → TRIANGULATE → REFACTOR). Every invariant below
gets its failing test first; the work unit does not close until the whole suite is green.

Two layers, because some invariants only exist in a database:

- **Unit / SQLite** (the schema comes from the models, so the new constraints are present):
  `cd backend && conda run -n storico python -m pytest -m "not integration"`
- **Integration / Postgres 16** (testcontainers, `@pytest.mark.integration` per test, skipped when
  the Docker daemon is unreachable — the convention of `tests/test_integration/test_migration_chain.py`):
  `cd backend && conda run -n storico python -m pytest -m integration`
- Whole suite, the acceptance gate: `cd backend && conda run -n storico python -m pytest`

| Requirement (spec scenario) | Test | Home | Layer |
| --- | --- | --- | --- |
| One Version Per Run, Numbered Per Story — three runs | Three `create_next_version` calls on one story yield 1, 2, 3 | `test_repositories/test_extraction_repo.py` | Unit |
| … — duplicate number impossible | Raw insert of an existing `(story, version)` raises `IntegrityError` | `test_integration/test_extraction_versioning_schema.py` | Integration |
| … — number never reused | After 1 and 2 exist, the next is 3 (no counter reset) | `test_repositories/test_extraction_repo.py` | Unit |
| Every Run Consumes a Number — failed run keeps it, never current | Failed row keeps `version_number`; `find_current_version` skips it | `test_repositories/test_extraction_repo.py` | Unit |
| … — retry never mints a second number | `run_background_extraction` retry path leaves exactly one row per run and one number | `test_api/test_extraction.py` | Unit |
| Current Version Derived, Never Stored — no flag | `information_schema.columns`, `pg_trigger`, `pg_matviews` show no `is_current`/trigger/view on `extractions` | `test_integration/test_extraction_versioning_schema.py` | Integration |
| … — pending leaves the previous current | Pending v3 on top of completed v2 → current is v2 | `test_repositories/test_extraction_repo.py` | Unit |
| … — failed top is never current | Completed v1 + failed v2 → current is v1 | `test_repositories/test_extraction_repo.py` | Unit |
| Concurrent Runs Receive Distinct Numbers — no collision | Two `asyncio.gather`ed allocations on one story: two distinct numbers, two rows | `test_integration/test_extraction_versioning_schema.py` | Integration |
| … — bounded retry then loud failure | Real collision: an uncommitted competing insert blocks the allocation; committing it fails the first attempt and the retry mints the next number | `test_integration/test_extraction_versioning_schema.py` | Integration |
| … — bound and discrimination pinned | `_is_version_conflict` true for the version violation (asyncpg-shaped and sqlite-shaped errors), false for a `NOT NULL` violation; a forced conflict on every attempt stops after 3 and raises `VersionAllocationConflictError` | `test_repositories/test_extraction_repo.py` | Unit |
| Every Extracted Task Belongs to Its Extraction | Tasks written by a run carry its `extraction_id`; a v2 run produces new task rows, v1's remain | `test_api/test_extraction.py` | Unit |
| … — `NOT NULL` | Direct insert with a null `extraction_id` is refused | `test_integration/test_extraction_versioning_schema.py` | Integration |
| Each Version Freezes Its Run Snapshot — failed version complete, output absent | `render` succeeds, `generate` raises `LLMError` → `prompt_rendered`, `system_prompt`, `provider`, `temperature`, `version_number` present, `raw_response == ""`, no confidence | `test_unit/test_extraction_failure_paths.py` | Unit |
| … — `prompt_rendered` null only when never rendered | A run that dies before render keeps `NULL`; nothing backfills it | `test_unit/test_extraction_failure_paths.py` | Unit |
| … — terminal writes preserve the snapshot (the regression test) | After a failed run and after a completed run, every snapshot column still holds its birth/render value | `test_unit/test_extraction_failure_paths.py` | Unit |
| … — declared temperature equals the temperature used | The route's resolved value is the column value and the `LLMConfig` the adapter received | `test_api/test_extraction.py` | Unit |
| Nothing Inside a Version Is Ever Deleted — no product path | No `delete` on the extraction port; the route/runner/recovery paths contain no delete call | `test_repositories/test_extraction_repo.py` (import/shape) + the port's own tests | Unit |
| … — the only deletion is the story cascade | Deleting the story removes its extractions and the tasks of those runs, and nothing else | `test_integration/test_extraction_versioning_schema.py` | Integration |
| The Migration Refuses Legacy Data — populated database | Guard raises before any DDL and leaves the pre-`0028` schema untouched | `test_unit/test_extraction_versioning_migration.py` (SQLite) and the populated-Postgres case (`upgrade` to `0027`, insert, `upgrade head`) | Unit + Integration |
| … — applies on an empty database | The chain reaches `0028` on an empty database and the head matches the scripts | `test_integration/test_migration_chain.py` (existing) | Integration |
| The Mark Is a Row in `task_invalidations` | Insert a mark; read it back; `tasks` has no invalidation columns | `test_integration/test_extraction_versioning_schema.py` + WU4 unit tests | Unit + Integration |
| The Reason Is Mandatory | Empty and space-only reasons are refused; a bounded reason round-trips verbatim | WU4 (SQLite `CHECK` is the same expression) | Unit |
| At Most One Active Mark | Second active mark refused; revoke then re-mark succeeds and the first row is still there | WU4 | Unit (+ Integration for the partial index shape) |
| Revoking Is an Update, Never a Delete | Revoke sets `revoked_by`/`revoked_at` on the same row and leaves `reason`, `marked_by`, `marked_at` | WU4 | Unit |
| Actor References Survive Account Deletion | Deleting the marking user nulls `marked_by` only; deleting the revoking user keeps `revoked_at` | `test_integration/test_extraction_versioning_schema.py` (needs the real FK action) | Integration |
| The Mark Belongs to the Version It Was Made On | Joining the mark through `tasks.extraction_id` resolves to v2 only; a v2 task with the same title carries no mark | WU4 | Unit |

The retry path is covered in halves on purpose: the *outcome* of a real collision is proven against
Postgres with an uncommitted competitor (the only deterministic provocation — the race window lives
inside one server-side statement, so a timing-based test would be flaky), and the *bound and
discrimination* are proven by pure unit tests. Nothing asserts "three real collisions", which is not
reachable deterministically. Integration tests skip without a Docker daemon, so the mobile/laptop
state is: the DB-level half of `0028` and every Postgres-only invariant is unverified — recorded
here, not discovered later.

## Threat Matrix

| Threat | Mitigation | Pinned by |
| --- | --- | --- |
| Terminal rebuild silently nulls a snapshot column | The port has no whole-row writer; the mark statements cannot name snapshot columns | The failure-keeps-the-snapshot regression test |
| A second birth path mints a second number for one run | `extract_and_persist` deleted; retry reuses the same id and writes outputs only | Migrated cases in `test_services/test_extraction_service.py` + the retry case |
| Concurrent runs collide | Unique constraint + three attempts + rollback before recompute | Collision tests (unit halves, Postgres outcome) |
| A genuine database error is misread as a version conflict | `IntegrityError` is discriminated before the `SQLAlchemyError` wrap; non-conflicts raise immediately | Discrimination unit test |
| A retry loop hides a persistent fault | Bounded at three, then `VersionAllocationConflictError` (a distinct type (b) can map) | Bound test |
| `prompt_rendered` lost because the provider failed | The render-time write commits before `generate` is called | Failed-snapshot test |
| `0028` meets data and half-migrates | The guard runs before the first DDL, in the same transaction | Refusal test (unit) + populated-database test (integration) |
| SQLite and Postgres diverge on a constraint | Both `CHECK`s are portable and mirrored on the model; the partial index is mirrored with `sqlite_where`; the Postgres-only behaviours are integration-marked | Per-requirement table above |
| A migration/model mismatch ships | The drift gate in `test_migration_chain.py` compares the migrated schema to the models | Existing integration test (its difference set is an empty frozenset) |
| Auto-generated CHECK constraints are not compared | The model's `CHECK` text and the migration's are identical by construction, written once as a literal per site | Review; no automatic gate exists — recorded deliberately |
| The manual task route answers 500 | Accepted for (a); pinned so it cannot be mistaken for a working path; slice (b) retires the route | `tests/test_api/test_tasks.py` |

## Migration / Rollout

1. The D11 wipe (relational data + `storico_extractions_dev` / `storico_extractions_prod`) runs as
   its own confirmed operation **before** the deploy that carries `0028`. It is not an Alembic step.
2. Deploy runs `alembic upgrade head` inside the maintenance window between `docker stop` and
   `docker run` (ADR-005). `0028` is the first revision in the chain that *refuses* rather than
   migrates: an environment that still holds rows fails the deploy loudly and keeps running the
   previous release, which is the intended answer.
3. **(a) must not be deployed alone.** Board, export and `GET /tasks` still read tasks by
   `user_story_id` until (b) applies the current-version filter, so a second run on a story would
   show both task sets. (a) and (b) ship in one release.
4. Rollback is `alembic downgrade 0027` plus the code revert. `downgrade()` drops version identity
   (destructive, acceptable only while no production extraction history exists — true by D11). The
   wipe itself is not reversible.
5. No Qdrant change, no new setting, no new endpoint in this slice.

## Seams for Slices (b) and (c)

**Slice (b).**
- *Exhausted allocation retry*: `VersionAllocationConflictError` arrives today at
  `repository_error_handler` (500). (b) registers its own handler before that one — FastAPI matches
  handlers by class, and a subclass needs its own registration to win — and picks the status
  (409 with a retry hint, or 503).
- *Current-version filter on reads*: `find_current_version(user_story_id)` is the mechanism; (b)
  applies it in `GET /tasks`, board and export, and exposes the selector from
  `list_page(user_story_id=...)`.
- *Marks endpoints*: `task_invalidations` is storage only here. (b) writes the domain entity, the
  repository port (create / revoke / read history), the owner-or-`ADMIN` gate, the `410 Gone` for
  `DELETE /tasks/{id}`, and the `Pydantic` reason validator that strips all whitespace (the residual
  the database `CHECK` does not cover).
- *Manual task creation*: retire `POST /api/v1/tasks/` together with the two tests that pin its
  refusal.
- *Version in the response*: `ExtractionResponse`/`ExtractResponse` (`api/schemas/extraction.py`) do
  not carry `version_number`, `provider` or `temperature`; adding them is (b)'s contract.

**Slice (c).**
- *Snapshot key content*: `RenderedPrompt.template_variables` is the only seam needed **on the
  output side** — it is what carries the keys into the render-time write. (c) writes
  `prompt_config.few_shots`, `project_context`, `story_text`, `negative_examples_omitted` (render
  time) and `usage` (after the provider answers) into the same render-time write, without changing
  the runner's ordering. Corrected 2026-09-28 after slice (c) was proposed: this paragraph claimed
  (c) needed no change to `render()`'s **signature** at all, and that is wrong in one direction. The
  input side does widen — the project context of D9 comes from repositories, the service stays
  repository-free, so the runner must hand it in as one new keyword-only argument (see
  `extraction-versioning-prompt/proposal.md`, Approach 3). The rejected readings of my own sentence
  were worse: the service holding repository ports, the runner bypassing `render()` to compose the
  prompt itself, or Python-filtering the paginated reads. What this slice guarantees is the write
  **moment**, not a frozen parameter list.
- *Qdrant `has_invalid_tasks`*: `_store_rag` is untouched by this slice; the payload key arrives with
  the mark read path (b) and the payload signature (c).
- *Prompt context blocks*: the two unpaginated context ports and the token-usage capture are (c)'s;
  nothing in (a) reaches the provider with more context than it does today except that the resolved
  system prompt is now also persisted.

## Open Questions

None. Every shape the proposal left open is settled above — the render/generate split, the write
between the calls, the allocation statement and its retry, the fate of `save`/`delete`, the domain
nullability, the mark table's constraints, `0028`'s ordering and downgrade boundary, and the two
slices' seams. Two items are decided *with a contingency* rather than left open: the `RETURNING`
clause (fallback: a by-primary-key re-read, if the unit environment's SQLite predates 3.35) and the
HTTP status of an exhausted allocation (slice (b)'s call, which is why the exception type — not the
status code — is what this slice guarantees).
