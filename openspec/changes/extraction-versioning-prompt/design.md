# Design: Extraction Versioning — Prompt Context, Snapshot Content and Few-Shot Exclusions

> **Change**: `extraction-versioning-prompt`
> **Status**: `design`
> **Based on**: `proposal.md`, the four `specs/` deltas, `explore.md`, and the two sibling slices
> (`../archive/2026-09-30-extraction-versioning-schema/explore.md`, `../archive/2026-09-30-extraction-versioning-schema/design.md`,
> `../extraction-versioning-api/design.md`)
> **Created**: 2026-09-28

Slice (c) of three. It owns what the provider receives and what each version records about having
received it: **D8**'s snapshot *content*, **D9**'s project context, **D7/D19**'s negative examples,
**D10**'s two few-shot exclusions and three payload keys, **D20**'s measurement with no new
instrument, and **D23**'s two unpaginated context ports.

Measured starting point: `main` `ecea3e2`. Slices (a) and (b) are **artifacts only** — no migration
`0028`, no `RenderedPrompt`, no `task_invalidations`, no `search_similar` change exists in code. Every
(a)/(b) mechanism this design consumes is therefore cited to those changes' artifacts, not to code.
The three slices ship in one release.

The spine of the design is three sentences. **The runner reads the context and hands it to `render()`
as one value, so the service stays repository-free and the snapshot is filled from
`RenderedPrompt.template_variables` in the write (a) already owns.** **Both new prompt blocks and
both new reads are composed from data the project already holds — no new store, no cache, no
instrument.** **Few-shot retrieval loses both excluded classes inside the Qdrant filter, and the
validity condition is a positive `must` on `false` so a point that merely lacks the key is never
admitted.**

The D-numbered decisions (D7, D8, D9, D10, D12, D19, D20, D22, D23, C5, C9) are **reproduced, not
reopened**. Where the proposal's or the source spec's *wording* is looser than the requirement it
carries, this design says so and follows the requirement — four such reconciliations are marked
**(correction)** below.

## Technical Approach

Ordered work. WU1–WU4 are the review slices the tasks phase should keep together; each is
behaviour-shaped, carries its own tests, and ends on a green suite (`cd backend && conda run -n
storico python -m pytest`).

**WU1 — The project enters the prompt.** `ProjectContext` and its row types; the two D23 ports and
their repository implementations plus the third read for the project's name and description; the
`context` keyword-only argument on `render()`; the five entries in `template_variables`; the
`## Project Context` and negative-example blocks in `task_generation.j2`. The negative block's markup
ships here but is empty until WU2 wires the marks read, which is why **D7's requirement belongs to
WU2**, not WU1. Ends green with the context block asserted on a rendered prompt and the exclusion
asserted at the repository.

**WU2 — What the version records.** `domain/services/negative_examples.py` (the composer, the cap,
the dedup through (b)'s normalizer); the marks read that feeds it; the runner's snapshot dictionary
and its render-time write; `LLMResponse` on the port, `usage` on `ExtractionResult`, the four
adapters' parse sites; `record_usage` on the extraction port; the `.text` ripple through the judge
service and the five settings probes. Ends green with a failed run that keeps a complete snapshot and
lacks only `usage`.

**WU3 — Few-shot exclusions and the mark's vector consequence.** `search_similar`'s signature and
filter; the three payload keys; the payload indexes; `set_has_invalid_tasks` on the port and its
`set_payload` implementation; `count_active_for_extraction` in (b)'s invalidation repository; the
refresh calls in (b)'s two mark handlers; `_store_rag`'s two new arguments. Ends green with the
filter asserted against a fake client and the mark/revoke refresh asserted at the API layer.

**WU4 — The two benches and the record.** `openspec/changes/extraction-versioning-prompt/
verify-report.md` with the 1 / 50 / 200 ladder, the mandatory 1000-story CSV-import run, the
per-provider `usage` confirmation table, and the outcome each run actually landed in. No source file
changes.

**Review workload.** WU1 (two ports + two repositories + a template + the service + the runner) and
WU3 (the vector port, adapter, payload, refresh and (b)'s handler order) are the two that can each
approach or cross the 400-line budget on their own. The delivery decision stays with `ask-on-risk`:
on budget risk, stop and ask — no chain strategy is preselected. WU1 and WU3 are the natural split
points if a pause is needed, and neither leaves the repo incoherent on its own.

## Architecture Decisions

### Decision: the context reaches the prompt as one runner-built value, passed as the single keyword-only `context` argument on `render()`

`ProjectContext` is a frozen slotted dataclass beside `FewShotConfig` in
`domain/services/extraction_service.py` — the module that already owns a domain-side value
dataclass, `FewShotConfig` at `extraction_service.py:32-40`:

```python
@dataclass(frozen=True, slots=True)
class ProjectContext:
    name: str                                     # project name at render time
    description: str                              # description at render time
    other_stories: tuple[StoryContextRow, ...]    # the project's OTHER stories, id + raw_text
    existing_tasks: tuple[TaskContextRow, ...]    # current-version, valid tasks only
    negative_examples: tuple[NegativeExample, ...] = ()   # D7/D19, composed by WU2
    negative_examples_omitted: int = 0

    def as_template_variables(self) -> dict[str, object]: ...  # the four-key `project_context`
```

It is **built by the runner** (`infrastructure/tasks/extraction_task.py::_run_extraction`, which
already owns the session, the story load (`story_repo.find_by_id(story_id)`, `extraction_task.py:312`)
and the repositories), between the
story load and the `render()` call, from exactly four reads (the two ports, the project row, and
(b)'s marks read). It is consumed by `render()` as:

```python
async def render(self, story, *, system_prompt, instruction_template, workspace_id,
                 few_shot_config, context: ProjectContext) -> RenderedPrompt
```

`render()` then builds `prompt_kwargs` — which **is** `RenderedPrompt.template_variables`, by (a)'s
definition — with five entries, all JSON-native:

```python
prompt_kwargs: dict[str, object] = {
    "user_story": raw_text,                                  # snapshot: story_text
    "project_context": context.as_template_variables(),       # snapshot: project_context
    "negative_examples": [...],                               # rendered, not snapshotted
    "negative_examples_omitted": context.negative_examples_omitted,   # snapshot
    "few_shots": [example_as_dict(e) for e in examples],      # snapshot, not interpolated
}
if examples:
    prompt_kwargs["examples"] = self._format_examples(examples)   # unchanged text
```

The runner's write is (a)'s, unchanged in moment and ordering, with the key set widened:

```python
tv = rendered.template_variables
snapshot = {
    "validate": validate, "system_prompt": system_prompt,          # inherited from (a)
    "few_shots": tv["few_shots"], "project_context": tv["project_context"],
    "story_text": tv["user_story"], "negative_examples_omitted": tv["negative_examples_omitted"],
}
await extraction_repo.record_rendered_prompt(extraction_id, prompt_rendered=rendered.text,
                                             prompt_config=snapshot)
```

Consequences this fixes:

- **The snapshot keys are read from `template_variables`, never re-derived** — the requirement's
  authority rule. `story_text` is `template_variables["user_story"]`; `project_context` is the very
  dictionary the template received. There is no second composition path to drift from.
- **`negative_examples` is deliberately not a snapshot key.** The proposal's key list is `few_shots`,
  `project_context`, `story_text`, `negative_examples_omitted`, `usage`; the block itself is in
  `prompt_rendered` and re-derivable from the marks, so copying it into `prompt_config` would store
  it twice.
- **Every value under `template_variables` must be JSON-serializable**, because the same dictionary
  is handed to a `sa.JSON` column (`models/extraction.py:49` is `JSON`, not `JSONB`), and any writer
  of it replaces the whole value (a's decision). `ProjectContext.as_template_variables()` and the
  example/negative builders do the `UUID → str`, `TaskStatus → str` and `datetime → ISO-8601`
  conversion at that boundary, and one test asserts `json.dumps(snapshot)` on a full context.

`context` is **required** (no `None` default): a default would let a caller render the two-variable
prompt of 0.8.0 while the row still claimed to be a 0.9.0 version, and the type is what carries the
requirement. Rejected alternatives and their cost: **the service holding the two repository ports**
(contradicts (a)'s repository-free service and re-opens the session-ownership question inside the
domain); **the runner rendering the context itself and calling the prompt manager directly**
(duplicates the one place that composes the instruction and puts `template_variables` out of reach
of the write that must record it); **`context: ProjectContext | None = None`** (cheaper for the ~10
existing service call sites, but it makes "no context" expressible on the product path). The
mechanical cost of required is that every `render()`/`extract()` test call site supplies a context —
one shared builder in `tests/_helpers.py` absorbs most of it, the same pattern (a) uses.

### Decision: the two D23 ports, their row types, and the third read for the project row

```python
# domain/ports/user_story_repository.py
@dataclass(frozen=True, slots=True)
class StoryContextRow:
    id: UUID
    raw_text: str

async def list_for_context(self, project_id: UUID, *, exclude_story_id: UUID) -> list[StoryContextRow]:
    """Every story of one project except ``exclude_story_id``, oldest first.

    Deliberately unbounded: the paginator's window (default 20, cap 100 —
    ``api/schemas/common.py:9-10``) would drop rows while the prompt claimed to carry
    the whole project. The exclusion rides in the WHERE clause, never in a Python filter.
    """

# domain/ports/task_repository.py
@dataclass(frozen=True, slots=True)
class TaskContextRow:
    title: str
    status: TaskStatus
    user_story_id: UUID

async def list_for_context(self, project_id: UUID, *, exclude_story_id: UUID) -> list[TaskContextRow]:
    """Current-version, valid tasks of one project except the excluded story's, oldest first."""
```

Both row types are frozen slotted dataclasses beside their ports, like `ExtractionExample`
(`domain/ports/vector_store_port.py:10-18`) and (b)'s `TaskInvalidationCandidate`; both are
re-exported from `domain/ports/__init__.py`.

```python
# story read — one statement
select(UserStoryModel.id, UserStoryModel.raw_text).where(
    UserStoryModel.project_id == project_id,
    UserStoryModel.id != exclude_story_id,
).order_by(UserStoryModel.created_at, UserStoryModel.id)
```

The ordering is `created_at, id` ascending on both reads, so the same project state composes the
same block (the requirement's determinism scenario); `id` is the tiebreaker because two rows written
in the same instant must not swap.

**The third read is `ProjectRepository.find_by_id` (`project_repository.py:40-42`), which already
exists — no new port method for two strings.** Two things about it had to be answered:

- **`project.workspace_id` is not re-read.** The runner already holds `workspace_id` as its own
  parameter (`extraction_task.py:64-67`, `:282`) and the loaded story carries `project_id`
  (`domain/entities/user_story.py:22`), so the project row is read for `name` and `description`
  only. `Project.workspace_id` (`domain/entities/project.py:13`, `models/project.py:24-26`) comes
  back as a side effect of the row read and is ignored — nothing derives the vector scope from it,
  and no second lookup walks project → workspace.
- **The read is not one round-trip, and that is recorded rather than argued.** `ProjectModel`
  declares both `workspace` and `user_stories` with `lazy="selectin"` (`models/project.py:33-35`),
  and `UserStoryModel` declares `project`, `tasks` and `extractions` the same way
  (`models/user_story.py:51-58`), so the ORM load is accompanied by selectin SELECTs a call-site
  count cannot see — the exact effect Δ3 recorded. The design keeps `find_by_id` because the read it
  accompanies is already O(the project's rows) and because (c) adds no port method; the ladder
  (WU4) measures the real statement count instead. **Contingency:** if the 1000-story bench shows
  the hydration dominating, the sanctioned narrowing is a two-column projection
  (`select(ProjectModel.name, ProjectModel.description)`, the `list_parts_by_project` precedent for
  reading columns instead of whole rows, `user_story_repository.py:138-147`) added to the same port
  — triggered by a measured number, not by preference.

Statement cost, against Δ3's corrected baseline of ≈16 fixed + ≈2 per task: the **call-site** delta
is three reads (two ports + the project row), which is what D23's "two statements more" refers to
for the ports alone; the real count is higher by whatever `lazy="selectin"` adds, and the ladder is
where that number is written down. The `~8 + 1/task` figure is not repeated anywhere in this change.

Rejected alternative: **a new `find_context_by_id`/`list_for_context` on the project port.** It
would read two columns and nothing else, but it adds a fourth port method, a repository
implementation and its tests for a read the existing method already serves — and the honest cost it
avoids is one the bench is required to measure anyway.

### Decision: the task-context read is current-version *and* valid-only, in one statement

A project holds one task set **per version** after (a)+(b), and an invalid mark can sit on any task
of any of them. Both facts belong in the `WHERE`, not in a Python pass:

```python
E, N = aliased(ExtractionModel), aliased(ExtractionModel)      # producing run, newer run
stmt = (
    select(TaskModel.title, TaskModel.status, TaskModel.user_story_id)
    .join(UserStoryModel, UserStoryModel.id == TaskModel.user_story_id)     # task → story
    .join(E, E.id == TaskModel.extraction_id)                               # task → extraction
    .where(
        UserStoryModel.project_id == project_id,                            # story → project
        TaskModel.user_story_id != exclude_story_id,                        # D9: never the story's own
        E.status == ExtractionStatus.COMPLETED.value,                       # current-version half 1
        ~exists().where(                                                    # current-version half 2
            N.user_story_id == E.user_story_id,
            N.status == ExtractionStatus.COMPLETED.value,
            N.version_number > E.version_number,
        ),
        ~exists().where(                                                    # D9: never an invalid task
            TaskInvalidationModel.task_id == TaskModel.id,
            TaskInvalidationModel.revoked_at.is_(None),
        ),
    )
    .order_by(TaskModel.created_at, TaskModel.id)
)
```

One statement, four tables, no `LIMIT`. The currency predicate is the same rule (b) applies to the
task reads, expressed in the "no higher-numbered completed version of this story" form its
workspace scope uses, which needs no `MAX` and is served by `uq_extractions_story_version` (a). The
invalid-task exclusion is `NOT EXISTS` on `task_invalidations` with `revoked_at IS NULL` — the same
"active mark" predicate (a)'s partial index backs (`uq_task_invalidations_active_task`).

**Why a Python filter would reintroduce the truncation D23 exists to prevent:** the only
project-scoped task read in the tree today is `list_page` (`task_repository.py:45`), and it is
windowed. A caller that read through it and filtered in Python would drop rows *before* the filter
could see them, while the composed block still claimed to carry "the project's tasks" — silent
truncation, which is the failure D23 names. Even over a hypothetical unpaginated read, filtering in
Python preserves correctness only for as long as every future caller remembers to keep the read
unbounded; putting both exclusions in the `WHERE` makes correctness independent of that promise, and
sends 1000 stories × several versions' tasks across the wire only to discard them.

**Tradeoff**: the currency predicate is now expressed in a third place (b's story scope, b's
workspace scope, this read), and three shapes for one rule is three chances to drift. A cross-check
test ties them: the tasks `list_for_context` returns for a project equal the union of (b)'s
current-version `GET /tasks?workspace_id=` rows for that project's stories, over a fixture with two
completed versions and one invalid mark. Rejected alternative: reusing `list_page` with
`limit=1000` — a magic number that is neither a contract nor a bound, and the project can cross it
(`story_csv.py:23,143` caps a *file*, not a project).

### Decision: the negative-example block is one read, one pure composer, one cap constant, reusing (b)'s normalizer

```python
# domain/services/negative_examples.py  (new)
MAX_NEGATIVE_EXAMPLES = 20

@dataclass(frozen=True, slots=True)
class NegativeExample:
    title: str
    reason: str
    version_number: int
    marked_at: datetime

@dataclass(frozen=True, slots=True)
class NegativeExampleBlock:
    examples: tuple[NegativeExample, ...]
    omitted: int
    def as_template_variables(self) -> list[dict[str, object]]:
        """JSON-native: ``[{title, reason, version_number, marked_at}]``."""

def compose_negative_examples(
    candidates: Sequence[TaskInvalidationCandidate],
) -> NegativeExampleBlock:
    """Sort ``marked_at DESC`` (tiebreak: ``version_number DESC``, normalized title, reason),
    dedupe on ``(normalize_task_title(title), reason)`` keeping the most recent of each pair,
    take ``MAX_NEGATIVE_EXAMPLES``, and report ``omitted = deduped_total - taken``."""
```

- **The read is (b)'s existing one**, `TaskInvalidationRepository.list_active_on_other_versions(*,
  user_story_id, exclude_extraction_id)` (b's design), called with `exclude_extraction_id=None`.
  That read joins `task_invalidations → tasks → extractions`, filters `tasks.user_story_id =
  :story_id`, `tasks.extraction_id IS DISTINCT FROM :exclude_extraction_id` and
  `revoked_at IS NULL`, and returns `TaskInvalidationCandidate(version_number, title, reason,
  marked_at)`. With no exclusion it is exactly D7's row set — every mark of every version of *this*
  story and no other story's — so **no second mark read is invented**, and the in-flight run has no
  tasks yet, so it cannot include itself. One statement.
- **Deduplication reuses `normalize_task_title`**, the helper (b) ships in
  `domain/services/task_title_normalizer.py` (casefold + whitespace collapse + strip). (c) imports
  it; a second normalizer is forbidden, and a unit test pins the import identity so a copy cannot
  appear quietly. Seam: (b)'s **WU4** carries that module; (c)'s WU2 depends on it, and if (c)'s WU2
  lands first it waits for (b) WU4 (same release, and the module is ~10 lines).
- **The cap is a module constant of the feature**, not a column, not `workspace_prompts`, not a
  request parameter. A workspace knob would let a workspace silently re-break D19, so the layer that
  owns the number is the domain (`workspace_prompt.py:26-34` already holds the three *few-shot*
  knobs, and the cap is deliberately not a fourth).
- **The omission is announced by the template and counted in the snapshot**: the template prints the
  sentence when `negative_examples_omitted > 0`, and the same integer is what WU2 puts in
  `prompt_config.negative_examples_omitted`. One source, two renderings.
- **Determinism matters because the block's text is snapshotted**: with `marked_at` ties the
  tiebreak order is total (version, then normalized title, then reason), so two runs over the same
  project state compose byte-identical blocks.

The rendered English block (in `task_generation.j2`, after the context block, before the story):

```
## Do Not Produce These Tasks (Previously Marked Invalid)

A reviewer marked these tasks invalid in earlier versions of this story. Do not produce them again:
- Implement login retry — reason: duplicates the auth task (version 1)
- Wire the retry banner — reason: too coarse to implement (version 2)

3 older marks were omitted.
```

**(correction)** The source spec's wording for D7/D19 is Spanish ("se omitieron N marcas más
antiguas"). The sentence that ships is English, and the deviation is deliberate: the template and
every model-facing block are English (`task_generation.j2:1-26` is English, and the validated
DataForge pipeline is English), while the Spanish sentence states the *rule* rather than the string.
The requirement itself says "in the template's English". A test asserts the rendered omission
sentence, so a later "translate the prompt" edit fails loudly rather than quietly changing what the
model reads.

**(correction)** The proposal's illustrative `project_context` shape lists `existing_tasks:
[{id, user_story_id, title, status}]`. The port's projection is `(title, status, user_story_id)` and
the requirement names exactly "each task's title, its status and the story it belongs to", so the
composed entry is `{user_story_id, title, status}` — a task id the read does not project cannot
appear in the shape without widening the projection, and the story id is what pairs a task with the
other-stories block.

Rejected alternatives: **composing in SQL with a window function** (the dedup key is
`casefold`-based, which Postgres `lower()` is not, and the cap is a feature constant — same reason
(b) computes D16's match in Python); **storing the composed block in the snapshot** (duplicate of
`prompt_rendered`, against D8's "nothing is stored twice"); **surfacing older marks as a
`workspace_prompts` limit** (dead configuration that can re-break D19).

### Decision: D10's first exclusion is a `must_not`, the second is a fail-closed positive `must`, and both live in the filter

```python
# domain/ports/vector_store_port.py
async def search_similar(
    self, text: str, limit: int = 3, threshold: float = 0.85,
    *, workspace_id: UUID, exclude_story_id: UUID,
) -> list[ExtractionExample]: ...

# infrastructure/vector/qdrant_adapter.py
query_filter = qdrant_models.Filter(
    must=[
        qdrant_models.FieldCondition(key="workspace_id",
                                     match=qdrant_models.MatchValue(value=str(workspace_id))),
        qdrant_models.FieldCondition(key="has_invalid_tasks",
                                     match=qdrant_models.MatchValue(value=False)),
    ],
    must_not=[
        qdrant_models.FieldCondition(key="user_story_id",
                                     match=qdrant_models.MatchValue(value=str(exclude_story_id))),
    ],
)
```

- **Why the validity condition is a positive `must` on `false` and not a `must_not` on `true`:** a
  `must_not` matches "the condition is false or absent", so a point whose payload simply lacks the
  key would be admitted — read as *valid*. The positive condition requires the key to be present and
  `false`, which is the fail-closed posture `vector-store-isolation` already documents for untagged
  points: a point that does not carry the flag is not valid. D11 wipes both collections before the
  flag exists, so no legacy point is *expected* to lack it; fail-closed is what keeps that true if
  one does.
- **The values are the strings the payload writes.** `workspace_id` is stored as
  `str(workspace_id)` and `user_story_id` as `str(...)` (`qdrant_adapter.py:257-265`), so both
  `MatchValue`s are string comparisons and no UUID coercion is involved.
- **The story exclusion is unconditional**, as the proposal fixes it: the port docstring states that
  every search excludes the story being extracted and every extraction carrying an active invalid
  mark, so no caller can opt out and no "include contaminated points" boolean exists.
- **Exclusion 1 is not hypothetical**: the in-flight point is upserted *after* the search
  (`extraction_task.py`'s `_store_rag` at `:535-557` runs after `render()`'s search), so what could
  return today is the previous run of the same story.

**Callers that must move** (a signature change, all mechanical):

| Caller | Change |
| --- | --- |
| `extraction_service._fetch_rag_examples` (`extraction_service.py:171-210`) | takes the story id and forwards `exclude_story_id`; **fails closed when the story has no id** (skip retrieval, warn `missing_story_id`), mirroring the existing missing-`workspace_id` branch at `:186-197` (`:195` carries the warning) |
| `extraction_service.render()` (was `extract()` at `:82`, search call at `:199`) | passes `exclude_story_id=getattr(story, "id", None)` |
| `tests/test_unit/test_vector_store.py` (≈10 call sites), `tests/test_unit/test_few_shot_retrieval.py`, `tests/test_services/test_extraction_service.py`, `tests/test_extraction_flow_few_shot.py`, `tests/test_integration/test_few_shot_rag_qdrant.py` (≈7 call sites) | pass the new keyword |
| `tests/test_api/test_extraction.py:59-76` `_RecordingVectorStore` | implements the new signature (its `store_extraction` takes `**kwargs` and is unaffected) |
| **No seed or CLI path exists**: the only production callers are the service and the runner | — |

### Decision: the payload grows to ten keys, and the indexes follow the mechanism already in the adapter

`store_extraction` gains two required keyword-only arguments and writes three keys:

```python
# domain/ports/vector_store_port.py
async def store_extraction(
    self, *, extraction_id: str, user_story_text: str, tasks_summary: str, model_used: str,
    workspace_id: UUID, project_id: UUID, version_number: int,
    confidence_score: float | None = None, user_story_id: str = "",
) -> bool: ...

# the upsert payload (qdrant_adapter.py:253-265): the existing seven keys plus
"project_id": str(project_id), "version_number": version_number, "has_invalid_tasks": False,
```

`has_invalid_tasks` is stored `False` at write time, and that is sound: a point is stored after its
run's tasks are created, and a task cannot be marked before it exists. **The upsert cannot wipe a
legitimate mark**: re-storing the same `extraction_id` overwrites the same point id, and while a run
is un-`completed` (b)'s frozen check refuses a mark on its tasks — `find_current_version` returns the
previous version, so `existing.extraction_id != current.id` holds. The window between the task write
and the upsert is not a window a mark can enter.

The two new filtered keys need payload indexes, and the mechanism to follow is the one already
there: `_ensure_workspace_payload_index` (`qdrant_adapter.py:104-119`), called from `_get_client`
right after the collection is ensured (`:97`), guarded by the `self._index_ensured` flag, issuing
`create_payload_index(collection_name=..., field_name=..., field_schema=..., wait=True)` and logging
a failure without failing the request. The design generalises it to one `_ensure_payload_indexes`
loop over `("workspace_id", "project_id", "has_invalid_tasks")` behind a single `_indexes_ensured`
flag. **Both collections get the indexes with no migration and no backfill**: each environment's
adapter points at its own collection (`qdrant_collection`; prod
`storico_extractions_prod`, ADR-005), and the ensure runs lazily on that collection's first use.

**(correction)** `vector-store-isolation`'s modified requirement says "keyword payload indexes on
`workspace_id`, `project_id` and `has_invalid_tasks`". `workspace_id` and `project_id` are
`PayloadSchemaType.KEYWORD` (they are strings); `has_invalid_tasks` is a JSON boolean and the design
gives it `PayloadSchemaType.BOOL`, the schema that serves a boolean match condition. The
requirement's point — the indexes exist so filtered searches stay fast — is met, and the deviation
is named rather than silent. **Contingency:** if the pinned `qdrant_client` rejects the boolean
index, the fallback is the literal `KEYWORD` schema, which still matches `false`; WU3's first RED
step pins the schema against the pinned client, and the opt-in live test
(`STORICO_TEST_LIVE_QDRANT=1`) asserts the collection's `payload_schema` keys.

### Decision: the validity flag is refreshed by point id — `set_payload`, before the relational write

```python
# domain/ports/vector_store_port.py
@abstractmethod
async def set_has_invalid_tasks(self, *, extraction_id: str, has_invalid_tasks: bool) -> None:
    """Set the validity flag on the point whose id IS ``extraction_id``.

    No search is involved: ``store_extraction`` upserts with ``id=extraction_id``
    (``qdrant_adapter.py:253``), so the point is addressable by the extraction id. A point
    that does not exist is a no-op (nothing was ever stored, so nothing can be retrieved).
    Raises ``VectorStoreError`` on failure — unlike ``search_similar``/``store_extraction``,
    the caller must not proceed on an unverified result.
    """
```

```python
# infrastructure/vector/qdrant_adapter.py
await client.set_payload(collection_name=self._collection_name,
                         payload={"has_invalid_tasks": has_invalid_tasks},
                         points=[extraction_id], wait=True)
```

`set_payload` without a `key` merges the mapping into the stored payload, so the other nine keys
survive; it is not a re-embed and not a re-upsert.

**Who calls it: (b)'s two mark handlers** in `api/routes/tasks.py` (b's WU4), in this order, which
is where **(c) corrects the proposal's wording**:

| Handler | Order |
| --- | --- |
| create mark | gate (403) → reason schema (422) → frozen check (409) → `find_active_by_task` (409) → **`set_has_invalid_tasks(extraction_id, True)`** → `invalidation_repo.create(mark)` → 201 |
| revoke | gate → frozen check (409) → `find_active_by_task` (404) → **`remaining = count_active_for_extraction(extraction_id, exclude_mark_id=mark.id)`** → **`set_has_invalid_tasks(extraction_id, remaining > 0)`** → `invalidation_repo.revoke(...)` → 204 |

**(correction)** The proposal's Affected-Areas cell says the handlers "call `set_has_invalid_tasks`
after the mark commits". The requirement's scenario says a refresh failure MUST leave the mark
unpersisted, and "after the commit" cannot satisfy it: a refresh failure would surface with the mark
already durable, which is exactly the state the requirement forbids — a mark confirmed over a vector
store that still returns the run it condemns. The spec's requirement wins, and the refresh sits
**before** the relational write. The other partial-failure direction (point flagged, write lost) is
over-exclusion, which the proposal already records as the safe direction.

The failure composition:

- **Refresh fails on mark** → `VectorStoreError` propagates → (b)'s handler answers 503
  `VECTOR_STORE_UNAVAILABLE`; no mark row exists. The user retries cleanly.
- **Refresh fails on revoke** → 503, and the mark stays active, so the flag (`true`) and the marks
  (one active) still agree. Nothing is silently admitted.
- **No vector store configured** → `get_vector_store` returns `None` (`api/dependencies.py:185-202`)
  and the handler skips the refresh entirely, exactly as the requirement's last scenario states.
- **Reported but assumed good news:** between the point being flagged and the write failing, a point
  is excluded with no mark. Over-exclusion is the safe direction and is recorded, not hidden.

**The revoke recomputation needs one new read on (b)'s port**, in (b)'s file:

```python
# domain/ports/task_invalidation_repository.py
async def count_active_for_extraction(
    self, *, extraction_id: UUID, exclude_mark_id: UUID | None = None
) -> int:
    """Active marks on any task of one extraction, optionally ignoring one row.

    ``task_invalidations JOIN tasks`` on ``tasks.id = task_invalidations.task_id``,
    ``tasks.extraction_id = :extraction_id``, ``revoked_at IS NULL``,
    ``id != :exclude_mark_id``. One statement.
    """
```

It is a **computed** value, not a post-hoc read of a committed state: computing the post-revoke
active count *before* committing the revoke is what makes the refresh-first order possible without
surgery on (b)'s `revoke`, which commits internally by design. Seam: **(c)'s WU3 adds this method to
(b)'s port and repository; (b)'s WU4 handlers call it and `set_has_invalid_tasks` in the order
above.** Nothing else in (b) changes.

**Composition with D15's `delete_by_story`:** the two never interact. `delete_by_story` (b) deletes
points by a `workspace_id + user_story_id` payload filter and does not read the validity flag, so a
flagged point is deleted like any other; the refresh is a point-id write and cannot resurrect a
deleted point (it no-ops). A mark on a task of a story being deleted concurrently is lost with the
story, which is D15's outcome.

### Decision: `usage` travels out on two domain types, the four adapters copy the provider's own mapping, and the snapshot is updated by one narrow write

```python
# domain/ports/llm_port.py
@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    usage: dict[str, object] | None = None

@dataclass(frozen=True, slots=True)
class ExtractionResult:          # currently dead: no source or test use it today
    tasks: tuple[ParsedTask, ...]
    raw_response: str
    confidence_score: float | None = None
    usage: dict[str, object] | None = None

async def generate(self, prompt, config, system_prompt=None) -> LLMResponse: ...
```

```
# the four parse sites, each of which reads only content today
ollama_adapter.py:159-165   -> LLMResponse(text=data["message"]["content"],
                                           usage={"prompt_eval_count": …, "eval_count": …}  # keys present only)
openai_adapter.py:124       -> LLMResponse(text=…, usage=response.usage.model_dump() if … else None)
anthropic_adapter.py:104-107-> LLMResponse(text="".join(text_blocks), usage=response.usage.model_dump() if … else None)
gemini_adapter.py:81        -> LLMResponse(text=response.text, usage=response.usage_metadata.model_dump() if … else None)

# domain/services/extraction_service.py — (a)'s generate() widens its return
async def generate(self, rendered, config) -> ExtractionResult
```

**(correction, seam amendment to (a))** (a)'s Interfaces section fixes
`generate(rendered, config) -> tuple[list[ParsedTask], str]`. Usage cannot leave the service through
a two-tuple, so (c) widens that return to `ExtractionResult` — the domain type that exists for
exactly this and that nothing has ever used. One sentence of (a)'s Interfaces section is therefore
superseded; the change is a return type and a `result.tasks` iteration at the runner, and both
slices ship together, so (a)'s WU3 may implement the final shape directly.

**`LLMPort.generate` returns `LLMResponse`** rather than `str`, one entry point, because usage is a
property of every provider response and a second `generate_with_usage` method would make "which one
do I call" a live question. The ripple is mechanical and named:

| Site | Change |
| --- | --- |
| the four adapters (`ollama_adapter.py:41`, `openai_adapter.py:52`, `anthropic_adapter.py:42`, `gemini_adapter.py:34`) | return `LLMResponse`; parse the usage container when present |
| `domain/services/extraction_judge_service.py:73` | reads `.text` |
| `api/routes/settings.py:175,208,241,274,315` (the five connection probes) | read `.text` |
| `domain/services/extraction_service.py:156` | reads `.text`, builds `ExtractionResult` |
| test doubles: `tests/test_integration/test_few_shot_rag_qdrant.py:117-130`, `tests/test_api/test_extraction.py:197,254,322`, `tests/test_api/test_llm_test_route.py:39` | return `LLMResponse` |
| adapter unit tests (`test_unit/test_{ollama,openai,anthropic,gemini}_adapter.py`) | assert the returned text and usage |

**The write, and why it is a narrow port method.** `usage` cannot be in (a)'s render-time write — the
provider has not answered — so the runner updates the same `prompt_config` **after** the provider
answers, through one method that names only that column:

```python
# domain/ports/extraction_repository.py
async def record_usage(self, extraction_id: UUID, *, prompt_config: dict) -> None:
    """Replace ``prompt_config`` with the complete dictionary. Names no other column."""
```

```python
result = await extraction_service.generate(rendered, llm_config)       # ExtractionResult
if result.usage is not None:
    await extraction_repo.record_usage(extraction_id, prompt_config={**snapshot, "usage": result.usage})
```

Two properties this buys: the write restates the whole dictionary (a `JSON` column has no merge, and
(a) already established that restating beats read-modify-write), and it cannot name a snapshot column,
so (a)'s rule that a terminal write cannot null a snapshot column still holds — `record_usage` is the
fourth method of that family and the only one whose subject is `prompt_config`.

**When the provider returns nothing, no write happens** and the key is absent — never zero-filled,
never estimated. **A `failed` run that never got an answer** keeps every other snapshot key (they were
written between render and generate, (a)'s ordering) and has no `usage`; `prompt_rendered` stays
non-null, so the failure is readable as "the prompt was sent and the call died". `prompt_rendered
= NULL` still means "died before render".

**Field names are confirmed before the adapter is wired, and the confirmation is a task, not an
assumption.** D20's names are unverified in this repo — a repo-wide grep for `usage`,
`prompt_eval_count`, `eval_count`, `usageMetadata`, `prompt_tokens`, `completion_tokens`,
`total_tokens` returns zero matches in source or tests, and `ExtractionResult`
(`llm_port.py:30-33`) has never been used. WU4 therefore carries a **per-provider confirmation
against a real response** of each provider, recorded in `verify-report.md` as a table (provider →
field actually present → captured mapping or "absent"), and each adapter test pins the captured shape
once confirmed. The rule that survives whatever the confirmation says is fixed here: **if the
provider returns nothing, the key is omitted and the omission is annotated.** Storing the provider's
own mapping (rather than a normalized schema invented here) keeps the confirmation visible in the
data.

Rejected alternative: **a normalized `{"input_tokens": …, "output_tokens": …}` schema invented in
the domain.** It reads better in a dashboard, but it requires deciding the normalization from field
names that are unverified, and it hides which provider actually returned what — the opposite of
"record the provider's own mapping verbatim".

### Decision: the template gains both blocks in English, and a workspace template that ignores them is an opt-out, detected in the version's record

`task_generation.j2` keeps its format instructions and its two existing variables
(`task_generation.j2:1-26`); the block order is fixed by the proposal and implemented literally:

```
## Project Context                 ← {% if project_context %} … name, description,
                                     other_stories, existing_tasks …
## Do Not Produce These Tasks (Previously Marked Invalid)   ← {% if negative_examples %}
## Few-Shot Examples               ← the existing section, unchanged ({% if examples %})
Now break down the following user story:
User story: {{user_story}}
```

The negative block sits after the context block so no invalid task is ever stated as positive
context, and before the story so it reads as a constraint on the answer. `examples` keeps producing
the same string `_format_examples` produces today (`extraction_service.py:212-222`), so every
workspace-authored template that interpolates `{{ examples }}` keeps working byte for byte.

**The opt-out is Jinja's own behaviour plus the record.** A workspace whose `instruction_template`
references only `{{ user_story }}` renders with the extra kwargs simply unused: Jinja ignores unknown
variables (`prompt_manager.py:93-123` renders with `**kwargs` verbatim), so the run **succeeds**,
produces no context and no negative block, and — because the snapshot is filled from
`template_variables` and not from the rendered text — `prompt_config.project_context` and
`prompt_config.negative_examples_omitted` still record what was composed. `prompt_rendered` remains
the authority on what the provider received. The divergence is therefore **readable by comparing two
stored facts of the same version**, which is what "never silent" means here.

**Where it is detected:** (1) automatically, in the render tests — one case asserts that a custom
template without the variables renders neither block while `template_variables` still carries them
(`tests/test_unit/test_prompt_manager.py` for the template half, a runner-level case in
`tests/test_api/test_extraction.py` for the snapshot half); (2) by a human, in the version's record.
**No runtime warning is added**, deliberately: the requirement blesses the opt-out, so a warning
would fire on every run of a workspace that chose it. The prompt editor is where a workspace adds the
blocks — it is a plain textarea with no variable legend today
(`frontend/src/components/react/LLMConfigEditor.tsx:1126-1150`), so there is nothing in 0.9.0 to keep
in step, and a variable legend is a UI follow-up outside this slice.

### Decision: both benches are an executable, operator-run plan whose only artifact is the verification report

They are two obligations, not one, and neither substitutes for the other.

**D20's ladder — 1 / 50 / 200 stories, on a Neon-like database, never the dev pooler.** Per size:
one fresh workspace, one project, stories created through the CSV import
(`POST /api/v1/workspaces/{workspace_id}/stories/import`, `api/routes/stories.py:325-326`), one
extraction run on a story of that project with a configured provider. Three numbers per project,
**from one query over the row the run stored — no new instrument** (D20 forbids a timing middleware
and a metrics view; `completed_at` and `created_at` already exist, `models/extraction.py:52,56-58`,
and `prompt_rendered` is (a)'s column):

```sql
SELECT e.version_number,
       length(e.prompt_rendered)                    AS prompt_chars,
       e.completed_at - e.created_at                AS duration,
       e.status,
       e.prompt_config -> 'usage'                   AS usage
FROM extractions e JOIN user_stories s ON s.id = e.user_story_id
WHERE s.project_id = :project_id
ORDER BY e.created_at DESC LIMIT 1;
```

**D23's mandatory 1000-story project, created through the CSV import.** One import of 1000 rows
(`MAX_ROWS = 1000` is enforced *inside the parser* per file, `story_csv.py:23,143`, and
`api/routes/stories.py:409-410` only formats the error detail), then one run, then the count check —
`json_array_length(prompt_config -> 'project_context' -> 'other_stories')` compared against
`SELECT count(*) FROM user_stories WHERE project_id = :project_id` minus one. 1000 is recorded as a
**floor**, not a project maximum, with the annotation's exact wording: *"1000 stories from one import;
a second import crosses it."*

**Both outcomes are legitimate and both are recorded.** Either the run stores a version whose prompt
size and duration are measured, **or** the provider rejects the prompt and — by D22 — that run
consumes a version number while producing nothing (`status = failed`, `prompt_rendered` non-null, no
`usage`, `error_info` naming the refusal). The rejection is a **finding**, not a red test to retry
until green: nothing in the extraction path is changed to make it pass, and if it happens it is a new
decision for the user, not something this change resolves by inventing a cap, a truncation or an
input-side pagination.

Why the rejection is plausible rather than theoretical: the two bounds that exist are per-item, not
per-prompt — a story is capped at 2000 characters (`api/schemas/story.py:20,31`,
`story_import.py:35`) and an import is capped per file, so a 1000-story project composes roughly
1000 × 2000 characters of other-story text plus one task set per version (nothing is deleted, D12)
against a hardcoded 2048-token **output** cap and no input cap (`extraction_task.py:387`,
`llm_port.py:15`). That is ~5×10⁵ tokens by the exploration's arithmetic (`explore.md`), which is an
estimate and is therefore recorded as one — the bench replaces it with a number.

**The operator-visible artifact is `openspec/changes/extraction-versioning-prompt/verify-report.md`**
(the repo's existing verification-note convention, as D20 requires), holding: the ladder table per
project, the 1000-story run and its bound statement, the outcome each landed in, the real numbers if
the outcome was rejection, the per-provider `usage` confirmation table, and one line stating that no
cap, truncation or pagination shortcut was added. The dev pooler is excluded by name because of its
~2 s per-statement floor (open debt 2), which would make a 200-story ladder measure the pooler
instead of the prompt.

## Data Flow

```
POST /workspaces/W/extract/                     (b) gate, config check, temperature resolved
  → create_next_version(...)                    (a) mints version_number; 202 returns it
  → asyncio.create_task(run_background_extraction(..., version_number=N))

runner (its own session):
  1. story = story_repo.find_by_id(story_id)                  story → project_id, raw_text, id
  2. context = ProjectContext(                                (c) WU1/WU2 — four reads
        project_repo.find_by_id(story.project_id)                → name, description
        story_repo.list_for_context(project_id, exclude_story_id=story.id)
        task_repo.list_for_context(project_id, exclude_story_id=story.id)   current + valid only
        invalidation_repo.list_active_on_other_versions(user_story_id=story.id,
                                                        exclude_extraction_id=None)
        → compose_negative_examples(...)                     pure: sort, dedupe, cap 20, omitted)
  3. rendered = await extraction_service.render(             RAG search excludes story + invalid
        story, ..., few_shot_config, context=context)        → RenderedPrompt(instruction,
                                                                  system_prompt,
                                                                  template_variables)
  4. record_rendered_prompt(extraction_id,                   (a)'s write; (c) fills its keys from
        prompt_rendered=rendered.text, prompt_config=snapshot)  template_variables
  5. result = await extraction_service.generate(rendered, llm_config)   ExtractionResult w/ usage
  6. if result.usage is not None:
        record_usage(extraction_id, prompt_config={**snapshot, "usage": result.usage})
  7. tasks written with extraction_id                        (a)
  8. _store_rag(..., project_id, version_number)             10-key payload, has_invalid_tasks=false
  9. mark_completed(...)                                     (a)

mark / revoke (b's handlers, (c)'s WU3 order):
  set_has_invalid_tasks(extraction_id, True | remaining > 0) → create/revoke the mark
  a failure raises VectorStoreError → 503 VECTOR_STORE_UNAVAILABLE, nothing persisted
```

## Interfaces / Contracts

```
# domain/services/extraction_service.py
ProjectContext(name, description, other_stories, existing_tasks,
               negative_examples=(), negative_examples_omitted=0)
    .as_template_variables() -> {"name", "description", "other_stories": [{"id","raw_text"}],
                                 "existing_tasks": [{"user_story_id","title","status"}]}
async render(story, *, system_prompt, instruction_template, workspace_id, few_shot_config,
             context: ProjectContext) -> RenderedPrompt      # template_variables gains 5 entries
async generate(rendered, config) -> ExtractionResult         # was tuple[list[ParsedTask], str]

# domain/services/negative_examples.py  (new)
MAX_NEGATIVE_EXAMPLES = 20
NegativeExample(title, reason, version_number, marked_at)
NegativeExampleBlock(examples, omitted).as_template_variables() -> list[dict]
compose_negative_examples(candidates: Sequence[TaskInvalidationCandidate]) -> NegativeExampleBlock

# domain/ports/user_story_repository.py / task_repository.py
StoryContextRow(id: UUID, raw_text: str)
TaskContextRow(title: str, status: TaskStatus, user_story_id: UUID)
list_for_context(project_id: UUID, *, exclude_story_id: UUID) -> list[…Row]     # both ports

# domain/ports/vector_store_port.py
search_similar(text, limit=3, threshold=0.85, *, workspace_id: UUID, exclude_story_id: UUID)
store_extraction(*, …, workspace_id: UUID, project_id: UUID, version_number: int, …) -> bool
set_has_invalid_tasks(*, extraction_id: str, has_invalid_tasks: bool) -> None   # raises VectorStoreError

# domain/ports/llm_port.py
LLMResponse(text: str, usage: dict[str, object] | None = None)
ExtractionResult(tasks, raw_response, confidence_score=None, usage: dict | None = None)
LLMPort.generate(prompt, config, system_prompt=None) -> LLMResponse

# domain/ports/extraction_repository.py  ((a)'s family + one)
record_usage(extraction_id, *, prompt_config: dict) -> None                     # names only prompt_config

# domain/ports/task_invalidation_repository.py  ((b)'s port + one)
count_active_for_extraction(*, extraction_id: UUID, exclude_mark_id: UUID | None = None) -> int

# infrastructure/vector/qdrant_adapter.py
_ensure_payload_indexes(client)     # workspace_id KEYWORD, project_id KEYWORD, has_invalid_tasks BOOL
set_has_invalid_tasks               # client.set_payload(payload={"has_invalid_tasks": …},
                                    #                    points=[extraction_id], wait=True)
```

## File Changes

| Path | WU | Change |
| --- | --- | --- |
| `domain/services/extraction_service.py` | 1, 2 | `ProjectContext` + `as_template_variables`; `render(context=...)`; the five `template_variables` entries; `_fetch_rag_examples` takes and forwards the story id; `generate() -> ExtractionResult` |
| `domain/services/negative_examples.py` | 2 | New: `MAX_NEGATIVE_EXAMPLES`, `NegativeExample`, `NegativeExampleBlock`, `compose_negative_examples` |
| `domain/ports/user_story_repository.py` · `task_repository.py` | 1 | `StoryContextRow` / `TaskContextRow` + `list_for_context` |
| `domain/ports/__init__.py` | 1, 2 | Re-export the new row types and `LLMResponse` |
| `infrastructure/database/repositories/user_story_repository.py` | 1 | The two-column unpaginated read, exclusion in the `WHERE` |
| `infrastructure/database/repositories/task_repository.py` | 1 | The one-statement current-version + valid-only project read |
| `infrastructure/llm/prompts/task_generation.j2` | 1 | `## Project Context` + the negative block (English); existing sections untouched |
| `domain/ports/vector_store_port.py` | 3 | `search_similar` signature + docstring; `store_extraction` two new args; `set_has_invalid_tasks` |
| `infrastructure/vector/qdrant_adapter.py` | 3 | `must`/`must_not` filter; 10-key payload; `_ensure_payload_indexes`; `set_payload` setter |
| `domain/ports/llm_port.py` | 2 | `LLMResponse`; `ExtractionResult.usage` |
| `infrastructure/llm/{ollama,openai,anthropic,gemini}_adapter.py` | 2 | Return `LLMResponse`; capture the provider's usage when present |
| `domain/ports/extraction_repository.py` + `infrastructure/database/repositories/extraction_repository.py` | 2 | `record_usage` (one `UPDATE`, `prompt_config` only) |
| `domain/ports/task_invalidation_repository.py` + `infrastructure/database/repositories/task_invalidation_repository.py` | 3 | `count_active_for_extraction` (b's files) |
| `api/routes/tasks.py` | 3 | The two mark handlers refresh the flag before their relational write (b's file) |
| `infrastructure/tasks/extraction_task.py` | 1, 2, 3 | Context reads and `ProjectContext` build; snapshot dict; usage write; `_store_rag` gains `project_id`/`version_number`; `version_number` threaded through `run_background_extraction`/`_run_extraction` |
| `domain/services/extraction_judge_service.py` · `api/routes/settings.py` | 2 | Read `.text` from `LLMResponse` |
| `tests/**` | 1–3 | See the testing table below |
| `openspec/changes/extraction-versioning-prompt/verify-report.md` | 4 | New: both benches, the usage confirmation table, the outcome of each run |

## Testing Strategy

STRICT TDD, in the config's order (RED → GREEN → TRIANGULATE → REFACTOR); every scenario below gets
its failing test first and a work unit does not close until the whole suite is green. Runners:

- **Unit / SQLite**: `cd backend && conda run -n storico python -m pytest -m unit` — the schema comes
  from the models (`Base.metadata.create_all`, `tests/conftest.py:149`) on
  `sqlite+aiosqlite://` (`tests/conftest.py:36`), so the new tables and constraints exist, but
  **SQLite enforces no foreign keys** in this suite (no `PRAGMA foreign_keys`).
- **Integration / Postgres**: `cd backend && conda run -n storico python -m pytest -m integration`
  (testcontainers; skipped without a Docker daemon).
- **Live Qdrant + Ollama** (opt-in): `STORICO_TEST_LIVE_QDRANT=1 … python -m pytest
  tests/test_integration/test_few_shot_rag_qdrant.py` — a skip here proves nothing, and the flag
  makes an unreachable service a failure by design.
- **Whole suite (acceptance)**: `cd backend && conda run -n storico python -m pytest`.
- No frontend test and no E2E: this slice has no UI.

| Requirement (spec scenario) | Test | Home | Layer |
| --- | --- | --- | --- |
| Project name and description at render time | Rendered prompt contains both; a description edit does not change version 1's stored prompt | `test_api/test_extraction.py` | Unit |
| The project's other stories and existing tasks appear | Rendered prompt contains each other story's `raw_text` and each task title with its owning story id | `test_api/test_extraction.py` + `test_unit/test_prompt_manager.py` (string) | Unit |
| The story never appears as its own context | Prior version's task titles absent from the prompt's task block; the story text appears once; `list_for_context` excludes it | `test_api/test_extraction.py` + `test_repositories/test_task_repo.py` | Unit |
| No invalid task as positive context, and revoke restores it | Marked task absent from `list_for_context` and from the prompt; after revoke it returns and leaves the negative block | `test_repositories/test_task_repo.py` + `test_api/test_extraction.py` | Unit |
| Negative examples are all previous versions' marks | Composer over three candidate rows; a mark of another story is absent; the block lists both titles with reasons | `test_unit/test_negative_examples.py` + `test_api/test_extraction.py` | Unit |
| Cap 20, most recent first, dedup, self-announcing, no workspace knob | Composer table (21 → 20 + `omitted == 1`; identical normalized title+reason dedupe to the newest; tiebreak order total); the rendered sentence; `negative_examples_omitted == 1` on the row; `FewShotConfig`/`workspace_prompts` carry no cap | `test_unit/test_negative_examples.py` + `test_api/test_extraction.py` | Unit |
| Context read unpaginated, exclusion in the `WHERE` | 120-story project returns 119 (past the API's cap of 100); a signature assertion that neither port method has `limit`/`offset`; **1000-story project returns 999** | `test_repositories/test_{user_story,task}_repo.py` (120) + `test_integration/test_context_ports_scale.py` (1000) | Unit + **Postgres** |
| A workspace template opts out | A custom template renders neither block while `template_variables` still carries the context; the snapshot records the composed context, `prompt_rendered` shows no block | `test_unit/test_prompt_manager.py` + `test_api/test_extraction.py` | Unit |
| Snapshot carries the few-shots with their text | With a recording fake returning two examples, `few_shots` lists both with text, model and similarity, matching the prompt's few-shot section | `test_api/test_extraction.py` | Unit |
| Snapshot carries `project_context` and `story_text`; nothing stored twice | Key set is exactly the six expected keys; editing the story leaves version 1's `story_text`; `json.dumps(snapshot)` succeeds | `test_api/test_extraction.py` | Unit |
| Snapshot records `negative_examples_omitted` | 5 marks → `0`; 21 distinct marks → `1` and the block announces it | `test_api/test_extraction.py` | Unit |
| Usage stored only when returned | Per adapter: the provider's mapping captured verbatim, or absent; runner: `record_usage` called once when present, never when absent; a `failed` run keeps every key but `usage` | `test_unit/test_{ollama,openai,anthropic,gemini}_adapter.py` + `test_api/test_extraction.py` | Unit |
| Measurement derives from stored facts, no new instrument | A completed row's `created_at`/`completed_at`/`prompt_rendered` are the measurement inputs, and the app's middleware list stays `[CORSMiddleware]` | `test_api/test_extraction.py` + a shape assertion on `create_app()` | Unit |
| Reproducibility is the stored prompt | Two runs, same provider/model/temperature, one new story in between → two different prompts, each row keeping its own | `test_api/test_extraction.py` | Unit |
| Both bench outcomes are honest and recorded | Operator run; numbers and outcome in `verify-report.md` | — | **Not automated (operator)** |
| Few-shot: no self, no invalid-marked extraction, both in the filter | Filter expression asserted against a fake client (`must` keys/values, `must_not` key/value); live Qdrant: same-story point excluded, marked extraction excluded, and with `limit=1` the valid example is the one returned | `test_unit/test_vector_store.py` + `test_integration/test_few_shot_rag_qdrant.py` | Unit + **live Qdrant** |
| A point without the flag is not valid | The validity condition is a positive `must` on `False` (never a `must_not` on `True`); live: a point written without the key is not returned, a valid point still is | `test_unit/test_vector_store.py` + `test_integration/test_few_shot_rag_qdrant.py` | Unit + **live Qdrant** |
| Workspace-scoped retrieval names the story to exclude | `exclude_story_id` is a required keyword on both the port and the adapter (the existing signature-inspection pattern, `test_unit/test_vector_store.py:157-166`); the service fails closed without a story id | `test_unit/test_vector_store.py` + `test_unit/test_few_shot_retrieval.py` | Unit |
| Payload indexes for the three filtered keys | `create_payload_index` called for `workspace_id`/`project_id` (`KEYWORD`) and `has_invalid_tasks` (`BOOL`); live: the collection's `payload_schema` carries all three | `test_unit/test_vector_store.py` + live | Unit + **live Qdrant** |
| Every point carries project, version and validity | The pinned payload test grows from 7 to 10 keys; the runner passes `project_id` and the run's own `version_number` through the recording fake | `test_unit/test_vector_store.py:606-639` + `test_api/test_extraction.py` | Unit |
| The flag tracks the marks, on mark and revoke | Mark → one `set_has_invalid_tasks(…, True)` **before** `create`; revoke with another active mark → `True`; last mark revoked → `False`; refresh failure → 503 and no mark row / the mark still active; no vector store → both operations proceed with no refresh call | `test_api/test_tasks.py` | Unit |
| The migration-free statement cost | The ladder records the real fixed count; no test asserts a statement count | — | **Not automated (bench)** |
| Cross-cutting: one currency rule in two places | The tasks `list_for_context` returns equal the union of (b)'s current-version `GET /tasks?workspace_id=` rows for the same project | `test_repositories/test_task_repo.py` | Unit |
| Cross-cutting: one normalizer | The composer imports `normalize_task_title` (identity assertion), and no second casefold/whitespace helper exists | `test_unit/test_negative_examples.py` | Unit |

**Why the layers divide this way.** A prompt-content assertion is unit-provable twice over: the
template's own text needs no database at all (`PromptManager.render` with the variables,
`test_unit/test_prompt_manager.py`), and "what the provider received" is asserted at the runner with
the LLM doubled (`test_api/test_extraction.py`, the existing `AnsweringLLM`/`_RecordingVectorStore`
pattern) — no provider, no Qdrant, no network. The **ports** need the repository layer, because
"the exclusion is in the `WHERE`" is only observable as rows: a fixture with two versions, another
story, and one invalid mark. The **1000-row non-truncation proof needs Postgres**: SQLite in memory
can show the rule at 120 rows (already past the API's page cap) but cannot stand in for the engine
the bench claims anything about. The **filter semantics** need a real Qdrant: a fake client proves
the expression we build, never that Qdrant excludes a point lacking the key.

**Un-verifiable in this environment, named rather than promised:**

- The provider **usage field names** for all four providers (no real response in this repo; confirmed
  per provider in WU4 against a live call and recorded in the verify report).
- Both **benches** (Neon-like endpoint, real provider, 1000 rows through the CSV import): operator
  runs, recorded in `verify-report.md`, never part of the suite.
- The **Postgres-only** 1000-row read proof, which needs a container the sandbox may not have.
- The **live Qdrant** filter behaviours, behind `STORICO_TEST_LIVE_QDRANT=1` plus Docker.
- The **`has_invalid_tasks` index schema** against the pinned `qdrant_client` (pinned by WU3's first
  RED step; fallback in the decision above).

## Threat Matrix

| Threat | Mitigation | Pinned by |
| --- | --- | --- |
| The prompt silently loses the project context | `context` is a required argument; the snapshot's `project_context` comes from `template_variables`, the same dictionary the template got | Required-argument + snapshot-key tests |
| A large project is truncated in the prompt | Two new unpaginated reads with the exclusion in the `WHERE`; `list_page` is never reused | 120-row and 1000-row counts |
| An invalid task reaches the prompt as positive context | `NOT EXISTS` on active marks in the read's `WHERE`; the negative block is the only path an invalid task has | Marked-task absence + revoke-restores cases |
| Superseded versions' tasks are injected as "existing tasks" | The currency predicate rides the same statement; a cross-check ties it to (b)'s page | Cross-cutting currency test |
| The block's text is not reproducible from the stored facts | Total order in the composer (marked_at, version, normalized title, reason) | Determinism case in the composer table |
| Two normalizers drift | The composer imports (b)'s `normalize_task_title`; identity assertion | Composer test |
| A point lacking the validity key is admitted | Positive `must` on `false`, never `must_not` on `true` | Filter-shape test + live Qdrant case |
| The same story comes back as its own example | `must_not` on `user_story_id`, required keyword, fail-closed at the service without a story id | Filter + signature + service tests |
| A mark is persisted while the point still retrieves the run it condemns | The refresh runs before the relational write and raises `VectorStoreError` → 503 | Mark-refresh-failure case |
| Revoke clears the flag by assumption and re-exposes a run with another active mark | `count_active_for_extraction(exclude_mark_id=…)` and `remaining > 0` | Two-active-marks revoke case |
| The payload silently loses a key or an index | The pinned 10-key payload assertion; the index calls asserted per field | `test_vector_store.py` payload + index cases |
| The snapshot breaks the JSON column | Every `template_variables` value is JSON-native by construction; `json.dumps` asserted | Snapshot test |
| A failed run loses the input snapshot | (a)'s render-time write is untouched; only `usage` is missing | Failed-run snapshot case |
| `usage` is fabricated when the provider returned nothing | No write when `usage is None`; the key is absent, never zero | No-usage case per adapter + runner |
| A provider's field name guess records nothing | Confirmed per provider against a real response before wiring, recorded in the verify report | WU4 table (operator) |
| A custom template loses the blocks silently | Blessed opt-out; the snapshot keeps recording what was composed; `prompt_rendered` stays the authority | Opt-out case |
| A bench rejection is "fixed" by retrying or by adding a cap | Rejection recorded as a measured outcome; a review check that no cap/truncation/pagination entered the path | Verify report + `threat` review |
| The prompt snapshot duplicates ~2 MB of JSON | Accepted by decision (D8's comparability reason); recorded, not optimised | Recorded risk in the proposal |
| A non-atomic refresh leaves the flag and the marks disagreeing in the unsafe direction | Refresh-first makes every partial failure over-exclude; both directions recorded | Threat row + failure cases |
| Review budget exceeded without a delivery decision | WU1/WU3 split points; `ask-on-risk` pause | Process control, not testable |

## Migration / Rollout

1. **No migration, no backfill, no new setting, no new endpoint.** The three payload keys and the two
   payload indexes arrive through the adapter's lazy ensure, per collection. D11's wipe runs before
   the deploy that carries 0.9.0 (a's rollout), so no legacy point is expected to lack
   `has_invalid_tasks`; the fail-closed filter is what keeps that true if one does.
2. The **dev and prod collections** each get the indexes on their own first use of the adapter
   (`_get_client` → `_ensure_payload_indexes`), because each environment's adapter is built with its
   own `qdrant_collection` name (ADR-005).
3. The **benches run after the code lands and after the wipe**, on a Neon-like endpoint, per the
   plan above; their numbers go to `verify-report.md`. A rejection outcome is recorded as measured,
   and the annotated known limitation states the real number with the note that a cap is a new
   decision for the user.
4. Deploy order: (a) and (b) and (c) in one release, `alembic upgrade head` inside ADR-005's
   maintenance window. (c) adds nothing to the migration chain.
5. **Rollback** (from the proposal, by mechanism): revert the template to its two-variable form and
   drop the new template variables; revert `search_similar` and the filter and stop refreshing
   `has_invalid_tasks`; restore `ExtractionResult`/`LLMPort.generate`; restore the two ports and
   `_store_rag`. Points written while the release was live keep the extra keys harmlessly. `usage`
   and the extra `prompt_config` keys become keys nothing reads. Nothing is destructive.
   **Not reversible:** a bench run that landed in the rejection outcome burned a version number
   (D22) — that is history, and it is exactly the fact the limitation must state.

## Seams for Slices (a) and (b)

**(a) — prompt context, snapshot content, the usage write.**

- *Render's input widens, its write moment does not*: (a) states that (c) fills its snapshot keys
  "without touching `render()`'s signature"; the parent artifacts reconcile that to a single
  keyword-only `context` argument on the **input** side while the write moment, the ordering
  (render → write → provider) and `RenderedPrompt.template_variables` stay as (a) built them. This
  design is on that basis and does not re-litigate it.
- *`generate()`'s return type is amended* (see the usage decision): `tuple[list[ParsedTask], str]` →
  `ExtractionResult`. One sentence of (a)'s Interfaces section; (a)'s WU3 may implement the final
  shape directly, otherwise (c)'s WU2 changes one line and one iteration.
- *`record_usage` is added to (a)'s port family* in (c)'s WU2: it writes `prompt_config` only, so
  (a)'s "no statement names a snapshot column" rule survives intact.
- *`find_current_version`, `create_next_version`, `record_rendered_prompt`, `mark_completed`/
  `mark_failed` and `tasks.extraction_id`* are consumed as (a) defines them; (c) changes none.
- *(c) needs `version_number` in the runner* to write the point payload. **Decision:** the route
  passes it into `run_background_extraction` alongside the temperature (a)'s WU2 already adds —
  it is the same value (b) returns in the 202 body, and a retry reuses it, which is D22's "a retry
  does not mint a second number". Rejected: reading the row back with `find_by_id` before
  `_store_rag` (one extra statement and a second source for a number the row owns). If (a)'s WU2
  lands first, this is one parameter.

**(b) — marks, the gate and the delete.**

- *`list_active_on_other_versions`* is (b)'s read and (c) calls it **unchanged** with
  `exclude_extraction_id=None` for the negative block; no new mark read is invented for D7.
- *`normalize_task_title`* is (b)'s WU4 module; (c)'s WU2 imports it. If (c)'s WU2 lands first it
  waits for (b) WU4 (same release).
- *The refresh calls are added to (b)'s two mark handlers* in **(c)'s WU3**, in the order in the
  refresh decision — **before** the relational write, which corrects the proposal's "after the mark
  commits". (b)'s WU4 handler bodies gain two lines each; nothing else in (b) moves.
- *`count_active_for_extraction`* is added to (b)'s port and repository by **(c)'s WU3** (the
  proposal's Affected-Areas cell names that file), and is called by (b)'s revoke handler.
- *`VectorStoreError` and its 503 handler* are (b)'s WU3; (c)'s WU3 raises that type. If (c)'s code
  lands before (b)'s handler exists, the failure surfaces as a 500 instead of 503 — a one-line
  ordering dependency inside one release, recorded so it is not discovered in production.
- *`get_vector_store`* (`api/dependencies.py:185-202`) is the injection point the mark handlers use;
  `None` means "no refresh", exactly as the requirement's last scenario states.
- *D15's `delete_by_story`* and the refresh do not interact: the delete filters by payload
  `workspace_id + user_story_id` and never reads the validity flag, and a point-id refresh cannot
  resurrect a deleted point.
- *No UI, no HTTP contract and no new error code are (c)'s*; the 503 the refresh produces is (b)'s
  `VECTOR_STORE_UNAVAILABLE`.

## Open Questions

None. Every shape the proposal left to this phase is settled above: the `ProjectContext` value and
its argument, the two ports and their row types, the third read and its selectin cost, the
current-version-and-valid join, the negative-example read, composer, cap and wording, the Qdrant
filter and its fail-closed form, the payload keys and indexes, the refresh's caller and ordering,
the usage types and the narrow write, the template's blocks and the opt-out, and both benches.

Three items are decided **with a contingency** rather than left open, each with its trigger:

- **The project row's selectin hydration** — trigger: the 1000-story bench showing it dominating;
  fallback: a two-column projection on `ProjectRepository`.
- **`PayloadSchemaType.BOOL` for `has_invalid_tasks`** — trigger: the pinned `qdrant_client`
  rejecting it; fallback: the literal `KEYWORD` schema, which still matches `false`.
- **When (c)'s code lands before (b)'s `VectorStoreError` handler** — trigger: the refresh failing in
  an intermediate state; fallback: it answers 500 until (b)'s WU3 lands, same release.
