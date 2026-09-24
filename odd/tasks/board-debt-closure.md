# ODD Feature: board-debt-closure

> **Status**: **complete** — closed 2026-09-24. **T2 landed** (`325410d`, 13 files) and passed an
> independent verification; **T6 landed** (`639a585`) after asking the owner about two rows the evidence
> contradicted; **T3 landed** (`44202d6`) with the browser run recorded in `docs/testing.md`. T1, T4 and
> T7 sit with the vault peer, which reports the board closed. Final gates green. Delivered as PRs #17,
> #18 and #19; the release is `make bump` on `main` **after** the merges, because this repository
> rebase-merges and would orphan a tag created earlier — see "Delivery".
> **Created**: 2026-09-24
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/board-debt-closure`, off `main` @ `74e72c2`.
> **Receipt-driven development**: **off** in this clone (decided by clone_local); global is on. Read
> this session, not copied forward.
> **Release target**: **`v0.5.1`** (PATCH), decided by the owner on 2026-09-24. The batch is debt
> closure, so the honest bump is PATCH; `0.6.0` stays free for the version that actually adds a
> capability. See "The version number is earned, not chosen".
> **TDD**: **not configured in this project.** No TDD setting exists under `.pi/`, and neither
> `AGENTS.md` nor `CONTRIBUTING.md` mandates it. Ordinary functional checks are the requirement.
> Runner: `backend/.venv/bin/pytest` (focused per task, full at closure), `backend/.venv/bin/ruff`,
> `frontend/pnpm vitest run`.

## Problem

The owner's board (`~/Documents/second-brain/01 - Projects/Storico/Storico — Kanban.md`) holds six
cards across `Todo` and `In Progress`. He asked this batch to carry all of them plus everything
fixed since `v0.5.0`, to move the cards that are already done to `Done`, and to be told when the
Qdrant `/health/services` card came up.

Measured before writing a line, **two of the four `Todo` cards are already closed** and a third has
no work in it, so the batch is smaller than the board suggests. What is genuinely left is one code
removal, one browser verification, and the bookkeeping that follows.

## Findings measured before writing

| # | Finding | Evidence |
| --- | --- | --- |
| B1 | **The cloud end-to-end extraction card is closed.** A real story extracted from `storico.vercel.app` produced 12 tasks and one point in `storico_extractions_prod`, carrying the matching `workspace_id` and `user_story_id`. | `odd/tasks/rag-per-environment.md`, "Production confirmation (2026-09-24)" |
| B2 | **The Qdrant `/health/services` probe card is closed, code and production.** `c729e20` moved the probe from `/health` to `/healthz`, sent the `api-key` header, and added a real `embeddings` probe. In production the route then answered `qdrant: ok` (517 ms) and `embeddings: ok` → `google` / `gemini-embedding-001` / 768. The 517 ms against the 8.7 ms the broken probe reported is the signature that separates a cloud round trip from a refused local connection. | `c729e20`; `odd/tasks/rag-per-environment.md`, "Production confirmation" |
| B3 | **The seed card has no work in it.** The one-time seed job migrates legacy `few_shot_examples` values into Qdrant; the rows hold `null`, so there is nothing to migrate. | `odd/tasks/qdrant-few-shot-verification.md`, N4; the repo retains the column "read-only until this job has run" (`src/storico/cli/seed_few_shot.py`) |
| B4 | **The column drop reaches 12 tracked files, not one.** The legacy column is declared in the ORM model, mapped by the repository, carried on the domain entity, neutralized in prompt resolution, documented in `docs/database.md`, and read by the seed CLI plus three of its tests. One delete is not enough and requires a schema revision. | `grep -rn "few_shot_examples"` over `backend/`, `docs/`; count per file below |
| B5 | **Nothing implements Sentry or correlation IDs.** Neither string appears anywhere in `backend/src` or `frontend/src`; `prod.todo.md` lists both as pending. | `grep -rni "sentry\|correlation"` → 0 hits |
| B6 | **The Playwright card is not "Playwright", it is an orphan.** `frontend/e2e/few-shot-examples.spec.ts` imports `@playwright/test`, which is not in `frontend/package.json`, so the file cannot run; `docs/testing.md` records the same gap and lists E2E as `🔲 V2`. | `frontend/package.json`, `docs/testing.md` |
| B7 | **A bare `cz bump` cannot produce `0.6.0` from this history.** Since `v0.5.0` the log holds 15 `docs` and 7 `fix` commits, zero `feat`; the remaining batch work is `refactor` (PATCH) and `test` (no bump). So the honest next version is `0.5.1`. The three manifests already carry `0.5.0` and match the tag, so the bump precondition holds. | `git log --format=%s v0.5.0..HEAD \| sed 's/(.*//' \| cut -d: -f1 \| sort \| uniq -c`; `make bump` in `Makefile`; `release-versioning.md` established fact 3 |
| B8 | **The board contradicts `prod.todo.md`.** The board's `Done` column holds "Rotación de la clave maestra de cifrado" and "Auditoría de variables de entorno en el deploy", and `prod.todo.md` marks both `🔲 pendiente`. Reported, not resolved: which side is wrong is the owner's call. | the board file vs `prod.todo.md`, "Seguridad" |
| B9 | **The vault is owned by a live peer session and is dirty.** It has uncommitted edits to the board and to the project notes, so this batch must not write there directly. | `git status` in `~/Documents/second-brain`; the advertised session |

## Scope decisions (owner, 2026-09-24)

| # | Decision | Choice |
| --- | --- | --- |
| D1 | Where extraction versioning lands | **`0.7.0`, not this batch.** The board's `0.6.0` idea was the milestone label; the version that carries versioning is `0.7.0`. |
| D2 | Whether the project description becomes extraction context | **`0.7.0`.** It is not extraction-versioning, but it belongs with it, not with a debt-closure release. |
| D3 | How the E2E card is attacked | **ego-browser, no new dependency.** Playwright stays out of `package.json`; the verification is a reproducible browser guion plus evidence. |
| D4 | Where Sentry + correlation IDs go | **Out of this batch, into `0.8.0`,** which will be dedicated to observability. The vault gets a note carrying everything needed so `0.8.0` does not start from zero. |
| D5 | The version number | **`0.5.1`.** Debt closure is PATCH; the number is earned by the commit types, not chosen. |
| D6 | Whether the master-key rotation was performed | **Not applicable**, decided by the owner on 2026-09-24: with one encrypted workspace credential in production, rotating was not needed. |
| D7 | Whether the env-var audit covered Vercel | **Only the VM.** So the row stays partial rather than closing. |
| D8 | Which collection dev writes to | **`storico_extractions_dev`**, the documented one. The local `.env` now sets it. |

### The version number is earned, not chosen

`make bump` runs a bare `cz bump`, and `cz_conventional_commits` reads the log since the tag: `feat`
is MINOR, `fix`/`refactor`/`perf` PATCH, and `docs`/`test`/`chore`/`style`/`ci`/`build` do not bump.
With no `feat` in this history, the release is `0.5.1`. This repository already shipped two tags
(`v0.3.1`, `v0.3.2`) whose manifests were silently skipped because they lagged the tag, so the
honest number is recorded here rather than forced.

## Tasks

| ID | Task | Scope | Route | State |
| --- | --- | --- | --- | --- |
| T1 | Close the three already-settled board cards with their evidence, and record why the E2E card is not Playwright. | vault (delegated to the vault peer) + this file | delegated | relayed |
| T2 | Remove the legacy `few_shot_examples` column: revision `0027`, ORM model, repository, domain entity, prompt resolution, the seed CLI that read it, its tests, and `docs/database.md`. | `backend/` and `docs/database.md` | delegated writer | **landed** (`325410d`) |
| T3 | Verify the product end to end in a real browser with ego-browser: mount/unmount under View Transitions, the few-shot settings flow, and the extraction → tasks path. Retire or convert the orphan Playwright spec. | `frontend/e2e/`, `docs/testing.md` | delegated (browser session) | pending |
| T4 | Vault bookkeeping: move the closed cards to `Done`, move Sentry + correlation IDs out of `In Progress` to `Backlog` marked `0.8.0`, and write the `0.8.0` observability note. | vault (delegated to the vault peer) | delegated | relayed |
| T5 | Close: report the verified outcome, the failed/skipped/pending checks, and hand the release (`make bump`) to the owner. | this file | inline | pending |
| T6 | Reconcile `prod.todo.md` with the owner's decisions and with the measurements taken this session, and state in `docs/deployment.md` the dev half of the per-environment collection contract. | `prod.todo.md`, `docs/deployment.md` | inline — two single-purpose text edits, and the parent held the only measurement and the owner's answers | **landed** (`639a585`) |
| T7 | Vault refresh: hand the peer the measured repository figures so `Storico — estado actual y backlog.md` stops being a 2026-09-23 snapshot. | vault (delegated to the vault peer) | delegated | pending |

## Acceptance criteria

- [x] T2: revision `0027` reaches `alembic head`, `downgrade` restores the column, and the focused
      backend suites plus `ruff` are green.
- [x] T2: `grep -rn "few_shot_examples" backend/src docs/` returns only historically true mentions,
      never a live reader.
- [x] T2: the live RAG verification in `tests/test_integration/test_few_shot_rag_qdrant.py`
      **survives** — real embeddings, real Qdrant, workspace-scoped retrieval (`16 passed` with
      `STORICO_TEST_LIVE_QDRANT=1`).
- [x] T3: every browser check has its observed result recorded, including the ones that fail.
- [x] T4: the board matches the repo, and the `0.8.0` note is actionable without re-measuring.
- [ ] T5: `make bump` produces `v0.5.1` with the three manifests rewritten in step — handed to the
      owner; the repository cannot close it because the bump commits and tags.

## Work unit 1 — T2: the legacy `few_shot_examples` column (landed)

Commit `325410d`: **13 files, +150 / −421**. The independent verification ran against the staged
index, so its verdicts apply to the committed tree; the only edits made after it were the three it
asked for (V2, V3, V4 below).

### Measured evidence

| Check | Observed |
| --- | --- |
| Dev rows carrying content in the column, before the drop | **0 of 14**. Nothing was lost, and the measurement stops being reproducible once the column is gone |
| Focused suites | `39 passed in 0.38s` |
| Full backend suite | `779 passed, 21 skipped, 2 warnings in 25.78s`; both warnings pre-date this change and live in untouched files |
| `ruff check` / `ruff format --check` | `All checks passed!` / `232 files already formatted` |
| `alembic heads` / `current` | `0027 (head)`, single head, before and after the round trip |
| `downgrade -1` → `upgrade head` | column restored as `jsonb`, `is_nullable = YES`; ends at head `0027` with 14 rows intact |
| Live Qdrant suite (`STORICO_TEST_LIVE_QDRANT=1`) | `16 passed in 18.14s`; teardown left **0** throwaway collections and 0 points behind |
| `grep -rn "few_shot_examples" backend/src docs/` | migration DDL/history and historically true prose only — **no live reader** |
| `grep -rn "FewShotExample" backend/ --include="*.py"` | 0 hits |

### What the verification corrected

| # | Finding | Disposition |
| --- | --- | --- |
| V1 | **`FewShotExample` was not dead at the branch point.** It had three external importers at `3ab3325`: the workspace-prompt entity, the `domain/ports/__init__.py` re-export, and the live integration test. It became dead *inside* this work unit, which deletes all three plus the module. | The code is right and the removal stays; the producer's wording was sloppy. The correct claim is "dead within this change", not "dead code left behind". |
| V2 | **The migration asserted a production row state nobody measured** ("Every production row is null/empty"), while the only database measured was dev. | Fixed before the commit: the docstring states the dev measurement, says it is pre-drop and unreproducible, and asks the deploy to confirm production's shape first, because `downgrade` restores the column but not its values. |
| V3 | **`docs/database.md` repeated the same unreproducible value claim** with no provenance. | Fixed: the note now records that the measurement is pre-drop and no longer reproducible. |
| V4 | **The `storico.cli` package was left empty.** It was created by `8ae9f2a` for the seed job this change deletes, and nothing else ever lived there. | Removed in the same work unit. |
| V5 | **The producer brief said "9 modified" files.** The real shape is 8 modified, 3 deleted, 1 added. | Recorded; cosmetic. |
| V6 | **Stale untracked build artifacts** (`backend/src/storico_backend.egg-info/SOURCES.txt`, `cli/__pycache__`) still name the deleted modules. | Not touched: they are gitignored, have no runtime effect, and are already the subject of `odd/tasks/drop-stale-build-artifacts.md`. |
| V7 | **`odd/tasks/prod-honesty-followups.md:65` cites `cli/seed_few_shot.py:109` as a live location.** | Left as written: that file is the ledger of a measurement taken on 2026-09-22, and rewriting a past measurement to match today's tree would falsify it. |

### One guarantee the conversion dropped, deliberately

`TestLiveStoredPoint` no longer asserts the payload's `model_used`, because the value it pinned
belonged to the deleted seed job. What replaced it — a rewrite of the same point id overwrites
instead of duplicating — is stronger than the assertion it replaced, and `model_used` is covered by
unit tests. Named here so a reader does not have to diff the two classes to find it.

## Work unit 2 — T6: the production checklist and the per-environment contract (landed)

Commit `639a585`: `prod.todo.md` (five rows) and `docs/deployment.md` (+12). The vault peer relayed the
owner's decisions C1–C6 and asked for `:28` and `:29` to be flipped to ✅. The repository's own evidence
said otherwise about both, so the parent asked once before writing, and the answers landed each row
where the evidence actually supports it.

| Row | The peer's ask | What the evidence showed | What was written |
| --- | --- | --- | --- |
| `:28` Env-var audit | ✅ | The vault runbook documents the **VM half only**: 11 variable names, none empty, and it deliberately records names and never values. Nothing anywhere covers the Vercel project. | 🟡 — VM half done and cited, Vercel half named as the blocker (D7) |
| `:29` Master-key rotation | ✅ | `prod.todo.md` itself said "la herramienta no está escrita"; `odd/tasks/encrypt-workspace-api-keys.md:156` says *"Key rotation remains unimplemented"*; `docs/security.md` never mentions rotation; `git log --all --grep` finds no rotation commit. | ✅ as **not applicable** (D6). The `v1:` prefix stays, the tool stays unwritten, and the row now records that the procedure is written down nowhere. |
| `:36` Sentry, `:38` correlation IDs | deferred | Both genuinely absent from `backend/src` and `frontend/src`; the owner chose a dedicated `0.8.0`. | 🔲 with "Diferido a `0.8.0`", pointing at the vault note that holds the scope |
| `:44` Qdrant Cloud + embeddings | owner's call | **Measured this session** against production: `qdrant: ok` 465 ms, `embeddings: ok` → `google` / `gemini-embedding-001` / 768 dims, `vector_length: 768`; the cluster holds `storico_extractions_prod` with 1 point. | ✅ on the measurement, not on a decision |

The rotation row also carried a soft hyphen (U+00AD) inside "Rotación", which made `grep 'Rotación'`
miss it — the kind of invisible trap that makes a search-based audit report a false all-clear. Removed.

### Findings measured this session

| # | Finding | Evidence | Disposition |
| --- | --- | --- | --- |
| F1 | **The documented dev collection does not exist.** `docs/deployment.md:86` promises dev uses `storico_extractions_dev`; the local `.env` never set `STORICO_QDRANT_COLLECTION`, so dev wrote to `storico_extractions`. | `GET /collections` → `storico_extractions` (19 points), `storico_extractions_prod` (1 point); `storico_extractions_dev` absent | Fixed in `docs/deployment.md` and in the local `.env`. Nothing has been written to the new collection yet: the running backend still holds the old environment |
| F2 | **A healthy production reports `degraded`.** In prod `/health/services` answers `ollama: error` — the VM has no Ollama on purpose — and that one probe drags the global `status` down. | prod `/health/services` → `status: degraded`, `ollama: error` 8.7 ms, everything else `ok` | Reported, not changed. Anyone alerting on `status != ok` holds a permanent false alarm, and the probe asks about a provider production does not use. Material for `0.8.0` |
| F3 | **Three status lists, drifted.** `docs/deployment.md`'s deployment table and `docs/security.md`'s production checklist both overlap `prod.todo.md`, which declares itself the single list, and they disagree with it: CORS is ✅ in `prod.todo.md` and pending in both others; the custom domain likewise. | the three files read side by side | **Reported, not changed: this is new scope and needs the owner's authorization** |
| F4 | **`/health` reports the wrong version in dev.** Dev answers `0.3.0` while the tag is `v0.5.0`, because the endpoint reads installed metadata and this venv's dist-info dates from when `pyproject.toml` said `0.3.0`. | dev `/health` → `0.3.0`; prod `/health` → `0.5.0`, since the image installs from `pyproject.toml` at build time | Reported: a stale local venv, not a code defect and not a production lie. `pip install -e .` refreshes it |
| F5 | **The vault runbook contradicts the cluster.** "Gestión de la VM de producción de Storico" states that `storico_extractions_prod` *"todavía no existe"*; it holds 1 point. | `GET /collections/storico_extractions_prod` → `points_count: 1` | Reported to the vault peer |

## Work unit 3 — T3: the browser verification (landed)

Commit `44202d6`: the orphan Playwright spec retired, and `docs/testing.md` (+69/−8) now carries the
guion that was executed instead of the line that promised Playwright.

### What the browser run measured

| # | Check | Observed |
| --- | --- | --- |
| 1 | No session | `/en/dashboard` redirects to `/en/login?redirect=%2Fdashboard` |
| 2 | Real OAuth login | Dashboard renders `Angel Valdés` / `angelluis2605@gmail.com`, workspace `preflight-185458`, role `Admin` |
| 3 | Island hydration + real API data | Metrics `Projects 1`, `User Stories 1`, `Extractions —`, and the recent story listed |
| 4 | View Transitions across five routes | Dashboard → Stories → Dashboard → Kanban → Settings → story detail; URLs and titles correct, and the shell re-rendered (element refs changed between pages) |
| 5 | Workspace settings | LLM config (provider, model, temperature, tokens, base URL) **and** Prompt Configuration with "Automatic few-shot examples": max examples 2, similarity threshold 0.50. The legacy "Add Example" editor is **absent** |
| 6 | Story list and detail | `Pending Extraction`, the full story, and the parts (Actor `user`, Feature `reset my password by email`, Benefit `I can sign in again`) |
| 7 | **Extraction end to end** | `POST …/extract/` → `202`, `EXTRACTING` → `EXTRACTED`, **six tasks** rendered; extraction `01a0d55a-9f77-7e31-8dd4-0f79e208b835` completed |
| 8 | The RAG write, in the new collection | `Created Qdrant collection 'storico_extractions_dev'` plus its `workspace_id` index; `green`, 768 dims, Cosine, **1 point** carrying this workspace's id |
| 9 | The `pending` render, for real | "Extracting... / This can take up to a minute" observed in the browser — the state `docs/testing.md` gap 1 says no test observes |
| 10 | Kanban drag & drop | Backlog 6 → 5, To Do 0 → 1, via the grip handle; `PUT /api/v1/tasks/01a0d55b-…` → `200`; still 5/1 after a full reload |
| 11 | Console | **Zero** exceptions and zero non-informative entries across the flow, captured through CDP `Runtime` + `Log` |

Check 8 is the second end-to-end confirmation of T6's contract: the collection the documentation names
is now the one dev writes to, created on first use.

### Two findings, and two errors of my own instrument

| # | Finding | Disposition |
| --- | --- | --- |
| F6 | **Dev latency makes a correct page look broken.** Through the Astro proxy the calls took 1.7 s–31.8 s (`/api/v1/stories/ 31806ms`, `/stories/<id> ~7800ms`, `/tasks/ ~7350ms`, `/users/me ~3200ms`). | Recorded in the guion. A dev-loop observation, not a production number, and the reason the run needed 15 s waits |
| F7 | **Every list call costs an extra `307`.** The frontend requests `/api/v1/stories?page=1` and FastAPI redirects to the trailing-slash form; same for `/workspaces`, `/projects`, `/tasks`, `/extract`. | Pre-existing and already documented in `honest-llm-copy-and-doc-drift`; recorded, not fixed — doubling the round trips on a slow dev loop is worth a card, not a drive-by |
| I1 | **I concluded twice from a loading state.** The settings page and the story list both looked empty and both rendered correctly seconds later. | Both corrected; the lesson is written into the guion's traps table |
| I2 | **I called the drag & drop broken.** Two mouse attempts on the card body did nothing. The handle is the **16×16 grip icon** — `KanbanCard.tsx` spreads `dragHandleProps` there — and the third attempt, on the handle, moved the card. | The app was right and the instrument was wrong. Recorded as the first trap in the guion |

## Closure (T5)

Final gates on `fix/board-debt-closure` @ `44202d6`:

| Gate | Observed |
| --- | --- |
| Backend suite | `779 passed, 21 skipped, 2 warnings in 31.16s` |
| Backend lint | `ruff check` clean; `ruff format --check` clean over 232 files |
| Frontend suite | `37 files / 425 tests passed` |
| Alembic | `0027 (head)`, single head |
| Live RAG suite | `16 passed` with `STORICO_TEST_LIVE_QDRANT=1` (run during T2's verification) |
| Tree | clean; seven commits on `fix/board-debt-closure`, then split into one branch per logical unit and pushed as PRs #17, #18 and #19 |

### Handed to the owner

- **`make bump`**, which produces `v0.5.1`. The commit types earn PATCH (`refactor` and `fix`, no
  `feat`), and the precondition holds: the three manifests carry `0.5.0` and match the tag. It commits
  and tags, so it stays the owner's call, and it must run with a clean tree and no other session
  mid-flight.
- **Push and pull-request decisions.** Nothing is pushed. The forecast (~670 authored lines, two
  whole-file deletions) already justifies this as one unit, but the slicing is the owner's call.
- **Three things that need authorization before anyone touches them**: the drifted status lists (F3),
  the `degraded` global health status (F2), and the extra `307` per list call (F7).

### Left running

The backend (`127.0.0.1:8000`) and the frontend (`:4321`) are still up from the T3 run, with logs in
`/tmp/storico-backend.log` and `/tmp/storico-frontend.log`. The dev database is at head `0027`, the
local `.env` points at `storico_extractions_dev`, and the single point that run wrote is real data in
the real cluster.

## Delivery — three pull requests, and why the bump comes last

The batch is three logical units, and `CONTRIBUTING.md:189` asks for one logical change per pull
request. The owner chose the split, so each unit went out on its own branch off `main`, with no file in
common between them:

| PR | Branch | Contents |
| --- | --- | --- |
| [#17](https://github.com/alvaldes/storico/pull/17) | `refactor/drop-few-shot-column` | The column removal (13 files) plus this feature document, which records the batch's plan, its decisions, its verification and its open findings |
| [#18](https://github.com/alvaldes/storico/pull/18) | `docs/prod-todo-reconcile` | `prod.todo.md` and the dev half of the per-environment collection contract |
| [#19](https://github.com/alvaldes/storico/pull/19) | `test/e2e-browser-guion` | The orphan spec retired and the executed browser guion |

This document rides with PR #17 because it is one file whose history cannot be cut three ways: slice it
per unit and the sibling pull requests drag pieces of a document that does not exist in their own base.

### The release cannot be tagged before the merge

**Measured, not assumed.** This repository merges pull requests with **rebase**, so the commits are
re-created and their SHAs change:

| Evidence | What it shows |
| --- | --- |
| The previous batch's work-unit commits (`6e04218`, `04b743d`, `53f1693`, `ba3adc2`) are **not** ancestors of `main` | The SHAs were rewritten, so it is neither a merge commit nor a fast-forward |
| `main` carries no commit with a `(#N)` suffix, and its history holds more than one commit per merged PR | It is not squash either |
| `78d6e23 bump: version 0.4.0 → 0.5.0` — what `tags/v0.5.0` points at — is a direct commit on `main`, with no pull request of its own | The bump is committed **on `main`, after the merges** |

A `v0.5.1` tag created on a branch would point at a commit the rebase orphans, and the tag would stop
being reachable from `main`. Hence the release is `make bump` on `main` once the three merges land — the
same shape as the previous four releases.

### The merge deploys to production

`.github/workflows/deploy-backend.yml` runs on a push to `main` that touches `backend/**`, and PR #17
touches `backend/**`. Its merge rebuilds the image and applies `alembic upgrade head` inside the
maintenance window — which is what drops the column in production.

Safe by design, because no release is live during the migration. And the drop destroys nothing:
**production was measured** (2026-09-24, read-only, with the owner's authorization) before this PR
opened.

| Database | `workspace_prompts` rows | Carrying content |
| --- | --- | --- |
| dev | 14 | **0** |
| production | 2 | **0** |

Measuring it surfaced a trap worth keeping: **the obvious query lies.** Every row stores the JSONB
*scalar* `null` rather than SQL `NULL`, so `WHERE few_shot_examples IS NOT NULL` answers "14 of 14" in
dev and "2 of 2" in production. An audit that stops there reports data where there is none — and that
is exactly what the producer's first pre-check numbers looked like before the shape-aware count
corrected them. What matters is an object with a non-empty `items` array, or a non-empty array.

Production also confirmed the deploy ordering: it sits at revision `0026`, so the column is still
there and the release that stops reading it is the one this merge deploys.

## Checks (authored line forecast)

| Slice | Forecast (adds + dels) |
| --- | --- |
| T2 | ~+110 / −390, of which ~300 is deleting the one-time seed CLI and its dedicated test file |
| T3 | ~+60 / −60 (the orphan spec converted or removed, plus `docs/testing.md`) |
| Records | ~+40 / −10 |
| **Total** | **~+210 / −460 ≈ 670 authored lines** |

The forecast exceeds the ~400-line review heuristic, and the reason is two whole-file deletions that
are one coherent removal: the seed CLI exists only to read the column this batch drops. Splitting it
would leave a revision in the tree whose only reader was deleted in the other slice, so it is
recorded as one unit rather than sliced artificially. Delivery strategy: `ask-on-risk`; no pull
request is opened without the owner asking, so the slicing decision is raised at closure.

## Progress

- [x] Exploration and the six scope decisions.
- [x] Feature document, branch, Engram mirror and `todo` projection created before the first write.
- [x] T2 — landed as `325410d` and independently verified.
- [x] T6 — landed as `639a585`, after asking the owner about the two rows the evidence contradicted.
- [x] T3 — landed as `44202d6`; the browser run is recorded above and in `docs/testing.md`.
- [x] T1 — relayed; the peer reports the board closed.
- [x] T4 — relayed; the peer wrote the `0.8.0` note.
- [x] T7 — the measured repository figures handed to the peer.
- [x] T5 — closed here; `make bump` handed to the owner.

## Next step

Nothing left in this batch. The owner runs `make bump` for `v0.5.1` and decides on the push; the three
unauthorized findings (F2, F3, F7) are candidates for their own cards.
