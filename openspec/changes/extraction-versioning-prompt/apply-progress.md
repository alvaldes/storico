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
