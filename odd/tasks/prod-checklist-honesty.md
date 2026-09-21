# ODD Feature: prod-checklist-honesty

> **Status**: **PR 1 landed and pushed; PR 2 not started.** This record is the resume point — read it
> first, then the new section "Resuming in a fresh session" at the end.
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
| D6 | testcontainers deprecation | **Include it.** CI warns on every run: `testcontainers.postgres is deprecated, use testcontainers.community.postgres instead`. It is debt rather than a lie, it is one import, and it is already in the log the previous item was measured from. |
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
| WU5 | `backend/src/storico/config/settings.py`, `backend/.env.example` | D5: both settings and the three `STORICO_RAG_*` lines removed. |
| WU6 | `backend/tests/test_integration/test_projects_integration.py` | D6: `testcontainers.postgres` → `testcontainers.community.postgres`. |

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

- [ ] WU4 — retire the `trello` option with legacy normalisation and its test. Files:
      `backend/src/storico/api/schemas/settings.py` (`ExportSettings.default_format`),
      `frontend/src/types/settings.ts` (`ExportFormat`),
      `frontend/src/components/react/AccountPage.tsx` (the `SelectItem` and the label record),
      `frontend/src/stores/__tests__/settingsStore.unit.test.ts` (its fixture **is** the legacy case),
      `frontend/src/components/react/__tests__/AccountPage.test.tsx` (fixture at line 86).
      Per D3: narrow the `Literal` to `["json", "markdown"]` and normalise a stored legacy `trello` to
      `json` on read, with a test that fails without the normalisation. `ExportPanel.tsx` already
      offers only `json | markdown` and needs no change. The `export_format_trello` i18n keys become
      unused — drop them from both files together if dropped at all, keeping `en.json`/`es.json` key
      parity (the guard test reads only those two files).
- [ ] WU5 — delete the two dead settings and their `.env.example` lines. Files:
      `backend/src/storico/config/settings.py` (`rag_similarity_threshold`, `rag_max_examples`),
      `backend/.env.example` (the three `STORICO_RAG_*` lines).
- [ ] WU6 — move the testcontainers import off the deprecated module. File:
      `backend/tests/test_integration/test_projects_integration.py` (`testcontainers.postgres` →
      `testcontainers.community.postgres`); check the class name and constructor against the version
      actually installed instead of assuming the API is identical.
- [ ] Gates for PR 2: backend `ruff check src tests`, `ruff format --check src tests`, `pytest -q`;
      frontend `pnpm exec tsc --noEmit`, `pnpm vitest run`.
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

## Resuming in a fresh session

State of the world at handoff, in the order it matters.

### 1. PR 2 is the only thing left in this batch

Nothing has been written for it — no branch exists. WU4 is the one that needs care: the same `Literal`
validates reads **and** writes, so narrowing it without the normalisation turns a previously valid
stored value into a 500 on read. Production's `user_preferences` is empty (0 rows, measured), so there
is no data to migrate — but the frontend test that loads `defaultFormat: 'trello'` (in
`settingsStore.unit.test.ts`) **is** the legacy case, and it should become the test for the
normalisation rather than being deleted.
`backend/tests/test_unit/test_drop_user_preference_llm_migration.py` also contains that value, but its
`_seed` writes through a SQLAlchemy `Session` against the metadata table and never crosses the Pydantic
schema, so it is unaffected.

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
