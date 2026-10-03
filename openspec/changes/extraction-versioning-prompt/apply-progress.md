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
