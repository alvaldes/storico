# Verify report — extraction-versioning-prompt (slice (c))

**Head verified:** `55e9949` (`feat/extraction-versioning-prompt-wu3d`, open as PR #50).
**Status: PARTIAL.** Phases 1–3 are code-complete and verified as far as this machine allows. **Phase 4's
measurements (4.1–4.3) have not run**: they are operator-run data operations and they need two things
this machine does not have — a reachable generation provider with a credential (the owner is providing a
Gemini key) and a Neon-like database (the owner is providing one). Nothing below is reported as green
because it was not run; the pending rows say so.

## 1. What ran where (the honest split)

| Layer | Command | Where | Observed |
| --- | --- | --- | --- |
| Backend suite, no marker filter | `python -m pytest -q` | this machine | **1282 passed, 45 skipped** |
| Backend suite, no marker filter | same | CI (Docker runner) | **1303 passed, 24 skipped** |
| Integration layer (Postgres via testcontainers) | `-m integration` | CI | the **21** Docker-gated cases ran and passed |
| Live Qdrant layer | `STORICO_TEST_LIVE_QDRANT=1 … -m integration` | this machine, against **Qdrant Cloud** | **22 passed** |
| The same file **without** the flag | `-m integration` | this machine | **22 skipped** (the honest count) |
| Live Ollama layer | `-m integration` | — | **2 skipped**: no Ollama on this host |
| Lint / format | `ruff check src tests` · `ruff format --check src tests` | both | clean · **272 files** |

The numbers reconcile exactly: **1327 collected = 1282 + 45 = 1303 + 24**, so 21 Docker-gated cases ran
in CI and 24 cases (22 Qdrant + 2 Ollama live) **skip in both places**. The live-Qdrant layer ran only
because this machine reaches Qdrant Cloud; **CI cannot run it**, so its evidence is this run's — not a
green badge.

## 2. The no-shortcut sweep (task 4.5)

Confirmed **by reading the extraction path**, not by trusting the benches:

- **The story text reaches the prompt whole.** `extraction_service.py` reads
  `raw_text = getattr(user_story, "raw_text", str(user_story))` and uses that value for retrieval and for
  `prompt_kwargs["user_story"]`. There is **no** `len(`, `min(`, slice, cap or token budget on it — the
  only `len(...)` in the module is a log field for the example count.
- **`max_tokens` is an output cap everywhere.** It is `num_predict` for Ollama, `max_tokens` for OpenAI
  and Anthropic, and `max_output_tokens` for Gemini — the model's answer budget, never the prompt's.
- **Neither context read is paginated.** `list_for_context` on both repositories takes no `limit` and no
  `offset` (pinned by `inspect.signature` in the unit layer), and `list_page`'s 20/100 window has no
  caller on this path: both methods are called only from the runner.

**Conclusion: no input token cap, no truncation and no input-side pagination were introduced anywhere
between the story text and the provider call.** That is what a bench failure would have put in doubt —
and since the benches have not run yet, the sweep stands as the statement that the path is unclipped
*by construction*, not as a claim that it survives 1000 stories.

## 3. Two production defects the live layer found (and the fix)

This is the strongest evidence in the slice for why the live layer exists — both defects were **green
across the entire unit layer**:

1. **The filter excluded on a field with no payload index.** Qdrant answered `400 Index required but not
   found` for every filtered search, because `must_not` names `user_story_id` and only `workspace_id`,
   `project_id` and `has_invalid_tasks` were indexed. The adapter's graceful degradation turned that hard
   refusal into an **empty list**, so **few-shot retrieval would have been silently disabled in
   production with every unit test green**. Fixed by indexing `user_story_id` as `KEYWORD`.
   The design's own index list was **incomplete**: it named three fields while the filter it ships
   filters on four.
2. **An absent point is not a quiet success.** The setter's contract says a missing point is a no-op; the
   unit case assumed a quiet return, and the live server answers `404 No point with id …`. The setter now
   honours the documented no-op by shape, and the residual risk is named: a server re-wording would
   reintroduce the raise.

Both fixes were verified against the real service (the 22 live cases above), and the three unit pins that
asserted the index set moved to four under explicit authorization.

## 4. What the version now records (the snapshot contract, verified in the unit layer)

`prompt_config` carries exactly six keys — `validate`, `system_prompt`, `few_shots`,
`project_context`, `story_text`, `negative_examples_omitted` — read from
`RenderedPrompt.template_variables` and never re-derived; `negative_examples` deliberately travels in
`prompt_rendered` instead; `usage` is added by `record_usage` **only when the provider returned one**, so
"the provider reported nothing" never becomes a zero or an empty dict. A run whose provider failed keeps
every key but `usage` and a non-null `prompt_rendered`; a run that died before render keeps
`prompt_rendered IS NULL`.

## 5. The statement-count baseline (to be confirmed by 4.2)

This change records the baseline as **≈16 fixed statements + ≈2 per task**, plus the call-site delta of
the three context reads. The earlier "~8 + 1" figure is **not** repeated as measured. 4.2's ladder is what
turns this into a measurement; until it runs, this row is a stated baseline and not a number.

## 6. Pending, explicitly (Phase 4, operator-run)

| Task | What it needs | Status |
| --- | --- | --- |
| **4.1** per-provider `usage` confirmation | one reachable generation provider per adapter, with credentials. The owner is providing **Gemini**; Ollama is not running on this host and no OpenAI/Anthropic key exists here, so those rows will read **"not confirmed"** — which is not the same as "absent from the provider" | **pending** |
| **4.2** D20's 1 / 50 / 200 ladder | a Neon-like database **with a direct connection** (the dev pooler is excluded by name: its ~2 s per-statement floor would measure the pooler instead of the prompt) | **pending** |
| **4.3** the mandatory 1000-story project | the same database, one CSV import of 1000 rows and one run. **Exactly two outcomes are legitimate**: a stored version whose size and duration are recorded, **or** a provider rejection recorded as a finding (by D22 that run consumes a version number and produces nothing). Nothing in the extraction path may be changed to make it pass | **pending** |
| **4.4** this report's tables | the numbers from 4.1–4.3 | **pending** (this file is its skeleton) |

**The rule these rows inherit:** a rejection or a failure at 1000 stories is a **recorded finding**, not
a red test to retry until green, and **1000 is a floor** — `MAX_ROWS = 1000` caps one uploaded file, not
a project, so a second import crosses it.

## 7. Bottom line

The code of slice (c) is complete and green where it can be checked on this machine, the live vector
layer is verified against the real service, and the two defects it caught are fixed and re-verified. The
**measurements that require real provider credentials and a Neon-like database have not run**, and this
report says so instead of borrowing the unit layer's green for claims it cannot support.
