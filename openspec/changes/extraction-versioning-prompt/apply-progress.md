# Apply Progress — extraction-versioning-prompt

Cumulative log. WU1 part (i) — the two unbounded context ports and their repositories (tasks
1.1–1.4) — 2026-10-03, branch `feat/extraction-versioning-prompt-wu1` (tip `cd2d1d9`, the `v0.10.0`
bump on `main`; branch not switched, nothing committed or staged). Slices (a) and (b) are merged;
this tranche adds reads nothing calls yet — no production behaviour changes.

## Consumed branch / baseline facts

Parent-verified at this head, re-observed during the run: full suite
`conda run -n storico python -m pytest -m "not integration"` read **1206 passed, 36 deselected**
before the new tests; `ruff check` and `ruff format --check` clean. The `task_invalidations` table,
the current-version predicate on the task repository (`_current_version_only`, slice (b)) and
`SQLAlchemyTaskInvalidationRepository.create`/`revoke` are live and consumed, not re-invented.
Pre-existing untracked `backend/.gitignore` and `.claude/skills/` untouched.

## Completed tasks (persisted checkboxes updated in tasks.md)

- [x] 1.1 RED — `TestListForContext` in `backend/tests/test_repositories/test_user_story_repo.py`
      (4 cases): three stories minus the excluded one, projected to `(id, raw_text)`; oldest-first
      order (`created_at, id` ascending) and two-call determinism; a 120-story project returning
      **119** rows (past the API page cap of 100, which `list_page` would have applied); the
      signature pin over both `UserStoryRepository.list_for_context` and its SQLAlchemy
      implementation — no `limit`/`offset` parameter, `exclude_story_id` required and keyword-only
      (the `inspect.signature` pattern of `test_unit/test_vector_store.py:157-166`).
- [x] 1.2 RED — `TestListForContext` in `backend/tests/test_repositories/test_task_repo.py`
      (8 cases): the excluded story's tasks absent across **both** its completed versions (v1 + v2,
      both with tasks); a task with an active mark absent and the same task present again after
      revoke through the invalidation repository's `create`/`revoke` — the same path the mark
      endpoints drive; a superseded version's tasks absent when a newer completed version exists; a
      `pending` v3 above a completed v2 leaving v2's tasks current; deterministic `created_at, id`
      order; the projection `(title, status, user_story_id)` with `TaskStatus` re-hydrated; the
      currency cross-check (below); the same no-window signature pin.
- [x] 1.3 GREEN — frozen slotted `StoryContextRow(id, raw_text)` beside
      `UserStoryRepository` and `TaskContextRow(title, status, user_story_id)` beside
      `TaskRepository` (both with `status: TaskStatus` typed as the entity enum), each port gaining
      `list_for_context(project_id, *, exclude_story_id)` with a docstring stating the read is
      deliberately unbounded — the context block is not a paginated resource and a page window would
      truncate it silently — and that the exclusion rides in the `WHERE`, never in a Python filter.
      Both row types re-exported from `domain/ports/__init__.py`.
- [x] 1.4 GREEN — `SQLAlchemyUserStoryRepository.list_for_context`: the two-column projection
      `select(UserStoryModel.id, UserStoryModel.raw_text).where(project_id == :p, id != :excluded)
      .order_by(created_at, id)`. `SQLAlchemyTaskRepository.list_for_context`: **one** statement —
      `task → story` join (project scoping), the currency predicate **reused from
      `_current_version_only`** (the same "no higher-numbered completed version" shape (b)'s page
      and export reads carry — no second spelling of currency in the file), `NOT EXISTS` an active
      `task_invalidations` row (`revoked_at IS NULL`, the predicate (a)'s partial unique index
      backs), and `tasks.user_story_id != :excluded`. Both exclusions in the `WHERE`; no Python
      filtering anywhere.

## TDD Cycle Evidence

| Cycle | Test(s) | Command | Result |
| --- | --- | --- | --- |
| RED (1.1) | 4 new story cases | `conda run -n storico python -m pytest tests/test_repositories/test_user_story_repo.py -m "not integration"` | **4 failed, 23 passed** — every failure `AttributeError: type object 'UserStoryRepository' has no attribute 'list_for_context'`; all 23 pre-existing cases still collected and passed |
| RED (1.2) | 8 new task cases | `conda run -n storico python -m pytest tests/test_repositories/test_task_repo.py -m "not integration"` | **8 failed, 21 passed** — same `AttributeError` kind on `TaskRepository`; all 21 pre-existing cases green |
| GREEN (1.3+1.4) | both repository files | `conda run -n storico python -m pytest tests/test_repositories/test_user_story_repo.py tests/test_repositories/test_task_repo.py -m "not integration"` | **56 passed** (12 new + 44 pre-existing) |
| Phase runner | repo + prompt-manager + extraction API files | `conda run -n storico python -m pytest tests/test_repositories/test_user_story_repo.py tests/test_repositories/test_task_repo.py tests/test_unit/test_prompt_manager.py tests/test_api/test_extraction.py -m "not integration"` | **116 passed** |
| Full suite | whole backend | `conda run -n storico python -m pytest -m "not integration"` | **1218 passed, 36 deselected** — baseline 1206 + exactly the 12 new test functions |
| Lint | repo-documented forms | `conda run -n storico python -m ruff check src tests` / `… format --check src tests` | **All checks passed; 269 files already formatted** |

One mid-GREEN failure was mine, not the implementation's: the first draft of the mark/revoke case
put the mark on a task of the story it then excluded, so the task was hidden by the story exclusion
rather than the mark and could never "return" after revoke. The fixture was restructured (mark on
*another* story's task; the story being decomposed excluded) before GREEN completed — no assertion
was weakened to pass it.

## What each statement orders by, and why the exclusions live in the `WHERE`

- **Stories**: `ORDER BY user_stories.created_at, user_stories.id` — ascending, so the prompt reads
  the project the way it was built; `id` is the tiebreaker for rows written in the same instant, and
  the total order is what makes two runs over unchanged state compose identical context blocks.
- **Tasks**: `ORDER BY tasks.created_at, tasks.id` — same reason, same tiebreaker, asserted by a
  two-call equality case with distinct `created_at` seeds.
- **Exclusion in the `WHERE`**: the context block claims to carry the whole project; a Python filter
  over a paginated read would drop rows *before* the filter could see them (silent truncation, D23),
  and even over an unbounded read it would make correctness depend on every future caller
  remembering the promise. The story exclusion (`id != :excluded` / `user_story_id != :excluded`),
  the currency predicate and the active-mark `NOT EXISTS` are all terms of the one statement.

## Signature pins

`inspect.signature` over both halves of each port (port method + SQLAlchemy implementation): no
`limit` parameter, no `offset` parameter, `exclude_story_id` keyword-only with no default — a page
window cannot be reattached and the exclusion cannot be made optional on either side.

## The cross-check's shape

`test_matches_the_current_version_read_the_api_serves` runs at the **repository layer**, against the
same current-version read the API's `GET /tasks?workspace_id=` serves —
`list_page(workspace_id=…, limit=100, offset=0)` — not the HTTP route: a repository test file
asserts repository contracts, the route adds only the membership walk and schema on top of exactly
this read, and the phase runner keeps this file off the API fixtures. The fixture is two-version,
one-mark: story A with completed v1 (tasks `v1-plain`, `v1-marked`) and completed v2 (task
`v2-task`), story B with one completed version, story C excluded. The active mark sits **on the
superseded version's task** on purpose: both reads drop that version by currency, so their scopes
coincide and the case isolates the currency rule (the mark's own effect is the dedicated
mark/revoke case). The excluded story's page rows are dropped in the *test* only to align the two
scopes — the production read puts that exclusion in the `WHERE`.

## Measured 120-row case

A 120-story project (seeded through `save_many`) returns **119** rows minus the excluded one, with
every non-excluded story id present — past `list_page`'s cap of 100, which would have truncated.

## Files changed (this unit — code/test files 529 changed lines: 523+/6−, plus the two SDD artifacts; `git diff --numstat`)

- `backend/src/storico/domain/ports/user_story_repository.py` (+28/−0)
- `backend/src/storico/domain/ports/task_repository.py` (+34/−1)
- `backend/src/storico/domain/ports/__init__.py` (+4/−2)
- `backend/src/storico/infrastructure/database/repositories/user_story_repository.py` (+24/−1)
- `backend/src/storico/infrastructure/database/repositories/task_repository.py` (+44/−1)
- `backend/tests/test_repositories/test_user_story_repo.py` (+105/−0)
- `backend/tests/test_repositories/test_task_repo.py` (+284/−1)
- `openspec/changes/extraction-versioning-prompt/tasks.md` (+4/−4 — checkboxes 1.1–1.4 only)
- `openspec/changes/extraction-versioning-prompt/apply-progress.md` — new (this file)

Larger than the ≈320-line part-(i) estimate: the 12 pinned scenarios forced ≈390 test lines against
the forecast's sharing of WU1's ≈750 across its three parts. No `size:exception` claimed — the part
ends on a green suite and the budget question belongs to the whole WU1 PR (parts i+ii+iii).

## Deviations from design / task letter

1. **Currency spelling**: the design's sketch joins an explicit `E`/`N` alias pair; the implemented
   statement reuses the file's existing `_current_version_only(scope)` predicate (slice (b)'s
   "no higher-numbered completed version" `NOT EXISTS` form) per the task letter's reuse rule —
   behaviourally the same predicate, one spelling in the file. The task letter's stop-condition
   (reuse impossible without changing the predicate's behaviour) did not trigger.
2. **Cross-check layer**: repository layer against `list_page`'s workspace scope, as the task letter
   directs; the design's `GET /tasks?workspace_id=` wording is served by exactly that read.
3. **Format**: two hand-applied whitespace fixes (a signature wrapped over three lines, two wrapped
   `seed_extraction` calls) after `ruff format --check` flagged them; no formatter was executed,
   the fixes are the exact lines the diff named.

## Remaining unchecked tasks (exact lines from tasks.md)

- [ ] 1.5 through 1.15 (RED/GREEN/TRIANGULATE/REFACTOR of `ProjectContext`, `render(context=…)`,
      the template blocks and the call-site churn) — part (ii) and part (iii) of WU1, untouched.
- Phases 2–5: untouched.

## Risks

- The task-context statement is a third expression of the currency rule (b's story scope, b's
  workspace scope, this read) — the cross-check ties it to (b)'s page at the repository layer; the
  1000-row Postgres scale proof (1.14) and the live-Qdrant work belong to later tasks and were not
  run here (no Docker daemon in this environment; `-m integration` never invoked).
- `list_for_context` has no caller yet (part (ii) wires it); until then the only proof of the
  statements is the repository layer itself.

---

## W1-T2 — `ProjectContext`, the required `context` argument, the two template blocks, the churn (tasks 1.5–1.10)

2026-10-03, same branch `feat/extraction-versioning-prompt-wu1`, part (i)'s tip `b09272e` untouched
below this work. Nothing committed or staged by this run.

### Consumed branch / baseline facts

Parent-verified baseline at `b09272e` re-observed through the run's end state: full suite
`conda run -n storico python -m pytest -m "not integration"` read **1218 passed, 36 deselected**
before this tranche's tests and **1227 passed, 36 deselected** after — the delta is exactly the
9 new test functions (5 template cases + 4 runner/context cases). `ruff check` and
`ruff format --check` clean at both points (269 files formatted). Part (i)'s two ports
(`list_for_context` on both, the row types re-exported) were consumed as shipped; `prompt_manager.py`
was read and confirmed to need no change — `render_instruction` renders with `**kwargs` verbatim
and the Jinja environment uses the default undefined, so a workspace template that never mentions
the new variables renders with them simply unused.

### TDD cycle evidence

| Cycle | Task(s) | Command | Result |
| --- | --- | --- | --- |
| RED | 1.5 (5 template cases in `test_unit/test_prompt_manager.py`) | `conda run -n storico python -m pytest tests/test_unit/test_prompt_manager.py -m "not integration"` | **3 failed, 16 passed** — the content/order/omission cases failed on `assert '## Project Context' in result` / the negative header / the omission sentence; the two absent-block cases (nothing marked; the opt-out template) passed trivially against the old template, as `{% if %}`-guarding predicts |
| RED | 1.7 (4 runner/context cases in `test_api/test_extraction.py`) | `conda run -n storico python -m pytest tests/test_api/test_extraction.py -m "not integration"` | **4 failed, 46 passed** — the three prompt-content cases failed on the missing `## Project Context` block in the stored `prompt_rendered`; **the required-argument case failed `DID NOT RAISE TypeError`** — i.e. at RED a `render()` call without `context` succeeded silently, which is precisely the hole the required argument closes |
| GREEN | 1.6 (template) | `conda run -n storico python -m pytest tests/test_unit/test_prompt_manager.py tests/test_few_shot_examples.py -m "not integration"` | **31 passed** — the template cases turned green and `test_few_shot_examples.py`'s three direct `render_instruction` sites stayed green untouched |
| GREEN | 1.8+1.9+1.10 | phase runner (below) | **125 passed** |
| Full suite | whole backend | `conda run -n storico python -m pytest -m "not integration"` | **1227 passed, 36 deselected** — baseline 1218 + exactly the 9 new test functions |
| Lint | repo-documented forms | `conda run -n storico python -m ruff check src tests` / `… format --check src tests` | **All checks passed; 269 files already formatted** |

One mid-GREEN failure was mine: the first pass left `test_extract_forwards_instruction_template`'s
multi-line `render()` call without the new argument (`TypeError: missing 1 required keyword-only
argument: 'context'`). The call site was completed — the failure was the churn missing a site, not
an assertion relaxed.

### The blocks as built (task 1.6)

Insertion point: immediately after the format instructions, before the existing
`{% if examples %}` section — which, `Now break down the following user story:` inside it, and
`{{user_story}}` are byte-for-byte untouched. Order in the template, each block guarded by its own
`{% if %}`:

1. `{% if project_context %}` → `## Project Context` — `Project: {{ project_context.name }}`,
   `Description: {{ project_context.description }}`, then one `- {{ story.raw_text }}` line per
   other story and one `- {{ task.title }} (story: {{ task.user_story_id }})` line per
   current-version valid task (Jinja's dict-attribute fallback reads the JSON-native variables;
   list-item lines carry the loop tags inline so no blank lines appear between items).
2. `{% if negative_examples %}` → `## Do Not Produce These Tasks (Previously Marked Invalid)` —
   intro sentence, then `- {{ example.title }} — reason: {{ example.reason }} (version
   {{ example.version_number }})` per mark (em dash, matching design.md's rendered example), and
   when `negative_examples_omitted` is truthy the English closing sentence
   `{{ negative_examples_omitted }} older marks were omitted.` — the source spec's Spanish wording
   deliberately corrected, every model-facing block in this template being English. Ships empty
   until WU2 wires the marks read; D7's block-composition requirement stays WU2's.
3. The existing `## Few-Shot Examples` section, unchanged.

Verified by rendering through the real `PromptManager` during GREEN: with marks and examples the
output matches design.md's rendered example block for block, and the block order assertion pins
context → negative → few-shot → `User story:`.

### The required argument and the context build (1.7 RED / 1.8 / 1.9)

- `ProjectContext` is a frozen slotted dataclass beside `FewShotConfig` in
  `extraction_service.py` with exactly the contracted fields;
  `as_template_variables()` returns the four-key `project_context` dictionary and does the
  `UUID → str` / `TaskStatus → str` conversion at that boundary (and nowhere else).
  **One deviation, mechanical not contractual:** the `negative_examples` field is annotated
  `tuple[NegativeExample, ...]` via a `TYPE_CHECKING`-only import of
  `storico.domain.services.negative_examples` — the module is WU2's file and does not exist yet,
  and creating it (or a placeholder type here) was outside this unit's surfaces. With
  `from __future__ import annotations` the annotation is a string at runtime; the tuple itself is
  always `()` until WU2. `prompt_kwargs["negative_examples"]` is therefore
  `list(context.negative_examples)` — rendered, never snapshotted — and WU2 task 2.4 replaces it
  with the composer's rendering.
- `render()` gained the **required** keyword-only `context: ProjectContext` (no default), and
  `prompt_kwargs` — which is `RenderedPrompt.template_variables` — is exactly the contracted five
  entries (`user_story`, `project_context`, `negative_examples`, `negative_examples_omitted`,
  `few_shots` as `[asdict(example) for example in examples]`), plus the unchanged `examples` text
  when there are examples. `RenderedPrompt` unchanged.
- The runner (`_run_extraction`) builds the context between the story load and `render()`: the
  project row through the existing `ProjectRepository.find_by_id(story.project_id)` (its
  `workspace_id` ignored), both new port methods with `exclude_story_id=story.id`, and a missing
  project row degrades to empty name/description rather than failing the run (SQLite enforces no
  FK, so a dangling `project_id` is reachable in tests; Postgres makes it unreachable). Until 2.5,
  `negative_examples=()` and `negative_examples_omitted=0` are the defaults.

### The required-argument churn (1.10)

Shared builder in `backend/tests/_helpers.py`:

```python
def simple_context(**overrides: object) -> ProjectContext:
    """name="Test Project", description="A test project description", empty row tuples;
    keyword overrides pass straight through (other_stories/existing_tasks take row tuples)."""
```

Files that took it, with call-site counts:

- `tests/test_services/test_extraction_service.py` — 10 `render()` sites + the two
  `assert_called_once_with(...)` assertions on `render_instruction` re-pointed to the widened
  kwargs (`project_context=simple_context().as_template_variables()`, `negative_examples=[]`,
  `negative_examples_omitted=0`, `few_shots=[]`). No assertion count or status was relaxed.
- `tests/test_services/test_workspace_prompt_resolution.py` — 1 site (the call site neither design
  table names).
- `tests/test_unit/test_few_shot_retrieval.py` — 11 sites.
- `tests/test_extraction_flow_few_shot.py` — 2 sites.
- `tests/test_integration/test_few_shot_rag_qdrant.py` — 1 site (`_extract` helper).
- `tests/test_api/test_extraction.py` — new cases only; the file had no direct `render()` call
  sites (the runner is exercised through `run_background_extraction`, which builds its own context).

`tests/test_few_shot_examples.py` needed **nothing**: it calls `render_instruction` directly with
its own kwargs, the new blocks are `{% if %}`-guarded, and its three cases were confirmed green
after the template change (within the 31-passed focused run and again in the full suite).

### Files changed (this unit — `git diff --numstat`: 543 changed lines, 527+/16−)

- `backend/src/storico/domain/services/extraction_service.py` (+75/−3)
- `backend/src/storico/infrastructure/llm/prompts/task_generation.j2` (+15/−1)
- `backend/src/storico/infrastructure/tasks/extraction_task.py` (+28/−1)
- `backend/tests/_helpers.py` (+24/−0)
- `backend/tests/test_api/test_extraction.py` (+220/−1)
- `backend/tests/test_extraction_flow_few_shot.py` (+3/−0)
- `backend/tests/test_integration/test_few_shot_rag_qdrant.py` (+2/−0)
- `backend/tests/test_services/test_extraction_service.py` (+23/−10)
- `backend/tests/test_services/test_workspace_prompt_resolution.py` (+2/−0)
- `backend/tests/test_unit/test_few_shot_retrieval.py` (+12/−0)
- `backend/tests/test_unit/test_prompt_manager.py` (+123/−0)
- `openspec/changes/extraction-versioning-prompt/tasks.md` (+6/−6 — checkboxes 1.5–1.10 only)
- `openspec/changes/extraction-versioning-prompt/apply-progress.md` — this section appended

Format note: `ruff format` was never executed; after the first draft, `ruff format --check` and
`ruff check` diffs were read and every named line was applied by hand (wrapped imports and calls,
joined comprehensions, and two inline `select` blocks replaced by the file's existing
`_extraction_rows` helper — a reuse, not a weakening).

### Deviations from the design / task letter

1. **`NegativeExample` forward reference** (above): `TYPE_CHECKING` import of WU2's future module;
   the field, its default and its semantics are exactly as contracted. The only alternative within
   the surfaces was an untyped placeholder annotation, which would have drifted from the design's
   dataclass sketch.
2. **Missing project row fallback**: the design's four-read composition assumes the project row
   exists; the runner degrades to empty strings when it does not, because the extraction should
   still render and record rather than die on a dangling id SQLite permits.

### Remaining unchecked tasks

- [ ] 1.11–1.15 (part (iii): the four TRIANGULATE cases and the REFACTOR confirmation) — untouched.
- Phases 2–5: untouched.

### Risks

- `negative_examples` in `prompt_kwargs` carries raw row objects until WU2 lands the composer; the
  tuple is always empty on every path today, so nothing non-JSON ever reaches
  `template_variables`, but the WU2 diff must replace that entry.
- The 1000-row Postgres scale proof (1.14) and the opt-out snapshot cross-check (1.13's record
  half) still belong to part (iii); no integration marker was run in this environment.

---

## W1-T3 — the triangulations and the closing refactor (tasks 1.11–1.15)

2026-10-03, same branch `feat/extraction-versioning-prompt-wu1`, part (ii)'s tip `3240b5b` untouched
below this work. Nothing committed or staged by this run. **Evidence-only tranche**: no production
file was touched (`backend/src/**` stayed out of the diff), and the two pre-existing untracked
entries (`backend/.gitignore`, `.claude/skills/`) were left alone.

### Consumed branch / baseline facts

Parent-verified baseline at `3240b5b` re-observed: full suite
`conda run -n storico python -m pytest -m "not integration"` read **1227 passed, 36 deselected**
before this tranche's tests and **1231 passed, 39 deselected** after — the delta is exactly the
4 new unit-layer test functions (1.11, 1.12, and 1.13's two cases); the deselected count rose by
exactly the 3 new integration cases in `test_context_ports_scale.py`, which skip locally and are
deselected by `-m "not integration"`. `ruff check` clean and `ruff format --check` clean (270 files
formatted — 269 plus the new integration file). Part (i)'s and part (ii)'s commits were consumed as
shipped: both `list_for_context` reads with their `WHERE` exclusions, `ProjectContext`, the required
`context` argument, the two template blocks, and the runner composing the context between the story
load and the render.

### TDD cycle evidence (kind: TRIANGULATE/REFACTOR — GREEN-only, exception stated)

These five tasks pin and confirm behaviour that parts (i)/(ii) already landed; none of them
changes production code. A RED observation would have required mutating a `backend/src` file to
break working behaviour, which this unit's surfaces forbid — so no RED was observed and none is
claimed. Verification is the GREEN and TRIANGULATE evidence below.

| Cycle | Task(s) | Command | Result |
| --- | --- | --- | --- |
| GREEN | 1.11 + 1.12 + 1.13 (2 cases) | `conda run -n storico python -m pytest tests/test_api/test_extraction.py -m "not integration"` | **54 passed** (50 pre-existing + 4 new) |
| GREEN | 1.13 (template half, pre-existing) + repo halves | phase runner (below) | **129 passed** |
| GREEN | 1.15 confirmation run | `conda run -n storico python -m pytest tests/test_few_shot_examples.py -m "not integration"` | **12 passed** — the three direct `render_instruction` sites green untouched with the optional blocks in the template |
| Phase runner | 1.11–1.15 | `conda run -n storico python -m pytest tests/test_repositories/test_user_story_repo.py tests/test_repositories/test_task_repo.py tests/test_unit/test_prompt_manager.py tests/test_api/test_extraction.py -m "not integration"` | **129 passed** |
| Integration | 1.14 | `conda run -n storico python -m pytest tests/test_integration/test_context_ports_scale.py -m integration -q` | **3 skipped** — every case `SKIPPED [1] … Docker daemon unreachable — this integration test needs docker to spawn a Postgres container via testcontainers.` This machine has no Docker daemon; the scale proof stays unverified here, and **CI owns these cases' verdict** (GitHub runners have a daemon) |
| Full suite | whole backend | `conda run -n storico python -m pytest -m "not integration"` | **1231 passed, 39 deselected** — baseline 1227 + exactly the 4 new test functions; deselected 36 → 39 = the 3 new integration cases |
| Lint | repo-documented forms | `conda run -n storico python -m ruff check src tests` / `… format --check src tests` | **All checks passed; 270 files already formatted** |

Two mid-GREEN failures were mine, not the implementation's: the first draft of 1.11 read the story's
*seeded* v1 row instead of the run's row (the story now carries a prior extraction, so
`rows[0]` is no longer the run — the selection now pins `row.id == pending.id`), and the first draft
of 1.12 seeded the decomposing stories' task with the title `Set up database schema`, which is a
substring of the template's own few-shot format example (`Set up database schema for transactions`)
and made an absence assertion pass vacuously — the title moved to `Configure the billing database`
in that case. No assertion was weakened; 1.11 keeps the letter's `Set up database schema` title,
where the positive presence is carried by the `(story: {other_story})` pairing the template example
cannot fake. One 1.13 draft asserted `rendered.text` equality that ignored the `system_prompt=None`
two-newline prefix — replaced with an `instruction` equality. Formatting: `ruff format` was never
executed; four lines the `--check --diff` named were applied by hand.

### The 1.11 / 1.12 inventory — what already existed, what was added

Checked before writing, as instructed; the repo-level letters were already satisfied by part (i)'s
cases, so **nothing was added to `test_repositories/test_task_repo.py`** — duplicating them would
have weakened the inventory, not the suite.

- **1.11, read level — already existed**: `test_task_repo.py::TestListForContext::
  test_the_excluded_story_is_absent_in_every_version` (excluded story with completed v1 + v2, both
  with tasks; neither version's tasks return — the `WHERE` exclusion holding across every version at
  once). The story-side half is `test_user_story_repo.py::TestListForContext::
  test_returns_the_other_stories_and_never_the_excluded_one`. **Added**: the end-to-end prompt
  case `test_api/test_extraction.py::TestExtractionPromptCarriesTheProject::
  test_a_storys_own_completed_tasks_never_enter_its_own_context_block` — the decomposed story has a
  completed v1 producing `Implement login retry`; its own next prompt never carries that title while
  a different story's `Set up database schema` does, paired with `(story: {other_story})`; the
  story's raw text appears exactly once, as the story to decompose.
- **1.12, read level — already existed**: `test_task_repo.py::TestListForContext::
  test_an_active_mark_hides_the_task_and_revoking_restores_it` (another story's task hidden by an
  active mark created through `SQLAlchemyTaskInvalidationRepository.create`, restored after
  `revoke`). **Added**: the prompt-level case `test_api/test_extraction.py::
  TestExtractionPromptCarriesTheProject::
  test_an_invalid_task_leaves_every_context_block_and_returns_after_revoke` — a three-story fixture
  where the marked story is never itself run (a completed run for it would mint a newer version and
  retire the marked task by currency, which is the read-level case above, not this one); the marked
  task is absent from **both** other stories' prompts while the mark is active, returns to the block
  after revoke through the same write path the endpoint drives (paired with its owning story id),
  and the decomposing story's own valid task stays excluded throughout — own-story exclusion and
  validity are independent `WHERE` terms.

### The 1.13 opt-out — the two stored facts and where each was read

- **Fact 1 — what the provider received**: the row's `prompt_rendered` column, read back from
  `extractions` after the run (`test_the_opt_out_run_completes_and_the_row_records_what_each_fact_saw`):
  status `completed`, the story text present, `## Project Context` and
  `## Do Not Produce These Tasks (Previously Marked Invalid)` absent, and the other story's raw text
  and task title absent although that data existed in the project when the context was composed.
- **Fact 2 — what was composed**: at this head the runner snapshots `prompt_config` as
  `{validate, system_prompt}` (WU2 task 2.5 owns filling it from `RenderedPrompt.template_variables`),
  so the row-level half of fact 2 is asserted as the composed config that survives
  (`prompt_config["system_prompt"]`, read from the row), and the `template_variables` half is
  asserted at the render boundary (`test_the_opt_out_templates_variables_still_carry_the_composed_context`:
  `template_variables["project_context"]["name"]` and `["negative_examples_omitted"]` present while
  the rendered text carries neither block). **Sequencing note for the parent**: the full
  two-stored-facts comparison the brief describes — `prompt_config.project_context` and
  `prompt_config.negative_examples_omitted` read back from the row — becomes assertable only once
  2.5 writes the snapshot from `template_variables`; asserting it now would have been RED against
  production and out of this unit's evidence-only surfaces. 2.6 already carries the row-level
  read-back (`prompt_config["negative_examples_omitted"] == 1`). The template half was already green:
  `test_unit/test_prompt_manager.py::TestTaskGenerationContextBlocks::
  test_a_workspace_template_without_the_variables_renders_neither_block` (part (ii)'s 1.5). No
  runtime warning exists and none was added — the spec blesses the opt-out.

### The new integration file (1.14) — `backend/tests/test_integration/test_context_ports_scale.py`

Three cases, each `@pytest.mark.integration` + the `_docker_reachable()` skipif copied from
`test_migration_chain.py` (copy-not-share, that module's own documented reason), each with
`loop_scope="module"` sharing one Postgres 16 testcontainer and the enum-type shim of
`test_projects_integration.py`:

1. `test_the_story_read_returns_999_of_1000_without_the_excluded_one` — 999 rows, equal to the
   table's own `count(*)` for the project minus one, none carrying the excluded id.
2. `test_the_task_read_returns_every_valid_current_version_task_without_a_limit` — one completed
   run with one task per story, no marks: 999 tasks, 999 distinct owning story ids, past the API's
   page cap of 100 (the signature pin against `limit`/`offset` stays at the unit layer).
3. `test_two_calls_over_the_same_state_are_byte_identical` — both reads equal twice.

**Observed local status: 3 skipped** (Docker daemon unreachable — the reason string above). CI owns
their verdict; a skip here proves nothing about scale.

**What the plan letter's "created through the CSV import" became, and why**: no container
integration file wires the FastAPI app, its Auth.js bearer-JWT dependency and a workspace membership
against a live server — they drive repositories and entities directly — and building that HTTP/auth
scaffolding was not this file's job. What runs instead is the import's **own write path, minus only
the HTTP and auth shell**: `parse_story_csv` decodes a generated 1000-row parts CSV (exactly at the
parser's `MAX_ROWS` cap), `validate_import` classifies it (blocked-assertion included), and the
stories persist through the same `save_many` commit `import_stories` executes. The rows enter
through the import machinery, not hand-built model inserts; the module docstring states this same
substitution.

### The 1.15 confirmations — what was read to make each

- **Exactly one context-construction site**: `grep -rn "ProjectContext(" backend/src` matches only
  `infrastructure/tasks/extraction_task.py:410` — the runner. No other production site composes one.
- **No read path filters in Python**: both implementations were read in full —
  `user_story_repository.list_for_context` (two-column projection; `project_id == :p` and
  `id != :excluded` as `WHERE` terms, `ORDER BY created_at, id`, rows returned as they come) and
  `task_repository.list_for_context` (one statement: the `task → story` join, the currency predicate
  reused from `_current_version_only`, the active-mark `NOT EXISTS`, and `user_story_id != :excluded`
  — all four in the `WHERE`; the docstring itself names the Python-filter trap). No `if`-filter sits
  between either statement and its return.
- **The two port methods appear in no paginated caller**: `grep -rn "list_for_context" backend/src`
  matches the two ports, the two implementations, and exactly two call sites — both in the runner
  (`extraction_task.py:404,407`), neither adjacent to any `list_page`/`fetch_page` window; the only
  `fetch_page` use remains `list_page`'s own body.
- **`test_few_shot_examples.py` still green**: 12 passed (run listed above) — the three direct
  `render_instruction` sites are unaffected by the `{% if %}`-guarded optional blocks.

### Files changed (this unit — final `git diff --numstat`: 520 tracked changed lines, 514+/6−, plus the new integration file)

- `backend/tests/test_api/test_extraction.py` (+331/−1 — 4 new test functions)
- `backend/tests/test_integration/test_context_ports_scale.py` — new file, 288 lines (untracked, so
  outside `git diff --numstat`; unit total including it: 808 changed lines)
- `openspec/changes/extraction-versioning-prompt/tasks.md` (+5/−5 — checkboxes 1.11–1.15 only)
- `openspec/changes/extraction-versioning-prompt/apply-progress.md` — this section appended
  (+178/−0, earlier sections verbatim)

### Deviations from the design / task letter

1. **1.13's snapshot half** (detailed above): asserted at the boundaries that exist at this head;
   the row-level `prompt_config` context keys land with WU2's 2.5 write and 2.6's read-back. This
   tranche adds no production code to make the comparison possible early.
2. **1.14's import path** (detailed above): the import's parse → validate → `save_many` write path
   against the container instead of the HTTP endpoint, for the scaffolding reason the brief's
   escape hatch anticipates; documented in the module docstring, not silently substituted.

### Remaining unchecked tasks

- Phases 2–5: untouched (2.1 onward). Phase 1 is complete: 1.1–1.15 all checked.

### Risks

- The three scale cases have never executed anywhere yet — locally they skip by design and CI has
  not run this branch. Until they pass on a runner with a daemon, 1.14's proof is structural, not
  observed.
- 1.13's full two-stored-facts comparison is split across this tranche (row fact 1, boundary fact 2)
  and WU2 (2.5's snapshot write, 2.6's row-level read-back); a reviewer of WU2 should re-read this
  section before judging 2.6's coverage.

## W2-T1 — the negative-example composer and its unit table (tasks 2.1–2.2)

The first part-i tranche of WU2 under the amended 2026-10-03 boundaries: **part i = 2.1–2.2 only** —
the pure composer and its unit table. No wiring: `ProjectContext.negative_examples` stays the
always-empty tuple WU1 shipped, `extraction_service.py`, `extraction_task.py`, the Jinja template and
the normalizer are untouched, and 2.3–2.11 remain unchecked.

### Consumed branch / baseline facts

- Branch `feat/extraction-versioning-prompt-wu2a`, tip `8f2b366` (not switched, not staged, not
  committed by this unit). Pre-existing untracked `.claude/skills/` and `backend/.gitignore` observed
  and preserved.
- Measured baseline before any edit (parent-supplied, re-confirmed by the full-suite run below):
  1231 passed, 39 deselected; ruff check clean; ruff format 270 files clean.

### RED (task 2.1) — observed failure kinds and counts

Command:
`cd backend && conda run -n storico python -m pytest tests/test_unit/test_negative_examples.py -m "not integration"`.

- First observed RED: **collection error, 1 error** —
  `ModuleNotFoundError: No module named 'storico.domain.services.negative_examples'` (the import in
  the test file is the failing act; nothing else in the suite was touched).
- The RED table then written is **7 test functions**, all of which failed for that one import reason
  before the module existed (module-level import, so the whole file fails together — the RED shape of
  a new-module unit).

### GREEN (task 2.2) — the composer as built

`backend/src/storico/domain/services/negative_examples.py` **New**: `MAX_NEGATIVE_EXAMPLES = 20` as a
module constant (no column, no `workspace_prompts` field, no parameter — a workspace knob would let a
workspace silently re-break D19), frozen slotted `NegativeExample(title, reason, version_number,
marked_at)` and `NegativeExampleBlock(examples, omitted)` with `as_template_variables()`, and
`compose_negative_examples(candidates) -> NegativeExampleBlock` as sort → dedupe → cap → omitted.

- **The sort is total**, not merely sorted: `marked_at DESC` → `version_number DESC` →
  `normalize_task_title(title)` → `reason`, implemented as one tuple key
  (`-marked_at.timestamp()`, `-version_number`, normalized title, reason). Proven by the tie-heavy
  fixture: 8 candidates all sharing one `marked_at` compose **byte-identically twice**
  (`json.dumps(block.as_template_variables())` equal across two compositions), and additionally a
  **reversed copy of the same input** composes byte-identically to the original — input order cannot
  leak into the snapshotted text.
- **Dedupe-before-cap**: a single pass over the ranked list dedupes on
  `(normalize_task_title(title), reason)` keeping the first seen — which, in `marked_at DESC` order,
  **is the most recent** of each pair; the same normalized title with a different reason is two
  entries (asserted). `omitted = deduped_total - taken`, so it counts only what the cap dropped,
  never what dedupe collapsed: the 5-candidate case contains a duplicate pair (deduped total 4,
  under the cap) and asserts `len(examples) == 4, omitted == 0`; the 21-distinct case asserts
  `len == 20, omitted == 1` with `examples[0].title == "Task number 20"` (most recent first).
- **`as_template_variables()` is JSON-native end to end**: `marked_at` serializes via
  `isoformat()` (asserted to be a `str` equal to the source timestamp's ISO form; title, reason and
  version number pass through), and the whole list survives `json.dumps` — asserted directly.
- **Import identity, how proved**: two assertions. (1) Identity of objects —
  `negative_examples.normalize_task_title is task_title_normalizer.normalize_task_title` on the
  module's own namespace, so a re-export under a different spelling or a local copy fails it.
  (2) Source check — `inspect.getsource` of the module must contain no `casefold`, no `lower(`, no
  `\s` regex and no `re.compile`: no second casefold or whitespace spelling can live there. Both live
  in `test_module_reuses_the_normalizer_and_defines_no_second_one`.
- No session, no I/O, no repository, no new mark read: the module's imports are
  `TaskInvalidationCandidate` (b's port type, consumed not redefined) and `normalize_task_title`.

### TRIANGULATE (folded into the RED table, per the plan's composer coverage C5/C6)

Covered as separate cases: dedupe-with-different-reason-stays-two; the reversed-input byte-identity;
the post-dedupe `omitted == 0`; the empty input (`examples == ()`, `omitted == 0`); the JSON-native
shape. No refactor round was needed — the module landed at its final shape.

### Files changed (this unit — `git diff --numstat` 2/2 tracked, plus two new untracked files)

- `backend/src/storico/domain/services/negative_examples.py` — **New**, 104 lines (untracked, outside
  `git diff --numstat`)
- `backend/tests/test_unit/test_negative_examples.py` — **New**, 172 lines (untracked, outside
  `git diff --numstat`)
- `openspec/changes/extraction-versioning-prompt/tasks.md` (+2/−2 — checkboxes 2.1 and 2.2 only)
- `openspec/changes/extraction-versioning-prompt/apply-progress.md` — this section appended, earlier
  sections verbatim

Unit changed-line count: **276 added lines** (104 + 172 code/test, both untracked so invisible to
`git diff --numstat`) + 4 tracked changed lines in the two SDD artifacts (`--numstat`: 2/2).

### Verification (each run after the manual format edits, in this order)

- `cd backend && conda run -n storico python -m pytest tests/test_unit/test_negative_examples.py -m "not integration" -q` → **7 passed**
- `cd backend && conda run -n storico python -m pytest tests/test_unit tests/test_api/test_extraction.py -m "not integration" -q` → **540 passed**
- `cd backend && conda run -n storico python -m pytest -m "not integration" -q` → **1238 passed, 39 deselected** — delta against the 1231 baseline is exactly the 7 new test functions
- `cd backend && conda run -n storico python -m ruff check src tests` → **All checks passed!**
- `cd backend && conda run -n storico python -m ruff format --check src tests` → **272 files already formatted**

Formatting note: the two new files needed reformatting on the first `ruff format --check` (three
over-long lambda/assert spellings). The formatter was **not** run (task letter forbids formatters);
the exact changes ruff's `--diff` output showed were applied by hand, then re-verified clean.

### Remaining unchecked tasks

- 2.3–2.11 (part ii = 2.3–2.6, part iii = 2.7–2.11): all still `[ ]`, including the dated amendment
  under the Phase 2 header, untouched.
- Phases 3–5: untouched.

### Risks

- None observed: the unit is pure and additive; the full-suite delta is exactly the 7 new tests, and
  no existing assertion was touched. Part (ii) still has to wire the composer's output into
  `ProjectContext` — until then the block renders empty and the composer has no production caller.

## W2-T2 — the negative block stops being empty and the snapshot records what was composed (tasks 2.3–2.6)

2026-10-03, branch `feat/extraction-versioning-prompt-wu2a` (tip `9b513e9`; branch not switched,
nothing committed or staged). WU2 part (ii) per the dated amendment: 2.3's block-level RED together
with the wiring that turns it green (2.4, 2.5), plus 2.6's row-level read-back. The composer of
W2-T1 finally gets its production caller; 2.7–2.11 (part iii) and every later phase remain untouched.

### Consumed branch / baseline facts

Parent-verified at this head, re-observed during the run: full suite
`conda run -n storico python -m pytest -m "not integration"` read **1238 passed, 39 deselected**
before the new tests; `ruff check` clean and `ruff format --check` read 272 files already formatted.
The only mark read used is (b)'s `list_active_on_other_versions(*, user_story_id,
exclude_extraction_id)`, called with `exclude_extraction_id=None` — exactly D7's row set for the
story, no second mark read invented. Pre-existing untracked `backend/.gitignore` and
`.claude/skills/` untouched. Nothing outside the seven allowed edit surfaces was modified.

### RED (tasks 2.3 and 2.6 written first, before any wiring)

14 new test functions added to `backend/tests/test_api/test_extraction.py` in two classes
(`TestNegativeExampleBlockOnTheLivePath` — 5 cases, `TestTheSnapshotRecordsWhatWasComposed` — 9
cases, plus the appended row-level half of 1.13 inside `TestWorkspaceTemplateOptOutAtTheRecord`).
Prove-RED run:
`cd backend && conda run -n storico python -m pytest tests/test_api/test_extraction.py -m "not integration" -q`
→ **12 failed, 56 passed**. Failure kinds, exactly as expected:

- **Block-level (2.3): `ValueError: substring not found`** — `_negative_block()` indexes the
  `## Do Not Produce These Tasks (Previously Marked Invalid)` header in the stored
  `prompt_rendered`, and the header never renders because the block ships empty (WU1's part (ii)
  state: the context carries no marks). Four 2.3 cases failed this way; the fifth (the no-knob
  column-set assertion) passed at RED because it pins the model's schema, which was already correct.
- **Snapshot-level (2.6): the snapshot carrying only the two inherited keys** — the six-key set
  assertion failed with `assert {'system_prompt', 'validate'} == {six keys}`; the story-edit and
  few-shots cases failed with `KeyError: 'story_text'` and `KeyError: 'few_shots'`; the opt-out
  row-level case failed with `None == 'Seeded Project'` on `prompt_config.get("project_context")`.
- Already-true pins that passed at RED, by design: the two-different-prompts case (the context block
  was wired in WU1, so a new story already changes the prompt) and the middleware-list case
  (`[CORSMiddleware]` was already the app's only middleware). They are recorded as structural pins,
  not as RED evidence.

### GREEN (2.4 + 2.5) and where the render-time mapping lives

- `backend/src/storico/domain/services/negative_examples.py`: **`negative_examples_as_template_variables(examples)`**
  is the ONE place the `NegativeExample → JSON-native dict` conversion lives; `NegativeExampleBlock.
  as_template_variables()` now delegates to it. Not duplicated: the service builds
  `prompt_kwargs["negative_examples"]` through the same module function, so the template's block, the
  block's own variables and the render kwargs cannot drift — there is no second mapping anywhere in
  the tree.
- `backend/src/storico/domain/services/extraction_service.py` (2.4): `prompt_kwargs["negative_examples"]`
  is now the composer's JSON-native mapping of `context.negative_examples` (it was a list of raw
  dataclasses); `few_shots` stays `[asdict(example) for example in examples]` — verified to be the
  vector port's own five fields (`user_story_text`, `tasks_summary`, `model_used`,
  `confidence_score`, `similarity_score`), text and never an id, and snapshot-only: the template
  renders the few-shot section from `examples`, never from `few_shots` (asserted on the row: the
  rendered prompt carries the example text but never a dict repr like `'user_story_text'`).
- `backend/src/storico/infrastructure/tasks/extraction_task.py` (2.5): the runner's fourth read is
  `SQLAlchemyTaskInvalidationRepository.list_active_on_other_versions(user_story_id=story.id,
  exclude_extraction_id=None)`, fed through `compose_negative_examples`; the block's
  `examples`/`omitted` fold into the `ProjectContext` it already builds. The snapshot dictionary is
  written **from `rendered.template_variables`** — `few_shots`, `project_context`, `story_text`
  (=`template_variables["user_story"]`), `negative_examples_omitted` — beside the inherited
  `validate` and `system_prompt`, in (a)'s `record_rendered_prompt` call. **The ordering render →
  write → provider did not move.**
- **The six-key snapshot and what `negative_examples` deliberately is not**: the stored
  `prompt_config` key set is exactly `{validate, system_prompt, few_shots, project_context,
  story_text, negative_examples_omitted}` (asserted with a set equality on a full context — marks,
  another story's task — plus `json.dumps(snapshot)` succeeding). `negative_examples` is **not** a
  snapshot key: the block itself travels in `prompt_rendered` and is re-derivable from the marks, so
  copying it into `prompt_config` would store it twice.

### The no-knob assertion's shape (C6)

Two assertions on the schema, not on today's behaviour:
`{c for c in WorkspacePromptModel.__table__.columns if c.startswith("few_shot")} ==
{"few_shot_enabled", "few_shot_limit", "few_shot_threshold"}` (the three few-shot knobs are the only
retrieval knobs the row owns) and `not [c for c in columns if "negative" in c or "cap" in c]` with
`[c for c in columns if "limit" in c] == ["few_shot_limit"]` (no field can move the composer's
constant — a future column cannot quietly appear the way a behaviour-only assertion would tolerate).
The behavioural half rides alongside: with `few_shot_limit = 25` upserted, 25 marks still compose 20
entries and the block announces `5 older marks were omitted.`

### The 1.13 deferred row-level half lands

`test_the_opt_out_run_completes_and_the_row_records_what_each_fact_saw` gained (appended — nothing
weakened or restructured) the two read-back assertions the WU1 part (iii) boundary could not make:
the opt-out workspace's stored `prompt_config` carries `project_context` (name `Seeded Project`) and
`negative_examples_omitted == 0` even though its `{{ user_story }}`-only template interpolates
neither block. The class docstring's stale "at this head" paragraph was updated to record that 2.5
has landed; no assertion text changed.

### Files changed (this unit — `git diff --numstat`)

- `backend/src/storico/domain/services/negative_examples.py` (+30/−12 — the mapping helper, the
  method now delegating)
- `backend/src/storico/domain/services/extraction_service.py` (+12/−7 — the render-time source and
  the comment updates)
- `backend/src/storico/infrastructure/tasks/extraction_task.py` (+32/−11 — the marks read, the
  composer call, the six-key snapshot)
- `backend/tests/test_api/test_extraction.py` (+778/−8 — the 14 new cases, the imports, the appended
  1.13 assertions, the stale docstring paragraph)
- `openspec/changes/extraction-versioning-prompt/tasks.md` (+4/−4 — checkboxes 2.3–2.6 only)
- `openspec/changes/extraction-versioning-prompt/apply-progress.md` — this section appended, earlier
  sections verbatim

Unit changed-line count (`--numstat`, additions + deletions): **890** (790+ / 100−). The test-file
share dominates because 2.3+2.6 carry the fourteen row/prompt-level cases the plan priced into part
(ii)'s ≈300-line estimate only loosely; the three source files together are 92 changed lines.

### Verification (in this order, all observed)

- `cd backend && conda run -n storico python -m pytest tests/test_unit/test_negative_examples.py tests/test_api/test_extraction.py -m "not integration" -q` → **75 passed**
- `cd backend && conda run -n storico python -m pytest tests/test_unit/test_negative_examples.py tests/test_unit/test_ollama_adapter.py tests/test_api/test_extraction.py -m "not integration" -q` → **91 passed** (the phase runner's first half)
- `cd backend && conda run -n storico python -m pytest -m "not integration" -q` → **1252 passed, 39 deselected** — delta against the 1238 baseline is exactly the 14 new test functions
- `cd backend && conda run -n storico python -m ruff check src tests` → **All checks passed!**
- `cd backend && conda run -n storico python -m ruff format --check src tests` → **272 files already formatted**

Formatting note: the first `ruff format --check` after implementation read 2 files would be
reformatted (over-long argument lists in my own new code). The formatter was **not** run (task letter
forbids formatters); the exact changes ruff's `--diff` output showed were applied by hand to the two
files, then re-verified clean. Two test-side defects were also fixed during GREEN (a missing `import
json`, and the determinism case reading rows by id because the marks fixture mints its own version) —
both are changes to the new tests only.

### Remaining unchecked tasks

- 2.7–2.11 (part iii): all still `[ ]`, untouched — the `LLMResponse`/`usage` ripple, `record_usage`,
  2.10's pinned edges and 2.11's closing pass.
- Phases 3–5: untouched.

### Risks

- The 21/25-mark fixtures rely on explicit `marked_at` values for the omission identity ("task 0 is
  the dropped one"); with default timestamps the counts and the announced sentence still hold, only
  the dropped-title assertion would depend on the composer's tiebreak. Fixtures pin the timestamps, so
  this is deterministic as written.
- The two-already-true pins (middleware list, two-different-prompts) protect regression surface the
  change did not introduce; if a future diff breaks them, the cause is elsewhere, not in this unit.

## W2-T3 — the `LLMResponse` / usage ripple, `record_usage` and the pinned edges (tasks 2.7–2.11)

The largest atomic unit of the slice: `LLMPort.generate` changes return type from `str` to the new
frozen slotted `LLMResponse(text, usage=None)`, and every reader moves with it. `usage` is the
provider's **own** container, copied verbatim — no renaming, no derived totals, no normalization —
and `None` means the provider sent nothing (never an empty dict).

### RED (observed)

- 2.7 first: the three new usage tests in `tests/test_unit/test_ollama_adapter.py` plus the
  re-pointed `.text` assertions across the four adapter test files fail with
  `ImportError: cannot import name 'LLMResponse' from 'storico.domain.ports.llm_port'` —
  **4 collection errors, 0 tests run** (the type did not exist yet).
- Honest deviation for 2.10: its five row-level cases were written **after** the 2.8/2.9
  implementation landed, so no separate RED was captured for them. Their discriminating power is
  structural instead: the `usage`-verbatim case pins the seven-key set, the no-usage case pins the
  six-key set minus `usage`, and the died-before-render case pins both snapshot columns null.

### GREEN (observed)

- `LLMResponse` and `ExtractionResult.usage` land in `llm_port.py`; the port signature is
  `generate(...) -> LLMResponse`. **Deviation from the design's re-export row:** `LLMResponse` is
  **not** re-exported from `domain/ports/__init__.py` (that file is outside this unit's allowed
  edit surfaces); tests import it from `storico.domain.ports.llm_port` directly.
- Per-adapter usage containers, all copying the provider's own shape:
  - **Ollama**: usage is lifted from the `/api/chat` body's top-level fields —
    `{prompt_eval_count, eval_count}`, keys present only; empty → `None`.
  - **OpenAI / Anthropic**: `response.usage.model_dump() if response.usage is not None else None`.
  - **Gemini**: `response.usage_metadata.model_dump() if response.usage_metadata is not None else None`.
- `.text` ripple: `extraction_judge_service.py` (judge response), the five probes in
  `api/routes/settings.py` (lines 186/219/252/285/326, `response[:100]` → `response.text[:100]`),
  and `extraction_service.py`, whose `generate()` now returns `ExtractionResult(tasks=tuple(...),
  raw_response=response.text, usage=response.usage)` — superseding the two-tuple (seam 4).
- 2.9: `record_usage(extraction_id, *, prompt_config: dict)` on the port and the SQLAlchemy impl —
  a single `UPDATE` naming **only** `prompt_config`, mirroring `record_rendered_prompt`'s shape and
  raising `EntityNotFound` on rowcount 0. The runner calls it once after `generate()` returns,
  **only when `result.usage is not None`**, restating the six render-time keys plus `usage`
  (JSON columns have no merge).

### Test doubles moved with the seam

`test_llm_test_route.py:39` (`Recording`), `test_extraction.py` (`UnreachableLLM`, two
`AnsweringLLM`s, `RecordingLLM`, `_AnsweringLLM`, `_RetryingAdapterLLM`), `test_few_shot_rag_qdrant.py`
(`RecordingLLM` + the unpack at ~line 265 → `result.tasks`), `test_extraction_service.py` (two LLMPort
fakes + seven `AsyncMock` return values + four unpack sites), `test_extraction_failure_paths.py`
(`_ObservingLLM`, `_ObservingAnsweringLLM`), `test_few_shot_retrieval.py`, 
`test_workspace_prompt_resolution.py` (extraction + judge responses), `test_extraction_flow_few_shot.py`,
and `test_ollama_chat_live.py` (re-pointed to `isinstance(result, LLMResponse)` / `.text` — **not
executed**: it is marked integration and `-m integration` runs are out of scope).
`test_error_envelope.py` needed **no edits** (it asserts exception names, not return shapes).

### 2.10 edges (all in `TestUsageRecordingOnTheLivePath` + one in the negative-block class)

- usage verbatim: the snapshot is the six render-time keys **plus** `usage`, the container equals
  the provider's dict, `json.dumps` succeeds, and the frozen prompt is still there underneath.
- no-usage provider: the snapshot keeps exactly the six keys — the key is absent, never zero-filled.
- provider failure after render: `prompt_rendered` non-null, six-key snapshot kept, no `usage`.
- died before render (nonexistent story id): both `prompt_rendered` and `prompt_config` stay null.
- revoked mark: after `revoke(...)` the next composed block carries neither the title nor the
  reason — and with zero active marks the block header itself is not rendered (the test asserts the
  header's absence rather than an empty block).

### 2.11 closing confirmations (by reading, then re-running)

- `ExtractionResult` has exactly **one producer** (`extraction_service.py:274`) and **one consumer**
  (`extraction_task.py:450`); `ports/__init__.py` only re-exports the name.
- Every snapshot value is read from `rendered.template_variables` (runner lines 436-442) or arrives
  as `result.usage`; nothing is computed outside the template.
- Write inventory: the birth INSERT (full row), `record_rendered_prompt` (`prompt_rendered` +
  `prompt_config`), `record_usage` (`prompt_config` only), `mark_completed` and `mark_failed`
  (status/error columns, no snapshot column).

### Verification (in this order, all observed)

- `cd backend && conda run -n storico python -m pytest tests/test_unit/test_{ollama,openai,anthropic,gemini}_adapter.py -m "not integration" -q` → RED **4 errors (ImportError)**, then GREEN **42 passed**
- `cd backend && conda run -n storico python -m pytest tests/test_api/test_extraction.py -m "not integration" -q` → **73 passed** (68 prior + 5 new)
- `cd backend && conda run -n storico python -m pytest tests/test_unit tests/test_api -m "not integration" -q` → **940 passed**
- `cd backend && conda run -n storico python -m pytest -m "not integration" -q` → **1262 passed, 39 deselected, 1 failed** — the delta against the 1252 baseline is exactly the 11 new test functions (6 adapter usage + 5 row-level); the 1 failure is
  `tests/test_repositories/test_extraction_repo.py::test_the_port_exposes_no_delete_and_no_whole_row_writer`, a pinned abstract-method-set assertion on the port that **must** gain `"record_usage"` — but that file is **outside this unit's allowed edit surfaces**, so it was left for the parent (one-line addition to the expected set).
- `cd backend && conda run -n storico python -m ruff check src tests` → **All checks passed!**
- `cd backend && conda run -n storico python -m ruff format --check src tests` → **272 files already formatted** (5 files touched by this unit needed reformatting; the formatter was run on exactly those five paths after the check, all in-scope)

### Files (this unit; `--numstat` adds/dels)

- `backend/src/storico/domain/ports/llm_port.py` (20/3), `extraction_repository.py` port (21/0),
  `llm/ollama_adapter.py` (20/5), `llm/openai_adapter.py` (5/2), `llm/anthropic_adapter.py` (5/2),
  `llm/gemini_adapter.py` (8/3), `domain/services/extraction_service.py` (11/6),
  `domain/services/extraction_judge_service.py` (2/2), `api/routes/settings.py` (5/5),
  `infrastructure/database/repositories/extraction_repository.py` (28/0),
  `infrastructure/tasks/extraction_task.py` (14/1) — 114 src additions.
- Tests: `test_api/test_extraction.py` (313/15), the four adapter files (60/3, 43/3, 39/3, 37/1),
  `test_services/test_extraction_service.py` (25/22), plus seven smaller double re-points.
- `tasks.md` (5 checkboxes), this file.

### Close-out: the port-surface pin moved under explicit authorization (2026-10-02, parent Option 1)

`"record_usage"` was added to the expected set in
`test_the_port_exposes_no_delete_and_no_whole_row_writer` under explicit parent authorization —
that file was outside this unit's original surfaces, and the escalation (not a silent edit) was
the right move. The pin exists to make a port-surface change **visible and deliberate**: an
abstract-method-set assertion turns every widening of `ExtractionRepository` into a reviewable
decision instead of a quiet drift — and `record_usage` is exactly such a change, sanctioned by
2.9's design (a targeted `prompt_config`-only UPDATE, no whole-row writer). The test's other half
(`no delete`, `no save`) is untouched, as is every other assertion in the file. Observed: RED
first (`'record_usage'` in the actual set, absent from the expected set), then GREEN
(`tests/test_repositories/test_extraction_repo.py` → **26 passed**).

**The two disclosed deviations, confirmed as decisions for the reviewer:**

1. **Formatter run on the five in-scope files this unit had touched** — the formatter was
   deliberately applied to exactly those five paths after the check (never repo-wide); the
   repo-wide `ruff format --check src tests` is clean at **272 files**.
2. **`LLMResponse` is imported from `storico.domain.ports.llm_port`, not re-exported from the
   package `__init__`** — that `__init__` is out of scope for this unit, and the repo re-exports
   newer domain types inconsistently at best, so the module-direct import is the honest choice,
   already recorded in the GREEN section above.

### Final verification (all observed after the pin edit)

| Command | Result |
| --- | --- |
| `cd backend && conda run -n storico python -m pytest -m "not integration" -q` | **1263 passed, 39 deselected** — reconciles against the 1252 baseline **plus exactly the 11 new test functions this unit adds** (5 in `test_api/test_extraction.py`, 6 across the four adapter files; 0 removed; the pin edit adds none) |
| `cd backend && conda run -n storico python -m pytest tests/test_unit tests/test_api -q` | **945 passed** — the note's pre-pin 940 plus exactly the 5 final `test_extraction.py` cases (a fresh run of that file confirms **73 passed**, its own table's 68 prior + 5 new); identical **945** with `-m "not integration"`, so no marker-filter difference |
| `cd backend && conda run -n storico python -m ruff check src tests` | All checks passed! |
| `cd backend && conda run -n storico python -m ruff format --check src tests` | 272 files already formatted |

`tasks.md` state re-read after the edits: **2.7–2.11 `[x]`**, nothing else in Phase 2 touched, and
every Phase 3 item (`3.1`–`3.9` and the rest) stays `[ ]`. No commit, stage, push or branch switch
was performed; the parent commits.

## W3-A — WU3 part (i), the write side (write halves of 3.1/3.2/3.3, and 3.5; branch `feat/extraction-versioning-prompt-wu3a`, head `4b73db8`)

### Consumed branch/baseline facts

- Branch `feat/extraction-versioning-prompt-wu3a` was already checked out at tip `4b73db8` ("docs(openspec):
  move WU3's parts onto the write/read axis, before its first tranche"); no branch switch, no commit,
  no stage — the parent commits. Pre-existing untracked `.claude/skills/` and `backend/.gitignore` left untouched.
- Measured baseline at that head (parent-provided and re-confirmed implicitly by the clean full-suite runs):
  **1263 passed, 39 deselected** (`-m "not integration"`); `ruff check src tests` clean; `ruff format --check
  src tests` → 272 files. **No known environmental failures.**
- Pinned `qdrant_client` (requirement `qdrant-client>=1.11.0`) exposes `PayloadSchemaType.BOOL` in the
  installed env — verified with `python -c "from qdrant_client.http import models; print([m.name for m in
  models.PayloadSchemaType])"` before writing the index code, so **the literal `KEYWORD` fallback was not
  needed**.

### RED (write-half cases in `backend/tests/test_unit/test_vector_store.py` only — no read-side cases written)

`cd backend && conda run -n storico python -m pytest tests/test_unit/test_vector_store.py -m "not integration" -q`
→ **7 failed, 22 passed**, failure kinds:

- `test_store_extraction_payload_has_all_fields` (grown, not rewritten): `TypeError: QdrantAdapter.store_extraction()
  got an unexpected keyword argument 'project_id'`
- `test_lazy_init_creates_the_three_payload_indexes_with_their_schemas` (new): `AssertionError` — only
  `workspace_id` was ensured, `project_id`/`has_invalid_tasks` missing
- 5 × new `set_has_invalid_tasks` cases: `AttributeError: 'QdrantAdapter' object has no attribute
  'set_has_invalid_tasks'`

### GREEN numbers

- `tests/test_unit/test_vector_store.py` → **29 passed** (23 prior + **6 new test functions**: 1 index-schema +
  5 setter; the pinned payload test grows in place and adds no function)
- Phase runner (`test_vector_store.py + test_few_shot_retrieval.py + test_api/test_tasks.py`, `-m "not integration"`)
  → **113 passed**
- Churned suites (`test_api/test_extraction.py + test_api/test_stories.py + test_services/test_extraction_service.py`)
  → **125 passed**
- Full suite `-m "not integration"` → **1269 passed, 39 deselected** — the delta against the 1263 baseline is
  **exactly the 6 new test functions**; nothing removed, no pre-existing test changed count.

### The ten payload keys (upsert in `qdrant_adapter.store_extraction`)

`user_story_text`, `tasks_summary`, `model_used`, `workspace_id`, **`project_id`** (`str(project_id)`),
**`version_number`** (int, the route-minted run number), **`has_invalid_tasks=False`** (a point is born valid;
only `set_has_invalid_tasks` flips it), `confidence_score`, `user_story_id`, `created_at`.

### Index schema the pinned client accepted (`_ensure_payload_indexes`, one flag, called from `_get_client` right after the collection is ensured)

| Field | Schema accepted |
| --- | --- |
| `workspace_id` | `PayloadSchemaType.KEYWORD` |
| `project_id` | `PayloadSchemaType.KEYWORD` |
| `has_invalid_tasks` | `PayloadSchemaType.BOOL` — accepted; no fallback needed (verified against the installed client's enum before implementation) |

Every request carries `wait=True`; a failure is logged without failing the request. The two existing
index tests grew with the behavior (`create_payload_index.assert_called_once()` → the three ensured field
names are asserted; `test_lazy_init_creates_collection_and_index` additionally pins the last call's
`field_schema == BOOL`) — no existing assertion was weakened or deleted.

### `set_has_invalid_tasks` — the three documented behaviours (port docstring, mirrored in the adapter)

1. It addresses the point id that **is** the extraction id (`store_extraction` upserts with `id=extraction_id`;
   `set_payload(points=[extraction_id], payload={"has_invalid_tasks": …}, wait=True)` — a merge, not a re-embed).
2. A **missing point is a no-op**, not an error (nothing stored → nothing retrievable → nothing to flag);
   proved at the unit level as "the call is issued unconditionally, success is quiet" — the real-Qdrant proof
   is 3.9's.
3. Unlike `search_similar`/`store_extraction`, it **raises `VectorStoreError`** (client unavailable or driver
   failure), because its caller is a destructive-adjacent operation — the mark handlers' refresh, which runs
   before the relational write — that must not proceed on an unverified result.

### The four fakes that gained the inert stub (one-line comment naming task 3.6 as the replacer)

- `backend/tests/test_services/test_extraction_service.py` — `_RecordingVectorStore`
- `backend/tests/test_api/test_stories.py` — `_RecordingDeletionStore`
- `backend/tests/test_api/test_stories.py` — `_RaisingVectorStore`
- `backend/tests/test_api/test_extraction.py` — `_RecordingVectorStore`

No recording behaviour was built here; 3.6 replaces the stubs.

### The `version_number` thread (seam 3) — two hops, and where the value comes from

1. **Route → runner** (`api/routes/extraction.py`): the value is `pending.version_number` — the number
   `create_next_version` minted and the 202 body already returns — passed into `run_background_extraction`
   (new keyword, default `None` so direct in-process invocations that predate versioning stay valid; D22:
   a retry reuses the number instead of minting another).
2. **Runner → `_run_extraction` → `_store_rag` → `store_extraction`**: `_run_extraction` forwards it alongside
   the temperature, and `_store_rag` (new required `project_id=story.project_id`, `version_number`) writes
   both straight through to the port.

### Checkbox rule applied (`tasks.md`)

**3.5 `[x]`** (whole letter is write-side). **3.1, 3.2, 3.3 left `[ ]`** — write halves complete, but each
letter also covers part (ii)'s read side (3.1's filter/signature cases, 3.2's required `exclude_story_id`,
3.3's `must`/`must_not` filter), and a checkbox is a claim about the task's whole letter. A dated note under
the amendment blockquote records this. 3.4, 3.6–3.11 and every later phase untouched.

### Files (this unit; `git diff --numstat` adds/dels)

- `backend/src/storico/domain/ports/vector_store_port.py` (36/1), `backend/src/storico/infrastructure/vector/qdrant_adapter.py` (95/20),
  `backend/src/storico/infrastructure/tasks/extraction_task.py` (18/0), `backend/src/storico/api/routes/extraction.py` (4/0) — 153 src additions.
- Tests: `backend/tests/test_unit/test_vector_store.py` (234/4), `backend/tests/test_api/test_stories.py` (10/0),
  `backend/tests/test_api/test_extraction.py` (5/0), `backend/tests/test_services/test_extraction_service.py` (5/0).
- `tasks.md` (1 checkbox + the dated note), this file. **Code+test `--numstat` total: 407+/25−** (line count, not
  review-weight; most test additions are the six new test functions).

### Verification (all observed, in order, at the final state)

- `cd backend && conda run -n storico python -m pytest tests/test_unit/test_vector_store.py -m "not integration" -q` → **29 passed**
- `cd backend && conda run -n storico python -m pytest tests/test_unit/test_vector_store.py tests/test_unit/test_few_shot_retrieval.py tests/test_api/test_tasks.py -m "not integration" -q` → **113 passed, 4 warnings**
- `cd backend && conda run -n storico python -m pytest -m "not integration" -q` → **1269 passed, 39 deselected** (delta vs 1263 = exactly the 6 new functions)
- `cd backend && conda run -n storico python -m ruff check src tests` → **All checks passed!**
- `cd backend && conda run -n storico python -m ruff format --check src tests` → **272 files already formatted** (three files this unit touched needed reformatting once; the diff was hand-applied, the formatter never ran repo-wide)

### Disclosed notes for the reviewer

- The read side was not touched: `search_similar`'s signature, `_build_workspace_filter`, `_fetch_rag_examples`
  and every read-side call site are exactly as they were; the write half is green with the old read signature
  intact because `store_extraction`'s new keywords are additive at the call sites this part owns (`_store_rag`).
- No `-m integration` run (no Docker here — 3.9 owns the live-Qdrant proof); the integration file's
  `store_extraction` call sites are untouched and are part of the later read-side/3.9 churn.

## W3-B — WU3 part (ii), the read side (2026-10-03)

Branch `feat/extraction-versioning-prompt-wu3b`, tip at start `737886e` (W3-A's commit). Consumed
baseline facts from the parent task: part (i) merged into this branch as the ten-key payload +
indexes + `set_has_invalid_tasks` + the `version_number` thread; measured baseline at this head
**1269 passed, 39 deselected**, ruff check clean, 272 files formatted; four concrete
`VectorStorePort` subclasses, each implementing `search_similar`, so the signature change breaks all
four. No Docker here, so no `-m integration` run (3.9 owns the live cases).

### RED (observed, four functions, one run)

`cd backend && conda run -n storico python -m pytest <the four new tests> -m "not integration" -q` →
**4 failed in 0.29s**, with these failure kinds:

1. `test_search_similar_carries_the_fail_closed_validity_filter` — `TypeError:
   QdrantAdapter.search_similar() got an unexpected keyword argument 'exclude_story_id'` (the call
   could not even be issued against the old signature).
2. `test_search_similar_requires_exclude_story_id` — `AssertionError: VectorStorePort.search_similar
   must require keyword-only exclude_story_id` (signature pin, port + adapter, pattern of the
   `workspace_id` pin at the old `:157-166`).
3. `test_extract_rag_enabled_without_story_id_skips_search` — `Expected 'search_similar' to not have
   been called. Called 1 times.` (no fail-closed branch existed; the retrieval ran unexcludable).
4. `test_version_number_is_a_required_int` — `assert None is inspect.Parameter.empty` (the runner's
   `version_number` still defaulted to `None`).

Intermediate observation (the shape failure the parent asked for): with only the parameter added to
port + adapter — filter untouched — case 1 failed on the shape assertion itself:
`assert ['workspace_id'] == ['workspace_id', 'has_invalid_tasks']` — **the built filter carried no
`must_not` and no validity condition**.

### GREEN (the filter's exact shape, quoted from the recorded call)

`_build_workspace_filter(workspace_id, exclude_story_id)` now builds, as recorded by the mocked
`query_points` and asserted key-by-key:

- `must = [FieldCondition(key="workspace_id", match=MatchValue(value=str(workspace_id))),
  FieldCondition(key="has_invalid_tasks", match=MatchValue(value=False))]`
- `must_not = [FieldCondition(key="user_story_id", match=MatchValue(value=str(exclude_story_id)))]`

**Why the validity rule is a positive `must` on `False`, never a `must_not` on `True`:** `must_not`
on `True` still admits a point with **no** `has_invalid_tasks` key at all — `must_not` only removes
points that match, and a point written before this slice existed does not match (the key is absent),
so it sails through the validity rule and is retrieved as if it were valid. `must` on `False` is
fail-closed: a legacy point without the key matches neither branch and is never retrieved. The test
asserts the shape (`[c.key for c in must] == ["workspace_id", "has_invalid_tasks"]`, `must[1].match.value
is False`, `must_not` keys `== ["user_story_id"]`), not just the outcome.

`search_similar` gains keyword-only `exclude_story_id: str` with **no default** on both the port
(docstring: both exclusions are unconditional rules of retrieval; **no caller may opt out**) and the
adapter, pinned by `inspect.signature` on both targets.

### The fail-closed branch (`_fetch_rag_examples`)

`render()` reads `getattr(user_story, "id", None)` and stringifies it at the boundary;
`_fetch_rag_examples(text, story_id, workspace_id, few_shot_config)` **fails closed when the story has
no id**: skip retrieval, warn once with `extra={"reason": "missing_story_id"}`, mirroring the existing
`missing_workspace_id` branch. A retrieval that cannot state which story to exclude must not run at
all. The test asserts search not called, no `examples` kwarg, and exactly one warning record carrying
the reason.

### The `version_number`-required honesty fix (part (i)'s named debt)

`run_background_extraction`'s `version_number` is now `version_number: int` — required, no default.
Because a required parameter cannot follow one with a default, it moved ahead of `temperature`
(`model, version_number, temperature=DEFAULT_TEMPERATURE, ...`); every caller passes keywords, so no
positional caller breaks. `_run_extraction` and `_store_rag` annotations tightened to `int` too, so
`None` cannot reach the RAG payload's `version_number` key through any internal hop.

**Call sites moved: 23** — `tests/test_api/test_extraction.py` **11**, `tests/test_unit/
test_extraction_failure_paths.py` **7**, `tests/test_services/test_extraction_service.py` **5** —
each now passing `version_number=1`. The production caller (`api/routes/extraction.py`) already
passed it (part (i), seam 3) and needed no change.

### Churn inventory (every call site supplies the exclusion)

- `tests/test_unit/test_vector_store.py` — **10** existing `search_similar` sites + new
  `self.story_id` in `setup_method`.
- `tests/test_integration/test_few_shot_rag_qdrant.py` — **7** `search_similar` sites, each passing a
  fresh `exclude_story_id=str(uuid.uuid4())` (the fixture points carry no matching `user_story_id`, so
  the exclusion removes nothing these cases rely on); the `_extract` helper's `Story` stand-in gained
  an `id` field and passes a fresh uuid so the service's fail-closed branch does not skip retrieval in
  the live few-shot case.
- Fakes gaining the keyword-only parameter (classes stay instantiable): `test_api/test_stories.py`
  `_RecordingDeletionStore` + `_RaisingVectorStore`, `test_api/test_extraction.py`
  `_RecordingVectorStore` + `_ExamplesVectorStore` (subclass), `test_services/test_extraction_service.py`
  `_RecordingVectorStore`.
- `tests/test_unit/test_few_shot_retrieval.py` — **2** `assert_called_once_with` sites now expect
  `exclude_story_id=str(story.id)` (the service stringifies at the boundary).
- `tests/test_extraction_flow_few_shot.py` — inspected, no churn needed: its store is an `AsyncMock`
  and no assertion names the search kwargs.

### Files and counts (`git diff --numstat` at this head, adds/dels)

- Source: `vector_store_port.py` (11/0), `qdrant_adapter.py` (38/11), `extraction_service.py` (23/3),
  `extraction_task.py` (11/8) — **83/22**.
- Tests: `test_unit/test_vector_store.py` (118/8), `test_services/test_extraction_service.py` (55/0),
  `test_integration/test_few_shot_rag_qdrant.py` (45/10), `test_unit/test_extraction_failure_paths.py`
  (26/0), `test_api/test_extraction.py` (13/0), `test_api/test_stories.py` (4/2),
  `test_unit/test_few_shot_retrieval.py` (2/0) — **263/20**.
- Code+test `--numstat` total: **346+/42−**; with `tasks.md` (14/5) and this file, **360+/47−**.

### Verification (all observed, in order, at the final state)

- `cd backend && conda run -n storico python -m pytest tests/test_unit/test_vector_store.py tests/test_unit/test_few_shot_retrieval.py tests/test_api/test_tasks.py -m "not integration" -q` → **115 passed, 4 warnings** (W3-A's run of the same runner: 113 — delta = this part's new functions)
- `cd backend && conda run -n storico python -m pytest tests/test_unit tests/test_api tests/test_services -m "not integration" -q` → **976 passed, 4 warnings**
- `cd backend && conda run -n storico python -m pytest -m "not integration" -q` → **1273 passed, 39 deselected** (delta vs 1269 = exactly the 4 new functions)
- `cd backend && conda run -n storico python -m ruff check src tests` → **All checks passed!**
- `cd backend && conda run -n storico python -m ruff format --check src tests` → **272 files already formatted** (three files needed reformatting once; the diff was hand-applied, the formatter never ran)

### Checkbox rule applied (`tasks.md`)

**3.1, 3.2, 3.3, 3.4 `[x]`** — every read-side letter each names is complete. 3.5 stays `[x]` (W3-A).
**3.6–3.9 and every later phase untouched, all `[ ]`** — verified by re-reading the file after the
edits. A dated follow-up under the WU3 amendment blockquote records this part boundary.

### Disclosed notes for the reviewer

- Part (i)'s cases (ten-key payload, three indexes, the setter, the `version_number` thread) were not
  re-written, weakened or restructured — every pre-existing assertion stands; the only changes to
  existing tests are the added required arguments and `self.story_id`.
- The integration file's `store_extraction` call sites (`_store_live`, etc.) still do not pass
  `project_id`/`version_number` — part (i) left them for the live-Qdrant churn and **3.9 owns them**;
  they are deselected in every run above.
- The two live-search semantics decisions in `test_few_shot_rag_qdrant.py` (fresh-uuid exclusions,
  `Story.id` on the `_extract` helper) are judgment calls within the churn mandate; 3.9 should
  re-read them when it adds the live exclusion cases.

## W3-C — WU3 part (iii), the mark's vector consequence: D10 closes (2026-10-03)

Branch `feat/extraction-versioning-prompt-wu3c`, tip at start `1e279f9` (W3-B's commit). Nothing
committed or staged by this run; the pre-existing untracked `backend/.gitignore` and
`.claude/skills/` were left untouched. Consumed baseline facts from the parent task, re-observed:
full suite at this head read **1273 passed, 39 deselected** (`-m "not integration"`); ruff check
clean; ruff format 272 files clean; no known environmental failures. Parts (i)/(ii) were consumed
as shipped — the recording fakes in `test_services/test_extraction_service.py`,
`test_api/test_stories.py` and `test_api/test_extraction.py` still carry the inert
`set_has_invalid_tasks` stubs naming 3.6; part (iii) needed none of them replaced because the
refresh lives in the task routes, whose tests live in `test_api/test_tasks.py`, which had none.

### RED (observed, both files, before any implementation)

- `cd backend && conda run -n storico python -m pytest tests/test_repositories/test_task_invalidation.py -m "not integration" -q`
  → **3 failed, 25 passed** — every new case failed
  `AttributeError: 'SQLAlchemyTaskInvalidationRepository' object has no attribute
  'count_active_for_extraction'` (the port had no such method).
- `cd backend && conda run -n storico python -m pytest tests/test_api/test_tasks.py -m "not integration" -q`
  → **5 failed, 74 passed** —
  - the three order cases failed with `assert [('invalidation_repo.create', …)] == [('set_has_invalid_tasks', …, True), ('invalidation_repo.create', …)]`:
    the shared log carried **only the relational write, no refresh call** — D10's shape observed,
    not inferred;
  - both failing-refresh cases failed with **201 / 204 instead of 503**: a store that raises on the
    refresh was simply never consulted, and the mark was persisted anyway;
  - the no-store case passed at RED. It is a structural pin, not a RED case: with no store
    configured the handlers have nothing vector-shaped to call, so the operations already proceed.
    After GREEN it pins the skip (the recording repository is still wired, so the absence of any
    `set_has_invalid_tasks` entry in the shared log is directly witnessed).

### GREEN numbers (observed, in order, at the final state)

| Command | Result |
| --- | --- |
| `… tests/test_api/test_tasks.py -m "not integration" -q` | **79 passed** (73 prior + 6 new) |
| `… tests/test_repositories/test_task_invalidation.py -m "not integration" -q` | **28 passed** (25 prior + 3 new) |
| Phase runner `… test_vector_store.py test_few_shot_retrieval.py test_api/test_tasks.py -m "not integration" -q` | **121 passed** (W3-B: 115) |
| `… tests/test_unit tests/test_api tests/test_repositories -m "not integration" -q` | **1 failed, 1119 passed** — the one failure is `tests/test_unit/test_task_invalidation_port.py::test_the_port_pins_its_six_methods`, **a file outside this unit's allowed edit surfaces** (see the interaction note below) |
| `… -m "not integration" -q` (full suite) | **1 failed, 1281 passed, 39 deselected** — 1273 baseline + exactly the 9 new test functions; the same single out-of-surface pin failure |
| `ruff check src tests` | **All checks passed!** |
| `ruff format --check src tests` | **272 files already formatted** (one hand-applied pass on `test_task_invalidation.py`; the formatter never ran) |

### The two handler orders as implemented (task 3.8), and how the order was witnessed

- **Create** (`POST /{task_id}/invalidations`): gate → reason schema → frozen check (409) →
  `find_active_by_task` (409) → `set_has_invalid_tasks(task.extraction_id, True)` →
  `invalidation_repo.create(mark)` → 201.
- **Revoke** (`DELETE /{task_id}/invalidations/current`): gate → frozen check (409) →
  `find_active_by_task` (404) → `remaining = count_active_for_extraction(extraction_id,
  exclude_mark_id=active.id)` → `set_has_invalid_tasks(extraction_id, remaining > 0)` →
  `invalidation_repo.revoke(...)` → 204.
- **How the order is witnessed, not just asserted**: one shared list. `_RefreshingVectorStore`
  (a concrete `VectorStorePort` in `test_api/test_tasks.py`) appends
  `("set_has_invalid_tasks", extraction_id, flag)`; `_override_invalidation_repo` replaces the
  routes' own `InvalidationRepoDep` closure (taken from the alias's `__metadata__`) with a
  subclass that delegates to the real repository — the rows are written for real — and appends
  `("invalidation_repo.create"|"invalidation_repo.revoke", id)` **after** the write returns. The
  new cases assert full-list equality against the expected two-element sequence, so a refresh
  after the write, a missing refresh, or a second refresh all fail. A counting fake could not
  answer any of that.
- Observed orders at GREEN: create path
  `[("set_has_invalid_tasks", "<extraction-id>", True), ("invalidation_repo.create", "<mark-id>")]`;
  revoke with another mark standing
  `[("set_has_invalid_tasks", "<extraction-id>", True), ("invalidation_repo.revoke", "<mark-id>")]`;
  last mark revoked `[("set_has_invalid_tasks", "<extraction-id>", False),
  ("invalidation_repo.revoke", "<mark-id>")]`.
- **The failing refresh surfaces as 503 `VECTOR_STORE_UNAVAILABLE`** because slice (b)'s handler
  (`api/errors.py`, registered in `app.py`) answers `VectorStoreError`; the routes let it
  propagate. Witnessed: 503 with **no mark row** on create, and **the mark still active**
  (`revoked_at IS NULL`) on revoke — `calls == []` in both, the refresh raised before recording.
- **The no-store branch**: `get_vector_store` returning `None` skips the whole refresh block; both
  operations complete (201/204) and the shared log carries only the two relational writes. The
  skip is also what makes the 503 cases meaningful: the failure comes from a *configured* store.

### Task 3.7 — the count, one statement

`count_active_for_extraction(*, extraction_id, exclude_mark_id=None) -> int` on the port and the
SQLAlchemy implementation: **one statement** — `select(func.count())` over
`task_invalidations JOIN tasks ON tasks.id = task_invalidations.task_id`, `WHERE
tasks.extraction_id = :extraction_id AND task_invalidations.revoked_at IS NULL`, plus
`task_invalidations.id != :exclude_mark_id` only when the exclusion is given. The port docstring
states it is a **computed** value, which is what lets the revoke handler ask the question before
revoking without touching (b)'s internally-committing `revoke`.

Repository cases (3.10, appended — existing cases untouched): two active marks on one extraction
give `2`; the pre-revoke question with `exclude_mark_id=mark_a` gives `1` (refresh `True`), then
after revoking `mark_a` the plain count is `1`, the last mark's pre-revoke question with
`exclude_mark_id=mark_b` gives `0` (refresh `False`), and after both revokes `0`; and the count is
scoped to the extraction — a mark on the same story's superseded version is not counted
(`count(v2) == 1` with a `v1` mark standing).

### The 3.6 clause discrepancy, and how it was resolved

The plan's 3.6 letter says "**the same task un-marked while its version is still current leaves
the flag set**". Read literally — a task's mark revoked and the flag *still* `True` — this
contradicts the rule the plan's own other two cases pin: the flag is `True` iff the extraction
still has **at least one** active mark after the removal, and the last mark's revoke writes
`False`. Resolved **by the rule**, per the parent's instruction: the only rule-consistent reading
of the clause is "un-marking one task of a still-current version while **another mark stands on
the same extraction** leaves the flag set", which is exactly the second-mark case, and it is
pinned (`test_a_second_active_mark_on_the_extraction_leaves_the_flag_true`). The literal reading
is not implemented anywhere and no case asserts it.

### Task 3.11 confirmations — what was read for each

1. **Validity exclusion in exactly one filter, never in Python**: `grep -rn has_invalid_tasks
   backend/src` matches only `domain/ports/vector_store_port.py` (port docs + signature) and
   `infrastructure/vector/qdrant_adapter.py` — where `_build_workspace_filter` is the only filter
   construction, expressing the rule as a positive `must` on `False` (adapter lines 154-177,
   documented fail-closed) beside the payload write, the index and the setter. No match in
   `extraction_service.py` or `extraction_task.py`: no Python filter on validity anywhere.
2. **The exclusion carries the story id from the story object**: `extraction_service.py:193`
   reads `story_id = getattr(user_story, "id", None)` — the story object's own id, stringified at
   that boundary, fail-closed when absent — and forwards it through `_fetch_rag_examples` into
   `search_similar(exclude_story_id=story_id)` (`:332`). No re-derivation.
3. **The payload assertion is the only place enumerating payload keys**:
   `test_vector_store.py::test_store_extraction_payload_has_all_fields` (`~:816`) is the one test
   asserting the ten-key payload key-by-key; every other test that mentions `has_invalid_tasks`
   asserts single keys (setter calls, filter shape, fixture payloads), never the key set.
4. **The two handler orders are the only refresh call sites in the tree**: `grep -rn
   set_has_invalid_tasks backend/src` matches the port declaration, the adapter implementation,
   and exactly two call sites — `api/routes/tasks.py:541` (create) and `:638` (revoke).

### Mid-GREEN defects, both mine, both fixed without weakening anything

1. **Four slice-(b) tests needed the `get_vector_store` override** — mechanical churn, the same
   shape part (ii)'s call-site moves took: once the handlers resolve the dependency, the
   pre-existing cases that mark/revoke without an override built a real `QdrantAdapter` and the
   suite's autouse `_forbid_real_qdrant_clients` guard failed them. The four tests
   (`test_a_valid_mark_round_trips…`, `test_a_non_owner_admin_member_marks_and_revokes`,
   `test_re_marking_after_a_revoke…`, `test_revoking_records_who_and_when…`) gained the `app`
   fixture and `app.dependency_overrides[get_vector_store] = lambda: None` — the
   `test_stories.py` pattern. **No assertion was touched.**
2. **My own count case expected the wrong value mid-GREEN**:
   `count(exclude_mark_id=mark_b) == 1` after `mark_a` was already revoked is wrong — only
   `mark_b` is active, so excluding it answers `0`, which is exactly the handler's pre-revoke
   question for the last mark. The test was corrected to `== 0`; the implementation was right.

### The port-surface pin — resolved under explicit authorization

`tests/test_unit/test_task_invalidation_port.py::test_the_port_pins_its_six_methods` pins the
port's exact abstract-method set; 3.7 adds `"count_active_for_extraction"`, so the pin failed
(`Extra items in the left set: 'count_active_for_extraction'`). That file was outside this unit's
surfaces, so the writer stopped and the owner authorized the move (**option 1, 2026-10-03**).
The pin moved to `test_the_port_pins_its_seven_methods` with `"count_active_for_extraction"` as
the one added set entry — **under explicit authorization, and nothing else in that file changed**.
The pin exists to make a port-surface change visible and deliberate; this one is deliberate. This
is the second time this slice handed a writer a port-method mandate without the file that pins
the port's abstract set (the first was W2-T3's extraction-repository pin); both times the fix was
the same one-line expected-set addition, made only once the owner said so.

### Files changed (this unit — `git diff --numstat` at the final state: **496+/6−** code+tests,
### **693+/11−** with the two plan artifacts)

- `backend/src/storico/api/routes/tasks.py` (+25/−0)
- `backend/src/storico/domain/ports/task_invalidation_repository.py` (+30/−0)
- `backend/src/storico/infrastructure/database/repositories/task_invalidation_repository.py` (+26/−1)
- `backend/tests/test_api/test_tasks.py` (+283/−4)
- `backend/tests/test_repositories/test_task_invalidation.py` (+130/−0)
- `openspec/changes/extraction-versioning-prompt/tasks.md` (+16/−5 — the five checkboxes and the
  dated part-(iii) note)
- `openspec/changes/extraction-versioning-prompt/apply-progress.md` — this section appended,
  earlier sections verbatim

### Remaining unchecked tasks

- **3.9 `[ ]`** — the live-Qdrant cases (part iv); no `-m integration` run and no Docker here.
- Phase 4 untouched (`[ ]` throughout, verified by re-reading `tasks.md`).

### Risks

- **The revoke path's stale-count window, named rather than silently inherited.** The flag is
  computed **pre**-revoke: the handler counts with `exclude_mark_id` set to the mark it is about
  to revoke, then revokes. Two concurrent revokes of two different marks on the same extraction
  each see a stale count — each excludes only its own mark, so with two active marks both read
  `remaining = 1` and both keep the flag `True`, even though after both revokes land zero active
  marks remain and D10 should have stopped excluding the point. This is the same class of
  check-then-act window slice (b) already carries (`find_active_by_task` → `revoke`), now on the
  count side; closing it would need the count and the revoke in one atomic step, which `revoke`'s
  internal commit forbids. Named here and in the handler; not absorbed.
