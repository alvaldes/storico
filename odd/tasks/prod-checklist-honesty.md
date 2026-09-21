# ODD Feature: prod-checklist-honesty

> **Status**: **PR 1 landed on `main`; PR 2 committed on `fix/retire-trello-option-and-dead-settings`,
> independently verified, and awaiting native review.** This record is the resume point — read it
> first, then the section "Resuming in a fresh session" at the end.
> - **PR 2 (code) — COMMITTED AND VERIFIED, NOT LANDED.** Branch
>   `fix/retire-trello-option-and-dead-settings` off `main` @ `fc59dc5`. Five work-unit commits —
>   `c5683b8` (WU4), `79d57dc` + `073a5f8` (WU5), `f5f82e0` (WU6), `1af649d` (WU7) — plus this
>   record's own commits, which add no code; 18 files. `git log fc59dc5..HEAD` is authoritative for the
>   tip, since counting this record's commits here would be self-referential. All five gates re-run
>   independently and green: backend `ruff check`, `ruff format --check`, `pytest -q` (705 passed,
>   1 skipped, 1 pre-existing `RuntimeWarning`); frontend `tsc --noEmit`, `vitest run` (421 passed,
>   36 files). No blocking finding; see "Independent verification" below. **Native review approved and
>   burned** — `review-bde8183340bdb47b`, `risk_tier: medium`, one lens (`review-reliability`),
>   `changed_files: 18`, `original_changed_lines: 472`, `correction_budget: 200`, two non-blocking
>   advisories. **Landed**: `git merge --ff-only` `fc59dc5` → `61a132b`, pushed, CI run `35563349443`
>   green and backend deploy run `35563349521` green; production probed healthy afterwards.
> - **PR 1 (docs) — DONE.** Branch `docs/honest-prod-claims`, four commits (`f147029`, `6f480c8`,
>   `d523492`, `b196589`), fast-forwarded into `main` (`fb48732` → `b196589`), branch deleted, pushed,
>   CI green (run `35554779323`). The backend deploy did not trigger, correctly: its `paths` are
>   `backend/**` and its own workflow file. Native review `review-bf9c1b2604557eac` came back
>   **approved** and its authority is **burned** (`gentle-ai.review-acknowledged/v1`).
> - **PR 2 (code) — NOT STARTED.** Branch `fix/retire-trello-option-and-dead-settings`; work units
>   WU4–WU6 below. Nothing has been written for it.
>
> Receipt-driven development is **on** in this clone (`~/.gentle-ai/state.json`,
> `rdd_mode_recorded_at = 2026-09-19T18:49:02Z`), so a native review is expected per candidate — but
> **the tier depends on which files are touched**. The two earlier markdown-only candidates came back
> `risk_tier: low` / `non_executable_only`; PR 1 came back **`medium`** with the `review-reliability`
> lens required, because its `risk_reasons` named `{"code": "executable_change", "path":
> "AGENTS.md"}`. `AGENTS.md` is the file that governs agent behaviour in this repository, so the
> provider does not treat it as passive documentation. PR 2 touches no instruction file and should be
> judged on its own content.
> **Created**: 2026-09-21
> **Workflow**: Organic Driven Development (ODD)

## Problem

`prod.todo.md` is the single production checklist, and `AGENTS.md` and `docs/deployment.md` are the
documents it points at for detail. Measuring those claims instead of reading them turned up **six
that are false today**, plus one user-visible option that promises something the system cannot do.

The trigger was the 2026-09-20 incident: an applied-by-hand migration left the schema at `0021`
against a head of `0024`, extraction failed 56 times, and none of the three documents involved
said so. This record closes the claims that measurement refuted and retires the dead option,
before a seventh claim expires on top of these six.

### Claims measured, and what the measurement said

| # | Claim | Where | Measured | Verdict |
|---|-------|-------|----------|---------|
| C1 | "El test de integración se saltea sin Docker. Correrlo al menos una vez antes de desplegar." (🟡) | `prod.todo.md` | CI run `35546955633`: `tests/test_integration/test_projects_integration.py::test_list_projects_with_counts_latency_under_500ms` **ran**, job ended `703 passed`. `pytest.ini` registers the marker but does not deselect it; `ci.yml` runs a bare `pytest -q` with no filter; `testcontainers>=4.9.0` is a dev dependency and GitHub runners have a Docker daemon (which is what `_docker_reachable()` probes). | **False as a premise** — it runs on every push. The skip describes a laptop without a daemon. |
| C2 | "Hoy toma `STORICO_AUTH_ALLOWED_ORIGINS`; revisar que en producción no incluya orígenes de desarrollo." (🔲) | `prod.todo.md` | Probe run inside the live container, printing booleans and never the value: `ORIGENES_DECLARADOS: 1`, `USA_EL_DEFAULT_LOCALHOST: False`, `CONTIENE_LOCALHOST_O_127: False`, `CONTIENE_VERCEL_APP: True`, `CONTIENE_HTTP_SIN_TLS_NO_LOCAL: False`. | **Already satisfied** |
| C3 | "Conector Trello ✅ MVP" | `AGENTS.md` (feature table, #25) | `infrastructure/` holds `cache, crypto, database, llm, tasks, vector` — there is no export adapter and no connector package. `trello` survives only as a format string and as a lucide icon name. | **False** |
| C4 | "`POST /api/v1/llm/test` ecoa el error de transporte — sus cinco ramas devuelven `{e}`." (🔲) | `prod.todo.md` | Confirmed verbatim at `api/routes/settings.py:166,199,232,265,306` (`message=f"... connection failed: {e}"`). Its sibling `POST /llm/models` is already correct: it publishes the provider and the status and logs the exception with `exc_info`. | **True** — the item stands as written |
| C5 | "Backend: FastAPI en Vercel (serverless)"; "PostgreSQL (proveedor pendiente de definir)"; "CI/CD: Pendiente de definir" | `docs/deployment.md:72,69,77` | The backend runs as a container on an Oracle VM (`deploy-backend.yml` → ssh → `docker run --network host`); the database is Neon (the `sslmode` normalization in `alembic/env.py` and `infrastructure/database/base.py` exists for it); `ci.yml` and `deploy-backend.yml` both exist and run. | **False** — it describes a different architecture |
| C6 | ADR-005 "Producción sin definir" (🔴 PENDIENTE) | `AGENTS.md` | Production is defined and running: Astro front on Vercel, FastAPI in Docker on the Oracle VM, Neon for Postgres, Qdrant not yet configured. | **False** |

C5 is not cosmetic: it is why the same checklist proposes "**Vercel WAF**" for rate limiting
(`prod.todo.md`, `docs/security.md:98`). A WAF in front of Vercel cannot protect an API that is not
served by Vercel.

### The dead option

`trello` is a **selectable setting nothing can honour**:

| Layer | File | Says |
|-------|------|------|
| Type | `frontend/src/types/settings.ts:1` | `export type ExportFormat = 'trello' \| 'json' \| 'markdown'` |
| UI | `frontend/src/components/react/AccountPage.tsx:236` | `<SelectItem value="trello">` — selectable and persisted |
| i18n | `frontend/src/i18n/{en,es}.json:329` | `"export_format_trello": "Trello"` |
| Contract | `backend/src/storico/api/schemas/settings.py:35` | `Literal["trello", "json", "markdown"]` |
| Endpoint | `backend/src/storico/api/routes/export.py:89` | `Unsupported format 'trello'` → **400** |

`ExportPanel.tsx:21` holds `useState<'json' | 'markdown'>`, so the 400 is not reachable from the
export panel: the failure is that Configuration **offers** a format the API refuses. That is the
same class as `provider-literal-and-copy-drift` and `honest-llm-copy-and-doc-drift`.

Two more files carry the same string as a fixture and will have to move with the decision:
`frontend/src/stores/__tests__/settingsStore.unit.test.ts:86,92` and
`frontend/src/components/react/__tests__/AccountPage.test.tsx:86`.

`backend/tests/test_unit/test_drop_user_preference_llm_migration.py:182,188` also contains
`{"export": {"defaultFormat": "trello"}}`, but its `_seed` writes through a SQLAlchemy `Session`
against the metadata table, so it never crosses the Pydantic schema and is unaffected.

### The two dead settings

`config/settings.py:37-38` declares `rag_similarity_threshold` and `rag_max_examples`. Nothing reads
them: the retrieval threshold is a **parameter with its own default** on
`qdrant_adapter.search_similar(threshold=0.85, ...)`, and the value that actually reaches it comes
from the per-workspace prompt config (`extraction_task.py:349` →
`getattr(ws_prompt, "few_shot_threshold", 0.85)`). `backend/.env.example:33-35` documents three
`STORICO_RAG_*` variables that configure nothing.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Fix the claims or delete the checklist | **Fix them.** The checklist is the single list by its own charter, and the failure mode above is a stale claim, not a redundant file. |
| D2 | Split the work | **Two PRs.** Docs and code have different review needs; bundling eleven files across three areas into one diff is a reviewer's tax with no benefit. |
| D3 | `trello` handling | **User-approved: normalise on read.** Narrow the `Literal` to `["json","markdown"]`, remove the option from the UI and the type, and normalise a stored legacy `trello` to `json` when it is read. Follows the precedent this very file already sets for the `llm` key (`REMOVED_PREFERENCE_KEYS`, "a document written before the removal still validates"). Production's `user_preferences` is **empty** (measured: 0 rows), so there is nothing to migrate. |
| D4 | The alternative to D3 | **Rejected: a data migration.** A new Alembic revision rewriting stored `trello` → `json` is the tidiest answer for other databases, but in production it would be a no-op over zero rows — and it would add a migration at the exact moment we know migrations are not applied by the deploy. Paying a manual production step for zero data is the wrong trade. |
| D5 | Dead settings | **Delete them** (`settings.py` + the three `.env.example` lines), rather than leave them documented as knobs. A documented knob nobody reads is a lie with a name. |
| D6 | testcontainers deprecation | **Include it.** CI warns on every run: `testcontainers.postgres is deprecated, use testcontainers.community.postgres instead`. It is debt rather than a lie, and it is already in the log the previous item was measured from. **Premise corrected by measurement: "it is one import" is false.** The canonical path `testcontainers.community.postgres` exists only from **4.15.0** — `4.13.3` and `4.14.2` ship no `community` package at all (measured by direct wheel inspection) — so the swap forces the declared floor up. The user approved `testcontainers>=4.15.0`. |
| D7 | `openspec/changes/archive/` | **Untouched.** It is a historical record of what was decided then, not a live claim. |
| D8 | `.env.prod.local` | **Reported, not touched.** It has `STORICO_AUTH_ALLOWED_ORIGINS` declared twice, so the first value is silently ignored. It is untracked and local to the operator's machine; the fix belongs to whoever holds that file. |

## Work units

### PR 1 — `docs/honest-prod-claims` (C1–C6, docs only)

| WU | File | Change |
|----|------|--------|
| WU1 | `prod.todo.md` | C1 🟡 → ✅ with the CI evidence; C2 🔲 → ✅ with the probe result; the Trello item keeps 🔲 but its detail stops implying a connector exists and points at WU4. |
| WU2 | `AGENTS.md` | C3: feature #25 → 🔲 with the real state. C6: ADR-005 → production is defined and running (Vercel front, Docker on the Oracle VM, Neon, Qdrant pending). |
| WU3 | `docs/deployment.md` | C5: the whole "Producción (Vercel)" section describes the architecture that runs — Oracle VM container for the backend, Neon for the database, the two workflows that exist, and the deploy's missing migration step pointing at the open item. The "Artefactos de build del frontend" subsection is correct and stays. |

### PR 2 — `fix/retire-trello-option-and-dead-settings` (WU4–WU6, code)

| WU | Files | Change |
|----|-------|--------|
| WU4 | `backend/src/storico/api/schemas/settings.py`, `frontend/src/types/settings.ts`, `frontend/src/components/react/AccountPage.tsx`, both frontend tests | D3: `Literal` narrowed, option removed from the UI and the type, and a stored `trello` normalised to `json` on read with a test that fails without the normalisation. |
| WU5 | `backend/src/storico/config/settings.py`, `backend/.env.example` | D5: both settings removed, and so was the `# RAG settings` block — its two `STORICO_RAG_*` placeholders, their header, and the blank line below it (four lines). |
| WU6 | `backend/pyproject.toml`, `backend/tests/test_integration/test_projects_integration.py`, `odd/tasks/ci-postgres-integration-test.md` | D6, as corrected: `testcontainers.postgres` → `testcontainers.community.postgres`, **and the floor raised to `>=4.15.0`**, because the new path does not exist below it. The prior record's claim that the boundary is "≤4.12" is also corrected to `<4.15.0` — leaving it would have created the seventh stale claim this batch exists to close. |
| WU7 | `docs/api.md`, `todo.md` | **Not in the original plan.** Two claims WU4 invalidated, found by the independent verifier and approved by the operator: `docs/api.md` described the endpoint's `defaultFormat` as still accepting `trello`, and `todo.md` asserted the enum still carried the value. The pre-existing landing copy in `i18n` that promises Trello export is deliberately **not** here — approved as a follow-up. |

## Non-goals

- **The deploy's migration policy.** It is the next piece of work, it needs a decision that is not
  this record's to make, and getting it wrong can reproduce the incident in a worse direction: a
  blanket "migrate before the container swap" is right for a `0023`-shaped revision and **wrong** for
  a `0024`-shaped one (the old release would read the ciphertext and hand it to a provider as an API
  key). See the options recorded in this session's review of the checklist.
- **Enabling Qdrant/RAG in production.** The adapters already exist (`qdrant_adapter.py` creates the
  collection on first use and degrades with a warning); what is missing is two variables and an
  embeddings provider with a key, which is a decision with a cost.
- **Building the Trello connector.** WU4 retires a promise; it does not create the feature.
- **Rate limiting, Sentry, correlation IDs, a custom domain, a frontend build in CI.** Each is real
  and each is its own piece of work.

## Tasks

**PR 1 — `docs/honest-prod-claims`** — landed on `main` @ `b196589`, pushed, CI green; native review
`review-bf9c1b2604557eac` approved and burned.

- [x] WU1 — `prod.todo.md`: C1, C2 closed with evidence; Trello detail corrected.
- [x] WU2 — `AGENTS.md`: C3 and C6 corrected.
- [x] WU3 — `docs/deployment.md`: production section rewritten to the architecture that runs.
- [x] Gates for PR 1: no doc gate exists in CI (it runs `ruff`, `pytest`, `tsc`, `vitest` and no
      markdown check), so PR 1 was verified by reading the changed claims against the measurements in
      this record.
- [x] Branch, commit, native review, land PR 1.

**PR 2 — `fix/retire-trello-option-and-dead-settings`** — not started. Branch off `main` @ `b196589`.

**PR 2 — `fix/retire-trello-option-and-dead-settings`** — committed and awaiting native review. Branch off `main` @ `fc59dc5`; four commits (`c5683b8`, `79d57dc`, `f5f82e0`, `073a5f8`), 15 files.

- [x] WU4 — retired the `trello` option with legacy normalisation and its test. Landed as `c5683b8`,
      10 files: `backend/src/storico/api/schemas/settings.py` (`default_format` narrowed to
      `["json", "markdown"]`, plus `RETIRED_EXPORT_FORMATS`), `backend/src/storico/api/routes/settings.py`
      (`_for_schema` also rewrites a retired export *value*, in both spellings), `backend/tests/test_api/test_user_settings.py`,
      `frontend/src/types/settings.ts`, `frontend/src/stores/settingsStore.ts`, `frontend/src/components/react/AccountPage.tsx`,
      both frontend tests, and both locale files. The store's `merge` path is covered as well: `persist`
      rehydrates `settings.export` from `storico-settings-v2`, so a returning browser is a third source
      of the retired value alongside the API. The `export_format_trello` key left `en.json` and
      `es.json` together, keeping parity.
- [x] WU5 — landed as **two** commits, because of a tool-level guard and not ambiguity: `79d57dc`
      removed both settings from `backend/src/storico/config/settings.py`; `073a5f8` removed the
      `# RAG settings` block from `backend/.env.example` — its two `STORICO_RAG_*` placeholders and
      its header. The guard (`read`/`write`/`edit`, no
      allowlist) refuses that path name, so `79d57dc` declined to work around it and recorded the gap
      in its own message; the operator authorized the second edit explicitly.
- [x] WU6 — landed as `f5f82e0`. `backend/pyproject.toml`, the integration test, and
      `odd/tasks/ci-postgres-integration-test.md`. **The plan's premise was wrong and D6 above is
      corrected**: the canonical path exists only from 4.15.0, so the floor moved with it, and the prior
      record's "≤4.12" boundary was corrected to "<4.15.0".
- [x] Gates for PR 2: backend `ruff check src tests`, `ruff format --check src tests`, `pytest -q`;
      frontend `pnpm exec tsc --noEmit`, `pnpm vitest run`. Re-run independently rather than taken from
      the writers' reports: all five green.
- [x] WU7 — correct the two claims WU4 invalidated (`docs/api.md`, `todo.md`). Added after the
      independent verification, with operator approval. The landing copy in `i18n` that promises
      Trello export is deliberately **not** here; it is an approved follow-up.
- [ ] Branch, commit, native review, land PR 2.

## Evidence

The measurements for C1–C6 are in the table above, each with the command or file that produced it.
The entries below are the per-work-unit records.

### PR 1 review and landing

Native review `review-bf9c1b2604557eac`, target
`sha256:ea7377114496870a29e3f159762d28171b6bea8ec7047f9f4c2dad8a063a9b67`: `state: approved`,
`risk_tier: medium`, `selected_lenses: ["review-reliability"]`, `changed_files: 4`,
`original_changed_lines: 196`, `correction_budget: 98`,
`risk_reasons: [{"code": "executable_change", "path": "AGENTS.md"}]`. One reviewer was materialised
(forecast `model_runs: 1`, `transport: pi_host_relay`; `prompt_bytes: 39316`, `result_bytes: 2638`) and
the review closed on the last admitted event. Acknowledgement burned the authority:
`authority: burned`, `burn_evidence: gentle-ai.review-acknowledged/v1`,
`delivery: ordinary-repository-policy`. Landing: `git merge --ff-only` `fb48732` → `b196589`, branch
deleted with `-d`, `HEAD == origin/main == refs/heads/main == b196589`, ahead/behind `0/0`, CI run
`35554779323` green.

Three advisories were returned, all `SUGGESTION` / informational, none of which opened a correction:
`R3-evid-2` (`prod.todo.md:19`), `R3-pubip-1` (`docs/deployment.md:73`) and `R3-waf-3`
(`prod.todo.md:25`). They are deliberately **not** bundled into PR 1 — editing the reviewed tree after
approval would mean delivering something other than what was reviewed — and are carried as follow-ups
in `prod.todo.md`'s sibling work. See "Resuming in a fresh session" below.

- **WU1 — `prod.todo.md`** (commit `docs: close two production checklist items that were already satisfied`). C1 🟡→✅: CI run `35546955633` executed `tests/test_integration/test_projects_integration.py::test_list_projects_with_counts_latency_under_500ms` and the job ended `703 passed`; `backend/pytest.ini` registers the `integration` marker without deselecting it, `.github/workflows/ci.yml` runs a bare `pytest -q` with no marker filter, `testcontainers>=4.9.0` is a dev dependency, and GitHub runners carry the Docker daemon that `_docker_reachable()` probes. C2 🔲→✅: the in-container probe printed booleans only and never an origin value — `ORIGENES_DECLARADOS: 1`, `USA_EL_DEFAULT_LOCALHOST: False`, `CONTIENE_LOCALHOST_O_127: False`, `CONTIENE_VERCEL_APP: True`, `CONTIENE_HTTP_SIN_TLS_NO_LOCAL: False`. The Trello item kept its 🔲 and its detail now states the connector does not exist (`backend/src/storico/infrastructure/` holds `cache, crypto, database, llm, tasks, vector`) and that the selectable option is retired in WU4. No markdown gate exists in CI, so both texts were verified by reading them against the measurements above.

- **WU2 — `AGENTS.md`** (commit `docs: correct the Trello and deployment claims in AGENTS.md`). C3: feature table #25 went ✅ MVP → 🔲, with a `> **Nota**:` block under the Conectores table recording the real state — no export adapter and no connector package (`backend/src/storico/infrastructure/` holds `cache, crypto, database, llm, tasks, vector`; `trello` survives only as a format string) — so the three-column table stayed intact. C6: ADR-005 went 🔴 PENDIENTE / "Producción sin definir" → ✅ Decidido, naming the architecture that runs (Astro on Vercel; FastAPI container on the Oracle VM `163.192.150.75` deployed by `.github/workflows/deploy-backend.yml` via SSH + `docker run --network host --env-file /home/ubuntu/storico/backend/.env`; PostgreSQL on Neon; Qdrant contracted but not configured), and its new Consecuencias record that the deploy runs no Alembic migrations (the 2026-09-20 incident, open in `prod.todo.md`) and that the untracked VM `.env` survives the worktree reset, so a missing variable fails silently. One line adjacent to that scope was also corrected: the Stack table's **Contenedores** row said `prod: Vercel`, which is false for containers, and now names the backend container on the Oracle VM and the Astro frontend on Vercel.

- **WU3 — `docs/deployment.md`** (commit `docs: describe the production architecture that actually runs`). C5 corrected in the "Producción" section (retitled from "Producción (Vercel)"): backend is a Docker container on the Oracle VM, not Vercel serverless; database is Neon, not an undefined provider; and CI/CD is no longer "pendiente de definir" — the two workflows that exist are named with the steps `ci.yml` actually runs (`ruff check`, `ruff format --check`, `pytest -q`, `pnpm exec tsc --noEmit`, `pnpm vitest run`). The deploy mechanism is described from `.github/workflows/deploy-backend.yml` itself (SSH, `git fetch origin main`, worktree reset to `origin/main`, image rebuild, stop/remove, `docker run --network host --env-file /home/ubuntu/storico/backend/.env`). A new "Migraciones" subsection records that the deploy runs no Alembic migrations (the 2026-09-20 `0021` vs `0024` incident, 56 failed extractions) and points at the open item in `prod.todo.md` without proposing a fix. The untracked VM `.env` note explains the silent failure mode, and Qdrant is recorded as contracted but not configured. The "Artefactos de build del frontend" subsection is unchanged.

### PR 2 work units

**TDD evidence was re-derived by the parent, not taken from the writers' reports.** Both writing agents
ran the suites and reported them green, but neither returned the observed-red output the brief asked
for, so the parent reproduced it by reverting only a work unit's *source* while keeping its tests, then
re-running. Backend WU4 with `api/schemas/settings.py` and `api/routes/settings.py` at `HEAD~1`:
**3 failed, 8 passed**, the write test failing as `assert 200 == 422`. Frontend WU4 with
`types/settings.ts` and `stores/settingsStore.ts` at `HEAD~1`: **3 failed, 12 passed** across the two
changed files. Restored and verified clean at the fix commit before continuing. Without that
re-derivation the tests would have been green with nothing showing they are load-bearing.
**Self-correction:** this paragraph first recorded the frontend red as "2 failed, 9 passed" — that
figure came from a partial run in which `AccountPage.test.tsx` failed to load, so only 11 of the 15
tests executed. The independent verifier caught the undercount; the figure above was re-derived
directly.

- **WU4 — `c5683b8`**, 10 files. Backend: `ExportSettings.default_format` narrowed to
  `Literal["json", "markdown"]`; a new `RETIRED_EXPORT_FORMATS = {"trello": "json"}` sits beside
  `REMOVED_PREFERENCE_KEYS`; and `_for_schema` now rewrites a retired *value* — in both spellings the
  store can hold (`default_format`, what `model_dump()` writes, and the camel `defaultFormat`) — while
  dropping removed *keys* exactly as before. The asymmetry is the point and is observable: a stored
  `trello` reads as `json`, and `PUT` answers 422 rather than silently storing what it was not given.
  The writer added an `isinstance(..., str)` guard before the membership test, which the brief did not
  ask for and which is right — a JSON document may hold any scalar, and `in` on a dict hashes the
  value. The new tests cover both spellings of the read and the refused write, and assert the rewrite
  does **not** write back, so storage keeps its `trello`.
  Frontend: the type narrowed; `normalizeExportFormat` added (never throws; `hasOwnProperty` before
  indexing the map, so a prototype key cannot resolve to a function); applied in `loadFromApi` **and**
  in `merge`. That second call site is beyond the plan and follows from the plan's own premise:
  `persist` writes `storico-settings-v2` and `merge` rehydrates `settings.export`, making a returning
  browser a third source of a retired value. Covering it is most of the fourth file's tests, including
  a rehydrate test that drives the real `persist` path.
- **WU5 — `79d57dc` and `073a5f8`**, split by a tool-level guard rather than by design. `79d57dc` removed
  `rag_similarity_threshold` and `rag_max_examples` and left a comment in their place naming why they
  are gone, so they are not re-added as knobs. `073a5f8` removed the `# RAG settings` block from
  `backend/.env.example`: two `STORICO_RAG_*` placeholders and their header, plus the separating blank
  line — four lines. (An earlier draft of this record called them "three `STORICO_RAG_*` lines",
  conflating the header with a variable; the verifier counted the variables and found two. The
  committed diff removes four lines.)
  The guard matches `.env`-family path names for `read`/`write`/`edit` with
  no allowlist, so the first commit could not include that file; it recorded the gap in its own message
  instead of quietly narrowing the work unit, and the operator authorized a second, explicit edit.
- **WU6 — `f5f82e0`**, three files. `backend/pyproject.toml` floor `>=4.9.0` → `>=4.15.0` with its real
  reason; `tests/test_integration/test_projects_integration.py` importing
  `testcontainers.community.postgres`; and `odd/tasks/ci-postgres-integration-test.md` recording the
  supersession in its status block, its D3 row and its established-facts list. Verified without Docker:
  the old import raises under `-W error::DeprecationWarning` and the new one is silent, and
  `testcontainers.community.postgres.PostgresContainer` resolves in the project venv (which has 4.15.0).
  What could **not** be verified locally: container construction, which needs the Docker daemon
  (`DockerException: Error while fetching server API version`) and is exercised by CI. The conda env
  also still carries the legacy namespace-package layout, on which the new path does not resolve at all;
  it needs the old shim uninstalled and the dev extra reinstalled.
  **The floor is not dev-only in this repository**, which is worth knowing before landing:
  `backend/Dockerfile` runs `pip install --no-cache-dir ".[dev]"`, so the production image installs the
  dev extra, testcontainers included, and the declared floor therefore reaches the production build.
  Nothing breaks — PyPI resolves 4.15.0, and pip would already have picked 4.15.0 under the old
  `>=4.9.0` floor, so no installed version changes. But a claim that the blast radius was "CI plus
  developer machines" would be false here, and shipping the test dependencies in the production image
  is a separate observation this batch does not act on.

**Three claims in this record's own brief were refuted by measurement** and are corrected here rather
than left standing: that the testcontainers change was "one import" (it forces the floor up — see D6);
that `PostgresContainer(...)` could be constructed without a Docker daemon (it cannot); and that the
4.15.0 shim is six lines (it is fifteen). One further self-correction: the parent first reported the
`backend/.env.example` edit as committed when it was still only in the working tree; it is `073a5f8`.

- **WU7 — `1af649d`**, two files, and not in the original plan. The independent verification found
  three stale claims beyond the plan's scope. Two of them **this change invalidated** — true before
  WU4, false after: `docs/api.md` described `/users/me/settings` as still transporting a `trello`
  `defaultFormat`, and `todo.md` asserted the enum still carried the value. The operator approved
  fixing exactly those two and deferring the third. The new `docs/api.md` paragraph records the
  retirement in the same shape that file already uses for the removed `llm` key — including the
  read/write asymmetry — and cites the route that actually exists.

### Independent verification

A separate read-only verifier re-derived every number in this record and every product claim of
WU4–WU6, without being told to trust any of them. It ran in an isolated clone plus a detached
worktree at `fc59dc5`, with `PYTHONPATH` pointed at the clone to defeat the editable install's `.pth`
that would otherwise resolve `storico` back to the real repository. The real tree was never mutated
and was left clean at its head.

**Result: no blocking finding.** Confirmations worth recording:

- All five gates green, with the skip and the warning each reproduced on the base tree.
- The asymmetry holds and its tests are load-bearing. Re-derived red for both halves, and the sharper
  variant that reverts **only** the route (leaving the narrowed `Literal` in place) fails the read
  with the exact `ValidationError` the docstring predicts. That same run proved the write rejection is
  owned by the **schema** rather than the route: the write test still passed.
- The read rewrite is pure — the nested `export` dict is copied before mutation, so there is no ORM
  dirty-tracking and no write-back. The copy is load-bearing, not cosmetic.
- No counterexample to the asymmetry was found in either direction: `ExportSettings` has exactly one
  other reference (its own schema module), the only writer of export preferences is the settings
  `PUT`, and the only reader of `user_preferences.preferences` goes through `_for_schema`.
  `setExportFormat` is typed and reachable only from a `Select` whose items no longer include the
  retired value.
- `testcontainers>=4.15.0` is exactly the required floor, re-measured by downloading the wheels rather
  than by reading a comment.

**Three claims of this record were refuted by that run and are corrected above or here:** the frontend
red count (2 → 3, from a partial run misread as complete); the `STORICO_RAG_*` count ("three lines" →
two variables plus a header, four lines removed); and the warning's type (`ResourceWarning` →
`RuntimeWarning: coroutine 'Connection._cancel' was never awaited`). The warning is pre-existing and
environmental — it comes from the remote `STORICO_DATABASE_URL` in `.env`, and both base and candidate
are silent without that file, so comparing them from different directories yields a false
"candidate-caused" reading. The verifier corrected its own first comparison for exactly that reason.

**One claim of this record's *brief* was false and survives in history.** The brief — and therefore
`c5683b8`'s commit message — says `POST /api/v1/export` answers `400` for `trello`. No such route
exists or ever existed: `api/routes/export.py` mounts one route,
`GET /api/v1/workspaces/{workspace_id}/export/tasks`, and its `format` **query parameter** is the
guard. The record corrects it here rather than leaving it. Rewriting the message would mean rewriting
five commit hashes that this record and the verification cite as evidence, so it was reported to the
operator instead of done unilaterally.

**Follow-ups this candidate deliberately does not carry**, all approved as separate work: the landing
copy in `frontend/src/i18n/{en,es}.json` that still promises Trello export — the same false-promise
class as C3, closed for `AGENTS.md` in PR 1 but not for the UI — and the six live `Settings` fields
(`embedding_provider`, `google_api_key`, `google_embedding_model`, `ollama_host`, `openai_api_key`,
`openai_embedding_model`) that `backend/.env.example` omits. The latter is a documentation gap rather
than a dead knob, and it is pre-existing: this candidate removed three lines from that file and added
none.

### PR 2 review and landing

Native review `review-bde8183340bdb47b`, target
`sha256:df55b76ed235871560e08285fffe3d3329368176a5ecae2bb251079e35a71523`:
`state: approved`, `risk_tier: medium`, `selected_lenses: ["review-reliability"]`,
`changed_files: 18`, `original_changed_lines: 472`, `correction_budget: 200`,
`risk_reasons: [{"code": "configuration_change", "path": "backend/.env.example"}]`. One reviewer was
materialised (forecast `model_runs: 1`, `transport: pi_host_relay`) and the review closed on the last
admitted event. Acknowledgement burned the authority: `authority: burned`,
`burn_evidence: gentle-ai.review-acknowledged/v1`, `delivery: ordinary-repository-policy`.

Worth recording about this lineage specifically: the first START minted a consent envelope whose
binding **expired after 10 minutes unanswered**, and the provider's prescribed continuation was
`restart-for-fresh-consent` — never a resend. Every rejection on that path was pre-authority
(`lineage_created: false`, `mutation_performed: false`), so nothing was created and nothing was lost.
A second START then created the lineage; an eligible interactive host resolved the consent envelope
before it reached the model, which is host-owned permission and not something this record grants.

Two advisories were returned, both `SUGGESTION` / `informational`, neither opening a correction:
`R3-suggest-fabricated-export` (`frontend/src/stores/settingsStore.ts:57-66`) and
`R3-suggest-snake-write-coverage` (`backend/tests/test_api/test_user_settings.py:178-192`). The
closure envelope carries only their id, lens, location and severity, so this record does **not**
paraphrase their content — it names them so the follow-up can open them. As with PR 1, they are not
bundled in: editing the reviewed tree after approval would mean delivering something other than what
was reviewed.

**Landed.** `git merge --ff-only` `fc59dc5` → `61a132b` on `main`, pushed (`fc59dc5..61a132b`), branch
deleted with `-d` — which fails unless the branch is merged, so the deletion is itself the proof.
`HEAD == refs/remotes/origin/main == 61a132b`, ahead/behind `0/0`, one branch left, working tree
clean.

The push triggered **both** workflows, because the candidate touches `backend/**` and
`deploy-backend.yml` watches that path: CI run `35563349443` **green**, and — the one that mattered —
the backend deploy run `35563349521` **green**, which resets the VM worktree, rebuilds the image and
restarts the container. Production was then probed read-only: `GET /api/v1/health` answers `200` with
`database.status: ok`, and `GET /api/v1/health/services` answers `200` `degraded` with Ollama and
Qdrant unreachable — the documented pre-existing state (Qdrant contracted but never configured, no
Ollama in the container), not something this deploy caused. This candidate carries no Alembic
revision, so the deploy's missing-migration step — the open root cause of the 2026-09-20 incident —
was not on this path.

**This section was written after the approval, in commits that the approved candidate did not
contain** (the review record, a counting fix, the Dockerfile note, and the landing record itself).
That is deliberate and is the same shape as PR 1's handoff commit: the record is non-executable
documentation, and freezing the record at the moment of approval would leave the batch with no record
of its own review or landing. Anyone treating the branch tip as "the reviewed artifact" should read the
target identity above instead — it names what was actually reviewed.

## Resuming in a fresh session

State of the world at handoff, in the order it matters.

### 1. PR 2 is committed; what is left is its verification, review and landing

Four commits on `fix/retire-trello-option-and-dead-settings` off `main` @ `fc59dc5`: `c5683b8` (WU4),
`79d57dc` (WU5 settings), `f5f82e0` (WU6), `073a5f8` (WU5 `.env.example`) — 15 files, tree clean,
nothing pushed. The writing agents reported the gates green and the parent re-derived the TDD red
evidence (see "PR 2 work units" above), but the gate numbers in this record have **not** yet been
re-run by a separate verifier, and the candidate has **not** been through native review. Those are the
remaining steps, in that order.

Two premises this record got wrong are worth carrying forward, because both would otherwise be
derived wrongly again: the `trello` retirement needed a **frontend** normalisation as well as the
backend one — the persisted `storico-settings-v2` blob is a third source of a retired value — and
WU6's floor change was unavoidable rather than optional, since the canonical module path simply does
not exist below 4.15.0.

### 2. Three advisories from PR 1's review are open and non-blocking

They were deliberately not bundled into PR 1. The review's own closure says to treat them as separate
later work and never as a reason to re-run review on that candidate.

| Id | Location | What it is |
|----|----------|------------|
| `R3-waf-3` | `prod.todo.md`, rate-limiting row | **The one that matters.** The row still recommends "Vercel WAF" while `docs/deployment.md` now records that the backend is not served by Vercel. That is an internal contradiction this batch introduced. It belongs with the rate-limiting work, not with the Trello cleanup. |
| `R3-pubip-1` | `docs/deployment.md` | The production VM's public IP is now written into a tracked document, where the deploy workflow deliberately takes it from a `DEPLOY_HOST` secret. |
| `R3-evid-2` | `prod.todo.md`, integration-test row | The row's evidence wording. Cosmetic. |

The reviewer's line numbers appear to run one below the file's own; the locations above are the lines
whose content matches the id.

### 3. Two mechanical lessons that cost time and will cost it again otherwise

- A delegated writer that returns **its own** unresolved consent envelope cannot have that envelope
  answered by the parent: `answer-consent` reports `consent-binding-stale` /
  `consent-binding-unknown` ("not held by this Pi session"). The parent runs START again to mint its own
  envelope — and that binding expires after **10 minutes** unanswered. Every rejection is pre-authority
  (`lineage_created: false`, `mutation_performed: false`), so nothing is lost by retrying; never resend
  a binding the provider has already refused.
- A `gentle-ai-worker` task must carry a `## Allowed edit surfaces` section containing **only**
  repository-relative paths, one per line, with no prose in it; explanatory text belongs under the next
  heading. The first attempt at this delegation was rejected for exactly that reason.

### 4. Do not "fix" MD060

`pi-lens` flags the `|------|` separator rows in every document in `odd/tasks/` and `docs/`. There is
no markdownlint config and no markdown gate in CI. Reformatting tables to silence it would diverge from
twenty sibling documents and bury the real change in noise.

The larger items this batch deliberately did not take on — the deploy's migration policy, enabling
Qdrant/RAG in production, rate limiting, Sentry, correlation IDs, a custom domain, a frontend build in
CI, and the Trello connector itself — are recorded as non-goals above, with their sizes.
