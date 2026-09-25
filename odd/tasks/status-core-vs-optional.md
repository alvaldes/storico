# ODD Feature: status-core-vs-optional

> **Status**: done — two work-unit commits on `fix/status-core-vs-optional`
> (`b90ded2`, `8d2c2f7`), plus this evidence commit. Nothing is pushed; the push and the pull
> request are the operator's decision. Receipt-driven development is off in this clone, so no
> native review ran; two independent verifications did, recorded below with their findings.
> **Created**: 2026-09-25
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/status-core-vs-optional`
> **Receipt-driven development**: off in this clone.

## Problem

`/status` presents five provider families as one measurement, and one optional integration as a
platform-wide failure.

1. **The "LLM Runner" row claims what it does not measure.** Its copy names
   *"Ollama / OpenAI / Anthropic / Gemini / any OpenAI-compatible endpoint"*
   (`frontend/src/i18n/en.json:719`, `es.json:719`), but the only probe behind it is
   `_check_ollama()` (`backend/src/storico/api/routes/health.py:100`), an HTTP `GET` on the
   platform's `STORICO_OLLAMA_HOST` default. Every other provider is **per-workspace state**
   (`workspace_llm_configs.provider/model/base_url/api_key`, the key encrypted), verified when
   that workspace saves or tests its configuration. No global probe can speak for them, and the
   row does not say so.
2. **The banner inherits the ambiguity.** `health_services()` computes
   `status = "ok" if all_ok else "degraded"` over all five probes
   (`health.py:262`), optional ones included, and the page reads that field
   (`frontend/src/pages/[locale]/status.astro:35`). One unreachable Ollama therefore paints
   *"Some systems degraded"* while every extraction through Gemini works.
3. **The route contradicts its own docstring.** `health.py:9-11` states that Ollama and Qdrant
   are optional and *"are NOT checked at the global health level"* — while
   `health_services` folds them into the global status it publishes.
4. **Production carries this as a permanent false alarm.** The VMs have no Ollama on purpose and
   run Google embeddings; prod answers `status: degraded` with `ollama: error` and everything
   else `ok`. Recorded as finding **F2** in `odd/tasks/board-debt-closure.md:155`:
   *"Anyone alerting on `status != ok` holds a permanent false alarm, and the probe asks about a
   provider production does not use."*

Two documentation drifts belong to the same defect, because they describe the surface being
changed: `docs/api.md:30` lists `/health/services` as *"base de datos, Ollama y Qdrant"* (it
publishes five probes), and `docs/testing.md:247` describes `/status` with five rows (it renders
six; `embeddings` is missing).

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Scope | **Operator-selected (2026-09-25): option A.** Backend contract plus frontend, not a frontend-only patch and not per-provider workspace diagnostics (C). The API stops lying for every consumer, not only for this page. |
| D2 | Banner when the core is healthy and an optional integration is not | **Operator-selected: "OK con avisos".** The banner stays green (*"All systems operational"*) and an amber note below names how many optional integrations are unavailable. A green banner with a visible caveat, never a bare "degraded". |
| D3 | What counts as core | `database` and `schema`. This is the route's own existing statement — the database is the required dependency, and a schema behind the code is *"a dependency of being useful"* (the 2026-09-20 incident cost 56 extractions on a missing column). `ollama`, `qdrant` and `embeddings` are optional integrations: extraction degrades without them, it does not stop. |
| D4 | Where the classification lives | **Backend, published per probe** as `scope: "required" \| "optional"`, with the top-level `status` computed from `required` only. The payload becomes self-describing instead of leaving each consumer to guess. |
| D5 | The row that started this | Renamed from the generic *"LLM Runner"* to the Ollama default host, and its copy says which workspaces it affects and where the other providers are configured. No new probe is invented for cloud providers: an unauthenticated route cannot probe per-workspace credentials, and pretending otherwise is the defect being fixed. |
| D6 | The `embeddings` row | Shows the provider and model the probe actually used (`provider`, `model` are already in the payload and were rendered nowhere). This is the row where a generic label was hiding a real measurement. |
| D7 | Deploy skew | The frontend deploys on Vercel and the backend on the VM, independently, so the page must read a payload **without** `scope`. It falls back to a local mirror of the core set (`CORE_PROBES`), pinned to the backend constant by the mirror test. The banner is then correct on both shapes and neither side can silently drift. |
| D8 | Documentation drifts | **Operator-selected: same work unit.** `docs/api.md` rides with the contract change; `docs/testing.md` rides with the page change. |

## Non-goals

- No per-workspace or per-provider LLM health endpoint (option C). It needs authentication and is a
  feature, not this correction.
- No change to the probes themselves: what `_check_*` measures and how it spells its failures stays
  exactly as it is.
- No new row, and no probe without a row — `status-probes-mirror.test.ts` keeps that invariant.
- No `/health` or `/health/ready` change: liveness and readiness answer their own questions and
  their contract is untouched.
- No restyling of the page beyond the second group heading and the amber note.

## Established facts (verified)

- `backend/src/storico/api/routes/health.py` publishes exactly five probes in
  `health_services`: `database`, `schema`, `ollama`, `qdrant`, `embeddings` (`:273-277`).
- `_check_ollama` (`:100`) is the only LLM probe; it reads `settings.ollama_host` and never
  touches `workspace_llm_configs`.
- The workspace LLM credential is per workspace:
  `WorkspaceLLMConfigModel` (`infrastructure/database/models/workspace_llm_config.py`) carries
  `provider`, `model`, `base_url`, `api_key` and a unique `workspace_id`.
- `Settings` has no LLM provider field at all (`config/settings.py`): `ollama_host` is documented
  as a fallback default, and `embedding_provider` is the only provider selection that is global.
- The frontend consumes the diagnostics document, not liveness:
  `HEALTH_SERVICES_PATH = '/api/v1/health/services'` (`frontend/src/lib/health.ts:43`), which is
  the regression that `health.ts`'s header documents.
- `status-probes-mirror.test.ts` already reads `backend/src/storico/api/routes/health.py` from
  disk to extract the probe list, so a mirror of the classification is the same technique, not a
  new one.
- Test runners: `cd backend && conda run -n storico python -m pytest -q` (or an active env with
  the `dev` extra) and `cd frontend && pnpm vitest run`; `pnpm test` runs the whole suite.

## Tasks

### T-001 — The backend publishes which probes are required

- **Status**: done (`b90ded2`)
- **Files to modify**: `backend/src/storico/api/routes/health.py`,
  `backend/tests/test_api/test_health_services.py`, `docs/api.md`
- **What**: declare `REQUIRED_PROBES = ("database", "schema")` and
  `OPTIONAL_PROBES = ("ollama", "qdrant", "embeddings")`; publish `scope` inside each probe of
  `health/services`; compute the top-level `status` from the required probes only. Update the route
  docstring so the sentence about the "global health level" matches what the payload does. Document
  the new shape and the classification in `docs/api.md`.
- **Acceptance**: with every optional probe failing and both required probes `ok`, the route answers
  `status: ok`; with a required probe failing it answers `status: degraded`; every probe carries a
  `scope`; `REQUIRED_PROBES | OPTIONAL_PROBES` equals the `services` keys exactly; the whole backend
  suite passes and `ruff check`/`ruff format --check` are clean.

### T-002 — The page stops reading one provider as the whole platform

- **Status**: done (`8d2c2f7`)
- **Files to modify**: `frontend/src/lib/health.ts`,
  `frontend/src/lib/__tests__/health.test.ts`,
  `frontend/src/lib/__tests__/status-probes-mirror.test.ts`,
  `frontend/src/pages/[locale]/status.astro`, `frontend/src/i18n/en.json`,
  `frontend/src/i18n/es.json`, `docs/testing.md`
- **What**: read `scope` off each probe, fall back to `CORE_PROBES` (mirrored from the backend and
  pinned by the mirror test), and derive the banner from the core probes only through a tested
  `summarizeHealth`. Group the rows under *Core* / *Optional integrations*; rename the Ollama row and
  correct its copy; render the embeddings provider and model; add the amber "N optional integrations
  unavailable" note under a green banner. Update `docs/testing.md`'s `/status` row to the six rows
  the page renders.
- **Acceptance**: `pnpm vitest run` passes, including the mirror test and the new summary cases; the
  Spanish copy is neutral (no voseo) and both catalogs keep identical keys; a payload without `scope`
  (the old backend) still yields a green banner when `database` and `schema` are `ok`.

## Evidence

### T-001 — `b90ded2`

Backend gates, observed by the independent verifier on the tree that became `b90ded2`:

| Gate | Observed |
| --- | --- |
| `pytest -q tests/test_api/test_health_services.py` | 33 passed |
| `pytest -q tests/test_health.py tests/test_api/test_health_services.py` | 38 passed, 1 warning |
| `pytest -q` (whole backend suite) | 863 passed, 21 skipped |
| `ruff check src tests` | All checks passed |
| `ruff format --check src tests` | 238 files already formatted |
| `pnpm vitest run src/lib/__tests__/status-probes-mirror.test.ts` | 3 passed, frontend untouched |

The verifier's discrimination check, which is the part that matters: three new tests would have
failed before the change — the optional-probe case, the scope case and the coverage case — while
the "required probe fails ⇒ degraded" pair would have passed either way and is a guard, not a
discriminator. It also read the source (`git show HEAD:...health.py`) rather than trusting the
report, confirmed the scopes are pinned to the constants by a non-tautological membership loop,
confirmed `/health` and `/health/ready` publish no `scope`, and reproduced the frontend mirror
test's extraction against the new `services` literal. It flagged two things and both are honest:
`OPTIONAL_PROBES` is read by no route code (the tests are its only consumer), and the stale
comment in `status-probes-mirror.test.ts` — carried into T-002, where it was corrected.

### T-002 — `8d2c2f7`

Frontend gates: `pnpm vitest run` → **41 files / 484 tests passed**; `pnpm exec tsc --noEmit` → 0;
`pnpm build` → Complete. The first verification round also mutated a copy of the new tests against
the pre-change `health.ts` and measured **12 failed / 17 passed**, which is the discrimination the
suite alone cannot state.

**The render matrix, observed in a real dev server rather than inferred.** No gate in this
repository executes an `.astro` frontmatter: `output: 'server'` means `pnpm build` never runs it and
vitest never renders it — the same blind spot that shipped a broken `/status` for four days with a
green build (`docs/testing.md`, the traps table). Both verification rounds therefore stood a stub on
a free port, ran the dev server against it, and fetched both locales. Observed:

| Case | `grep -c '</html>'` | Banner | Amber note |
| --- | --- | --- | --- |
| Production shape: core `ok`, `ollama` `error` | 1 / 1 | Green, *"All systems operational"* / *"Todos los sistemas operativos"* | Present, naming *"Ollama default host"* / *"Host de Ollama por defecto"* |
| Same payload with every `scope` removed (deploy skew) | 1 / 1 | Green | Present, same wording — D7 met |
| `database` `error` | 1 / 1 | Degraded, *"Some systems degraded"* | Absent |
| Backend unreachable (the `health === null` path) | 1 / 1 | *"Services unavailable"* | Absent |

The six rows and the two group headings were read off the rendered HTML in both locales, as was
the embeddings detail line (`google / gemini-embedding-001`), and no literal `{list}` reached the
DOM. A fourth row in that table exists because the closing round removed a redundant `health &&`
from the note's condition: the writer's own re-render covered only the `down` banner, so the two
`ok`-banner cases were re-observed rather than argued.

### What the verifications caught that the writers' gates could not

1. **A page-breaking defect with green gates.** `status.astro` computed `coreRows` and
   `optionalRows` *above* the `const serviceRows = [...]` they filter — a temporal dead zone
   `ReferenceError` on every request. `pnpm vitest run` does not render `.astro`, and `pnpm build`
   does not execute frontmatter under `output: 'server'`, so both passed on a page that could not
   render. Found by reading the diff, sent back to the writer, and the fix is the reason the render
   matrix above exists as a required observation for the rest of this feature.
2. **A third, unpinned probe list.** `DIAGNOSTIC_PROBES` in the page was tied to nothing. If the
   backend grew a required probe, every existing invariant still passed while `summarizeHealth`
   never evaluated it — a green banner over a failing core, the mirror image of the defect this
   feature removes. `status-probes-mirror.test.ts` now pins it against the backend probe list, and
   the closing verification reproduced both failure modes on an isolated copy: dropping a name
   fails `expected [ Array(4) ] to deeply equal [ Array(5) ]`, and renaming the constant fails on
   the extraction assertion first.

### Known limits, recorded rather than smoothed over

- **The mirror is a mirror.** `CORE_PROBES` and `DIAGNOSTIC_PROBES` live in the frontend because it
  cannot import Python; three source-reading guards in `status-probes-mirror.test.ts` are what keep
  them honest. That is the repo's existing technique for the same problem, not a new one.
- **The probe names are written in more places than is comfortable.** `health.py` names them in the
  `results` dict, the `services` literal and the two tuples. The `services` literal must stay free
  of nested braces or the frontend mirror test's `[^}]*` extraction truncates, which is why the
  route was not restructured to derive one from the other; the coverage test is what closes the
  gap today.
- **`/health` and `/health/ready` are untouched**, including their payloads. Only the docstring of
  `/health` was corrected, because it stated the opposite of what the code did.
- Not observed: a real browser session with a healthy production backend. The render matrix used a
  stub serving the exact production payload, which is the same document the page consumes; the
  live backend was unreachable in this environment and probed nothing.
