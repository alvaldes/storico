# ODD Feature: prod-honesty-followups

> **Status**: **landed on 2026-09-24, and NOT natively reviewed.** The batch was unpushed until then: its
> five work-unit commits (`6e04218`, `04b743d`, `53f1693`, `ba3adc2` and the commit that carried this
> record) sat on the branch `fix/prod-honesty-followups` off `main` @ `ade40ff` (`v0.5.0`), green by an
> independent read-only verifier, with **zero candidates admitted by native review** for the two blockers
> recorded under "Review". It was delivered by splitting into one branch per unit and landing them as
> PRs #11-#15, which unblocks nothing about those blockers — the review is still absent. See
> "Delivered" below.
> **Created**: 2026-09-22
> **Workflow**: Organic Driven Development (ODD)
> **Receipt-driven development**: on in this clone when this batch was written (decided by global);
> **off since 2026-09-24** (decided by clone_local), because the reviewer relay could not complete.

## Problem

The Qdrant few-shot landing (`v0.5.0`) closed with four open surfaces, and all four are the same defect
class this repository has been cleaning for three batches: **the system states something that is not
true**. In two of them the false statement is what an operator or an end user actually reads.

### F13 — every RAG point stores an empty model and no confidence

`_run_extraction` (`infrastructure/tasks/extraction_task.py:460`) calls the module-level `_store_rag`
(`:527` at the time; `:535` after this batch's fix), which hardcoded `model_used=""` (`:542`) and passed no
`confidence_score`. The `extractions` row for the *same* extraction records the real model. Measured during
the 2026-09-22 live run and recorded as F13: point payload `model_used: ""` against
`extractions.model_used = llama3.1:8b`.

Consequence: the point payload — the artifact few-shot retrieval reads — cannot be filtered or ranked by
model or confidence, and it disagrees with the relational row it was derived from.

#### The cost claim in the source record is refuted

`odd/tasks/qdrant-few-shot-verification.md` stated F13 twice, and both statements claimed a cost:
its F13 row said *"Each extraction is also embedded and upserted twice for the same point"*, and its
"Still open" list repeated *"F13 also costs one extra embedding and upsert per extraction"*. **There is no
such cost.** Read from the code, not inferred:

```
routes/extraction.py:239   -> run_background_extraction
  -> _run_extraction (extraction_task.py:279)
       -> extraction_service.extract(...)                    line 393
            -> ExtractionService.extract()  lines 82-170: prompt, LLM, parse
               -> returns (parsed_tasks, raw_response). No persistence, no vector store.
       -> persists the Extraction and the Tasks itself       lines 427-450
       -> module-level _store_rag(...)   ONE call            line 460
```

The second `_store_rag` (`domain/services/extraction_service.py:341`) has exactly one caller,
`ExtractionService.extract_and_persist` (`:317`). `extract_and_persist` (`:224`) has **no caller anywhere
in `backend/src/`** — `grep -rn "extract_and_persist" backend/src/` returns its definition and nothing
else. It is covered by roughly ten tests in `tests/test_services/test_extraction_service.py`, but no
production path reaches it.

Two mutually exclusive flows therefore own one `_store_rag` each, so there is no last-writer-wins and
**exactly one embed and one upsert per extraction**. What F13 costs is fidelity, not I/O. This is the same
correction shape as F11, which fixed two claims that record had made about itself.

The independent verifier re-derived this answer without reading this record and reached the same
conclusion: *"an extraction's text is embedded and upserted exactly ONCE on the production path"*.

### F12 — under production's invocation, every application `logger.info` is dropped

`grep -rn "basicConfig\|dictConfig\|setLevel" backend/src/` found **one** hit:
`cli/seed_few_shot.py:109`. The API process configured no logging at all. `backend/Dockerfile` runs
`uvicorn storico.api.app:create_app --host 0.0.0.0 --port 8000 --factory`, whose `dictConfig` leaves the
root logger at WARNING with no handler, so records from `storico.*` propagate to nothing.

The observable the few-shot feature chose for itself (D3) is an `INFO` injection line in
`extraction_service.py`. It is emitted and discarded in production, so the feature's only runtime signal is
invisible exactly where it matters. Measured A/B during the live run: the same warm extraction logged the
marker under an INFO-configured launcher and **zero** application records under plain `uvicorn`.

### Stale records in `odd/tasks/`

The batch started from three stale `Status` headers and, following this repository's own blast-radius rule
(`advisory-closures`, decision D3: fix every live document that states the claim, never a historical
record), measured the claim before writing. It turned out to live in **nine** records.

**Three headers described work as unlanded:**

| Record | Header said | Measured |
|---|---|---|
| `schema-drift-gate.md:3-5` | "Awaiting the operator's landing decision" | landed `305b5da` → `1e5fbcb`, pushed, branch deleted; PR 2 (`ab00025`, `206dcc8`, `d473ddb`, `b9624e6`) landed too |
| `schema-drift-reconciliation.md:3` | "not started" | landed `a1d549b` → `ada0847`, pushed, branch deleted |
| `release-versioning.md:3` | "nothing pushed" | the work and the tags `v0.4.0` and `v0.5.0` are on `origin/main` |

**Six present-tense claims said nothing was pushed, and all six were false.** Measured with
`git merge-base --is-ancestor` against `origin/main`: every commit those records name is an ancestor of it.

| Record | Clause |
|---|---|
| `custom-provider-free-form-name.md:5` | `nothing was pushed` (`0d5de36`, `2e47993`) |
| `drop-per-user-llm-config.md:5` | `nothing was pushed` (`711d9cd`, `a4c92f9`) |
| `honest-llm-copy-and-doc-drift.md:5` | `nothing was pushed` (`7617b08`, `da673e8`) |
| `llm-config-validation-gate.md:5` | `nothing was pushed` (`cc22a0c`, `5e60f42`) |
| `normalize-blank-llm-fields.md:5` | `nothing was pushed` (`17e8e6f`, `7bd4ce0`) |
| `qdrant-few-shot-verification.md:314-315` | `origin/main is still at 7230c33 and the tag exists only locally` |

`qdrant-few-shot-verification.md` also carried the F13 cost claim, which was never true rather than merely
outdated, and was corrected in place.

`release-versioning.md`'s follow-up item 2 was closed with the item-1 style (strikethrough headline,
`**Done.**`, outcome) while **preserving the technical finding inside it** — that `version_provider = "scm"`
makes the tag the version source and a clean clone would compute its next bump from its highest tag, and
that the guard blocked it fail-closed.

### The frontend copy promises an export format that does not exist

Ten strings in `frontend/src/i18n/en.json` and `frontend/src/i18n/es.json` named **Trello** as something the
product exports to. The connector does not exist: `backend/src/storico/infrastructure/` holds
`cache, crypto, database, llm, tasks, vector`, and `trello` survives as a format string that the API
**refuses**. The `prod-checklist-honesty` code batch narrowed `ExportSettings.default_format` to
`Literal["json", "markdown"]` and retired the selectable option; this is the copy half that batch recorded
as a follow-up.

| Key | Promise |
|---|---|
| `landing.hero.subtitle` | "listas para exportar a Trello, JSON o Markdown" |
| `landing.features.card_3_title` | "Exportación a Trello" |
| `landing.features.card_3_desc` | "Exporta tus tareas a Trello, JSON o Markdown…" |
| `landing.faq.a5` | "Puedes exportar a Trello (directamente a tus tableros)…" |
| `docs.getting_started.step_6` | "…expórtalas a Trello, JSON o Markdown." |

## Scope, measured before writing

The instrument that answers "where is this claim stated" is `git grep`, not the finding's id. Every
location above was located that way, in the two languages, before any edit. The one-file fix was rejected:
correcting only the file an advisory names leaves the repository contradicting itself, which is the defect
class being cleaned.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | F13's scope | **Operator-selected.** Fidelity only: pass the real model and confidence into the module-level `_store_rag`. The duplicated flow stays untouched; unifying it or deleting the dead `extract_and_persist` is a separate decision with its own cost. |
| D2 | F12's shape | **Operator-selected.** `dictConfig` inside `create_app()`, not at import time (configuring the root logger as a library import side effect is what the missing configuration was supposed to avoid), with the level read from a new `Settings.log_level` defaulting to `INFO`. |
| D3 | Historical records | **Extrapolated.** Stale `Status` headers and present-tense claims are corrected because they are navigation, not evidence; the *bodies* that record what was true at the time are left as written. |
| D4 | The env templates | **Operator-selected.** `.env.example` and `backend/.env.example` are blocked for both the parent and its subagents by the harness safety policy, which refuses reads and writes on `.env*` paths. The owner authorized one scoped write and the parent applied exactly the three lines per template. |
| D5 | The dead deploy artifacts | **Operator-selected.** Documented here and deferred, not deleted: `backend/api/index.py`, `backend/vercel.json`, `backend/entrypoint.sh` and the `mangum` dependency describe a backend-on-Vercel deployment that does not exist, but nobody has verified whether a Vercel project still points at `backend/`. |
| D6 | The RDD clauses | **Operator-selected.** The eleven records that say `Receipt-driven development is **off** in this clone` are **not** corrected. Flipping them to "on" would be false — it was off when that work landed, which is why no native review ran. The honest correction is a dated note, and that is a sweep of its own. |

## What lands

- `backend/src/storico/infrastructure/tasks/extraction_task.py` — the module-level `_store_rag` accepts the
  model and the confidence, and `_run_extraction` passes what it already holds.
- `backend/src/storico/api/app.py` — logging configured in the app factory, and the module-level `app`
  exposed through a PEP 562 `__getattr__` that materializes the instance on first access, so importing the
  module stops configuring logging as a side effect while `app` stays a singleton.
- `backend/src/storico/config/settings.py` — the `log_level` setting, validated loudly.
- `README.md`, `.env.example`, `backend/.env.example` — the new variable published.
- `backend/tests/test_unit/test_logging_config.py` — eight behavioural tests.
- `backend/tests/test_api/test_extraction.py` — the payload-fidelity test, against recorded call kwargs.
- `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json` — the five promised-export keys per language.
- `frontend/src/i18n/__tests__/export-copy.test.ts` — the guard.
- Nine `odd/tasks/*.md` records — the stale claims, with F13's refutation.

## Work units

| # | Unit | Commit | Files | Review tier (as previewed by the controller) |
|---|------|--------|-------|-------------|
| WU1 | F13 payload fidelity | `6e04218` | `infrastructure/tasks/extraction_task.py`, `test_api/test_extraction.py` | `medium`, 1 lens (`review-reliability`) |
| WU2 | F12 production logging | `04b743d` | `api/app.py`, `config/settings.py`, `test_unit/test_logging_config.py`, `README.md`, both `.env.example` | `medium`, 1 lens (by analogy; never inspected) |
| WU3 | Stale records + F13 refutation | `53f1693` | nine `odd/tasks/*.md` | **not isolatable** — see Review |
| WU4 | Honest export copy + guard | `ba3adc2` | both i18n catalogs, `export-copy.test.ts` | `medium`, 1 lens (by analogy; never inspected) |
| WU5 | This record | the commit that carries it | `odd/tasks/prod-honesty-followups.md` | not reviewed |

## Gates

Run by a delegated read-only verifier (`gentle-ai-verify`) on the exact tree that is committed, after all
five writers had stopped. Nothing is staged.

| Gate | Result |
|---|---|
| `ruff check src tests` | `All checks passed!` |
| `ruff format --check src tests` | `235 files already formatted` |
| `pytest -q tests/` | **`772 passed, 21 skipped, 2 warnings`** (28.12 s, and again 25.76 s) |
| `pnpm exec tsc --noEmit` | no output, exit 0 |
| `pnpm vitest run` | **`37 files / 425 tests passed`** |

The two warnings are the pre-existing SQLAlchemy `RuntimeWarning: coroutine 'Connection._cancel' was never
awaited`, attributed to two different tests; `docs/testing.md` already records that the count is not a
property of the tree and that nothing gates on it. The 21 skips are the `integration`-marked tests.

The verifier also confirmed independently: the diff is limited to the 21 expected paths; **no real
credential, token or live connection string appears in the diff or the untracked new files**; `m.app is
m.app` → `True`; importing the module leaves `logging.root.handlers` unchanged (`[] → []`); the root-logger
fixture restores its state and running the module first and last against unrelated modules produced
identical results; and every one of the nine corrected claims, plus every line number cited, measures
exactly as written.

Two things it could not verify, recorded honestly: it did not execute the payload-fidelity test against
pre-fix code (that needs a worktree mutation, which it was forbidden), so *fails-without-the-fix* is
established from the diff plus the RED the writer observed; and it did not re-measure the live Qdrant
payloads.

## Review

**No candidate was admitted. Zero reviews burned. Nothing was corrected.** This batch is gated but
**not natively reviewed**, and that must not be rounded up to "done".

### Blocker 1 — the reviewer relay returns JSON that does not parse

Candidate WU1 (`6e04218`) started cleanly: lineage `review-cebc8be05df6f969`, tier `medium`, one lens
(`review-reliability`), 115 changed lines, `correction_budget: 58`. The capture slot was taken **four**
times and failed identically every time:

```
outcome: pi-host-relay-transport-failure
failure: {kind: pi-failed, stage: pi, exit_code: null, timed_out: false, elapsed_ms: 53-65 s,
          timeout_ms: 915732}
reason:  "Reviewer completion failed for review-reliability: Expected property name or '}' in JSON
          at position 1 (line 1 column 2)"
mutation_performed: false
```

Each attempt ran ~55 s, so the model does complete; the completion just is not parseable JSON. `/reload`
was tried between attempt 3 and attempt 4 and did not change anything. This is **not** the known
irrecoverable family (`kind: submission-refused`, `stage: submit`, which preserves the rejected bytes and
replays them): there is no `rejected-results` artifact for this lineage, so the relay never produced an
artifact at all.

The parse failing at `position 1 (line 1 column 2)` — immediately after the opening brace — is inconsistent
with prose or a fenced block (both would fail at position 0) and is *consistent* with doubled braces in the
completion, the signature of an escape/template artifact. That is a hypothesis, not a measurement: the
relay prompt was not inspected.

The native state stayed consistent through all four attempts: `state: reviewing`, `generation: 1`, stable
`revision`, `mutation_performed: false`, no rejected payloads, no burned authority. The failure lives
entirely in the transport, not in the review authority.

### Blocker 2 — only the first commit after the branch point is isolatable

Independent of the relay, and it would block even a lens-free candidate. `gentle_review` with
`operation: inspect` derives the candidate as **`merge-base(HEAD, default branch)` → HEAD** — the branch
point — and does not accept an override:

| Attempt | Result |
|---|---|
| `inspect` with `{"baseRef": "<parent sha>", "committedOnly": true}` | fields accepted, **projection unchanged** |
| `inspect` with the parent as a **ref name** (temporary branch) | same, unchanged |
| `inspect` with `{"mode":"ordinary", ...}` | `native-inspect-input-invalid`, `unknown-field`, `field: mode` |
| `start` with `input.baseRef = <parent sha>` | `candidate-target-projection-drift`, `lineage_created: false`, `mutation_performed: false` |

So on a branch with sequential commits, the projection is the accumulated range and the contract forbids
reviewing the accumulated branch. WU1 isolated correctly **only because its parent is the branch point**.
WU3 projected all 17 accumulated paths instead of its 9 documents, and no override reduced it.

The actionable lesson for the next attempt: **advance the branch point after each landed unit** (or use one
branch per work unit), rather than committing every unit on one branch and reviewing them at the end. The
previous session's note that per-commit isolation "worked cleanly in all 10" does not reproduce today and
should not be trusted.

### What was deliberately NOT done

The lens verdict was **not** authored by the agent. Lens, refuter and validator verdicts are admitted
natively and never Pi-authored; fabricating the reviewer artifact to unblock the gate would have been
exactly the shortcut this batch exists to remove. No native harness state was deleted or hand-edited, and
the branch history was not rewritten.

## Delivered

The batch landed on **2026-09-24**, after the two blockers under "Review" kept it unpublished for two
days. Nothing about those blockers was resolved: what changed is the delivery route.

- The five work-unit commits were split into **one branch per unit off `main`**, because `inspect` derives
  the candidate from the branch point and a branch of sequential commits cannot isolate a unit. Each unit
  kept one commit, and the landed commits carry a `patch-id` **identical** to the ones the original branch
  had.
- They landed as pull requests **#11** (`fix/rag-point-model-confidence`), **#12**
  (`fix/application-logging`), **#13** (`fix/trello-export-copy`), **#14**
  (`docs/record-status-corrections`) and **#15** (this record). The original branch
  `fix/prod-honesty-followups` was deleted afterwards: it held nothing the five did not.
- Every unit was **re-verified on its own base** before landing, not merely cherry-picked. `#11`: 764
  passed, 21 skipped. `#12`: 771 passed, 21 skipped. `#13`: `tsc` clean and 425 frontend tests passed.
- The operator **disabled the review switch for this clone** on 2026-09-24
  (`review mode disable --scope clone`), after the relay failed in two distinct ways: the unparseable
  completion recorded under "Review", and later `reviewer-empty-output` with `reviewer.stopReason:
  length` on another candidate. Delivery therefore followed the repository's ordinary policy.

**This does not convert the missing review into an approval.** No lens verdict exists for any of the five
units, none was authored by the agent, and re-attempting the review stays open.

## Still open after this batch

1. **The native review of this batch.** The five units are landed and still unreviewed. The branch
   arrangement the re-attempt needed now exists — one unit per branch off `main`, which is the shape
   `inspect` can isolate — so the only remaining blocker is the relay.
2. **F10** — the poll response's `tasks` field is always empty. Unchanged by this batch.
3. **The duplicated extraction flow** — `ExtractionService.extract_and_persist` is production-dead while the
   background task re-implements its persistence. D1 deliberately leaves it; it is a real design decision,
   not a cleanup.
4. **The 16 advisories** from the `v0.5.0` landing, all `SUGGESTION` / informational.
5. **The test data in live services** — ten verification workspaces and eighteen points in
   `storico_extractions`. Removing it is a destructive mutation and stays a decision.
6. **`prod.todo.md`'s remaining items** — rate limiting, the env-var audit, master-key rotation, the
   transport error echoed by `POST /api/v1/llm/test`, Sentry, correlation IDs, Qdrant Cloud plus an
   embedding adapter, the domain and SSL, the Trello connector, and the thesis evaluation.
7. **Three tracked artifacts describe a backend-on-Vercel deployment that does not exist** (D5).
8. **The RDD clauses in eleven records** (D6).
