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
