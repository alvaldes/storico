# Verify report — extraction-versioning-prompt (slice (c))

**Head verified:** `55e9949` + the report commit (`feat/extraction-versioning-prompt-wu3d`, PR #50).
**Status: COMPLETE**, with one qualification stated in §1: the benches ran against **production's database**
(the owner's instruction) and their vector points went to the **dev** collection, so production's vector
store is untouched. Two provider rows remain *not confirmed* and say so.

## 1. What ran where (the honest split)

| Layer | Command | Where | Observed |
| --- | --- | --- | --- |
| Backend suite, no marker filter | `python -m pytest -q` | this machine | **1282 passed, 45 skipped** |
| Backend suite, no marker filter | same | CI (Docker runner) | **1303 passed, 24 skipped** |
| Integration layer (Postgres via testcontainers) | `-m integration` | CI | **21** Docker-gated cases ran and passed |
| Live Qdrant layer | `STORICO_TEST_LIVE_QDRANT=1 … -m integration` | this machine, **Qdrant Cloud** | **22 passed** |
| The same file **without** the flag | `-m integration` | this machine | **22 skipped** |
| Live Ollama layer | `-m integration` | — | 2 skipped (the two live cases are opt-in) |
| Lint / format | `ruff check` · `ruff format --check` | both | clean · **272 files** |

**1327 collected = 1282 + 45 = 1303 + 24**: 21 Docker-gated cases ran in CI, and 24 (22 Qdrant + 2 Ollama
live) skip in both places. The live-Qdrant layer ran only because this machine reaches Qdrant Cloud — **CI
cannot run it**, so its evidence is this run's.

## 2. The no-shortcut sweep (task 4.5)

Confirmed **by reading the extraction path**: the story text reaches the prompt **whole** (`raw_text` is
read once and used for retrieval and for `prompt_kwargs`, with no `len(`, `min(`, slice, cap or token
budget — the only `len(...)` in that module is a log field); `max_tokens=2048` is an **output** budget in
every adapter (Ollama `num_predict`, OpenAI `max_tokens`, Anthropic `max_tokens`, Gemini
`max_output_tokens`); and **neither context read is paginated** (`list_for_context` takes no
`limit`/`offset` and `list_page`'s 20/100 window has no caller on this path).

**And the 1000-story run below is the empirical half of the same claim.**

## 3. Two production defects the live layer found (and the fix)

Both were green across the entire unit layer:

1. **The filter excluded on a field with no payload index.** Qdrant answered `400 Index required but not
   found` for every filtered search, because `must_not` names `user_story_id` and only `workspace_id`,
   `project_id` and `has_invalid_tasks` were indexed. Graceful degradation turned that hard refusal into
   an **empty list**, so few-shot retrieval would have been **silently disabled in production with every
   unit test green**. Fixed by indexing `user_story_id` as `KEYWORD`. The design's index list was
   **incomplete**: three fields named, four filtered on.
2. **An absent point is not a quiet success.** The setter's contract says no-op; the unit case assumed a
   quiet return and the live server answers `404 No point with id …`. The setter now honours the no-op by
   shape; the residual re-wording risk is named.

## 4. The usage confirmation (task 4.1) — real responses

| Provider | Real call | Container the provider returned | Verdict |
| --- | --- | --- | --- |
| **Gemini** | `gemini-3.5-flash` through `GeminiAdapter` | `usage_metadata` → `prompt_token_count`, `candidates_token_count`, `prompt_tokens_details`, `thoughts_token_count`, `total_token_count` (and the None-valued detail keys `model_dump()` carries) | **confirmed**, copied verbatim |
| **Ollama** | `llama3.1:8b` through `OllamaAdapter` | `{"prompt_eval_count": 17, "eval_count": 3}` | **confirmed**, copied verbatim |
| OpenAI | — | — | **not confirmed** (no credential in this environment) — *not* "absent from the provider" |
| Anthropic | — | — | **not confirmed** (same reason) |

**Surviving rule, measured: no field, no key.** When a provider returns no usage container the `usage`
key is **omitted** and the omission is annotated — never zero-filled, never estimated. The runners
thousands of token counts above show the opposite case: when the container is there, it is stored whole.

**Two findings the real calls produced** (they are product-relevant, not test noise):

- **The repo's pinned Gemini model names are retired for new users.** With a valid key,
  `gemini-2.0-flash` and `gemini-2.5-flash` answer **`404 NOT_FOUND`: "no longer available to new users.
  Please update your code to use models/gemini-3.8-flash"**. Worse for a picker: `client.models.list()`
  **lists `gemini-2.5-flash`** while `generate_content` on it 404s — a model list built from `list()`
  would offer dead models. The bench therefore ran on **`gemini-3.5-flash`**, chosen by measurement.
  **This matters for production right now:** when the LLM configuration is recreated (D-a-6), a 2.x model
  name will fail on the first extraction.
- **A thinking model can consume the whole output budget.** With `max_output_tokens=64`,
  `gemini-flash-latest` returned `finish_reason=MAX_TOKENS`, **zero parts** and `thoughts_token_count=61`
  — the adapter correctly reports that as an empty response, and the run lands in `failed` with the
  reason. Production's budget is 2048; on a long prompt a thinking model can exhaust it.

## 5. D20's ladder (task 4.2) and D23's 1000-story project (task 4.3)

**Environment:** production's database (the owner's instruction), reached through a **direct** connection
(no pooler), with `STORICO_QDRANT_COLLECTION` pinned to **`storico_extractions_dev`** so production's
vector collection is untouched. Each rung: one fresh workspace, one project, the stories created through
the **import's own write path** (`parse_story_csv` → `validate_import` → `save_many`, the exact sequence
the import endpoint runs — driven in-process because no container harness wires the app's bearer
dependency against a live server), then one extraction through the **background runner** with Gemini.

| Stories | prompt chars | prompt tokens | total tokens | runner (wall) | row `completed_at − created_at` | context check |
| --- | --- | --- | --- | --- | --- | --- |
| **1** | 1,750 | 354 | 1,445 | 36.0 s | 25.6 s | `other_stories` 0 = `count(*)−1` 0 |
| **50** | 8,998 | 2,006 | 3,087 | 29.2 s | 18.8 s | **49 = 49** |
| **200** | 31,204 | 6,960 | 8,328 | 32.3 s | 21.9 s | **199 = 199** |
| **1000** | **147,852** | **33,314** | **34,505** | 33.3 s | 22.1 s | **999 = 999** |

Every rung landed in the **first of the two legitimate outcomes**: `status = completed`, a stored version
with its measured size, duration and usage, and the context count matching the database exactly. **No rung
was rejected** — the 1000-story prompt went through in ~33 s of wall clock, and the run's own row delta is
tighter (~22 s) because `created_at` comes from the database and `completed_at` from the application: the
two are measured by different clocks and both are reported rather than averaged.

**The 1000-story run's story source, disclosed:** the Salony dataset yields **917 distinct valid
stories**, so the rung was topped up with **83 synthetic stories** in the required INVEST shape (`As a
<role>, I want to review bench report number N so that I can act on its findings`). The measurement is of
**1000 rows through the import and one prompt**, which is what the task requires; the composition of those
1000 rows is stated because hiding it would make the number mean something else. **1000 is a floor**:
`MAX_ROWS = 1000` caps one uploaded file, not a project, so a second import crosses it.

**The statement-count baseline**, as this change writes it down: **≈16 fixed + ≈2 per task**, plus the
call-site delta of the three context reads. The earlier "~8 + 1" figure is not repeated as measured.

## 6. What the version records (verified in the unit layer, and observed above)

`prompt_config` carries exactly six keys — `validate`, `system_prompt`, `few_shots`, `project_context`,
`story_text`, `negative_examples_omitted` — read from `RenderedPrompt.template_variables` and never
re-derived; `negative_examples` travels in `prompt_rendered` instead; and `usage` is added by
`record_usage` **only when the provider returned one**. The live rows above show all seven keys on a
successful run and the runner's failure paths show a run whose provider failed keeping every key but
`usage` with a non-null `prompt_rendered`, and a run that died before render keeping `prompt_rendered IS
NULL`.

## 7. Data written to production by this report's benches (disclosed)

The benches created real rows in production's database: the bench owner user, and one workspace + project
per rung (`Bench 1`, `Bench 50`, `Bench 200`, `Bench 1000`) plus one additional workspace from a failed
first attempt at the 1000 rung (**904 stories imported, no extraction** — the harness refused to continue
when the import accepted fewer rows than the rung, which is the behaviour it should have). Their
extractions, tasks and snapshots are the evidence in §5. **Nothing was written to production's Qdrant
collection** (the bench pinned the dev one). The database's pre-bench state was measured first: revision
`0029` and **every business table at zero**, so nothing pre-existing was touched. If the owner wants these
rows gone, they are deletable per workspace; they are named here so nobody has to guess where they came
from.

## 8. Bottom line

Slice (c)'s code is complete and green where it can be checked here; the live vector layer is verified
against the real service and found two production defects that no unit test could; the prompt path is
unclipped by construction **and** by measurement at 1000 stories; and the usage rule holds against two
real providers — while the two providers this environment cannot reach are recorded as **not confirmed**,
not as absent.
