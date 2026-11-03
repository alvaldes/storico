# ODD Feature: llm-judge-instrument

> **Status**: implemented on `feat/llm-judge-instrument` (5 commits + the review-findings commit),
> verified by an independent read-only review, **not merged**. The LLM-as-a-Judge was unusable as an
> instrument: it judged with the generating model, scored a rubric the experimental design abandoned,
> and dropped every per-criterion value it computed. It now validates its own output, persists the
> verdict in three states, can run on a separate model, and scores the seven-criterion 1-7 rubric
> with TAS/IFI computed by the server.
> **Created**: 2026-11-03 (owner request on that date)
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `feat/llm-judge-instrument`, off `main` @ `b36258d`.

## Problem

Measured on 2026-11-03 against `main` @ `b36258d` (`v0.13.0` + 3 commits, migration head `0032`).
The chain exists — service, prompt, wiring, and two tests of the switched-on path — and it is still
unusable for the thesis, for four separate reasons:

1. **The judge is the generator.** `infrastructure/tasks/extraction_task.py:394` builds
   `LLMJudgeService(llm_port=llm_port, …)` with the same port and the same `llm_config` the
   extraction resolved (`:484-500`), and no judge model setting exists anywhere (`grep -rn "judge"`
   over `api/routes/workspace_settings.py` and the ORM models returns nothing). Switching the flag on
   produces self-evaluation, which is the self-preference bias the experimental design wants to
   *measure*, not to inherit.
2. **The rubric is not the rubric.** `infrastructure/llm/prompts/single_judge.j2` scores five
   criteria on 0-10 (coherence, completeness, feasibility, **format**, granularity). The design fixed
   on 2026-10-17 is seven items on 1-7, with *clarity* replacing *format* and dependencies plus
   global usefulness added — and TAS/IFI are derived from it (S1-S3). Today IFI cannot be computed:
   its definition is missing one of its three terms.
3. **The per-criterion values are computed and dropped.** `_parse_judge_response` builds a `criteria`
   dict (`extraction_judge_service.py:123-133`) and nothing reads it: `criteria` appears in no other
   backend file. Only `confidence_score` reaches the row, so the agreement analysis between judge and
   experts has no data to run on even with the flag on.
4. **Three failure shapes are unvalidated.** `int(total_score)` has no clamp (`75 → 1.5`,
   `-5 → -0.1`); the criteria are read with `data.get(x, {}).get("score", 0)` so a non-dict value
   raises `AttributeError`; and `validate()` returns `self._parse_judge_response(...)` **outside** its
   `try` (`:87`), so those deterministic type errors reach the generic `except Exception` of
   `run_background_extraction` and are retried with exponential backoff as if they were a network
   cut. And a failure of the judge leaves the same `confidence_score: null` a switched-off run
   leaves, so "not requested" and "requested and failed" are indistinguishable outside the row.

## Decisions

| #   | Decision | Choice |
| --- | --- | --- |
| D1  | Where output validation lives | **In `JudgeResult`**, the one object every caller already builds. Clamping in the caller would fix `extraction_task.py` and leave the second, unflagged call site (`domain/services/extraction_service.py:266`) identical — the exact mistake the 2026-09-24 note warned about. |
| D2  | How an unusable judge payload is classified | A new `JudgeOutputError(LLMError)`: it is caught by the existing `except LLMError` at the call site, so it is **not** retried as transient, and its message is what the persisted record carries. Every non-coercible value and every missing criterion raises it. |
| D3  | What the total and the verdict are | **Computed, never trusted from the model**: `total_score = sum(criteria)`, `approved = total >= ceil(0.7 × max_total)`. `0.7` reproduces today's `approval_threshold=35` on both the old (50) and the new (49) maximum, and it removes the hardcoded `35` from `prompt_manager.py` without inventing a workspace setting the design never asked for. |
| D4  | What is persisted | New nullable `extractions.judge_result` (JSON, not JSONB — the unit suite builds its schema on SQLite, same portability choice as `prompt_config`): `{state, criteria: {name: {score, justification}}, total_score, max_total, approved, model, model_source, error, error_type}`. Written once in the same terminal UPDATE as `confidence_score` (`mark_completed`). |
| D5  | How the three states are read | `judge_result IS NULL` + `prompt_config.validate == false` → **not requested**; `judge_result.state == "ok"` → **ran**; `judge_result.state == "failed"` → **requested and failed**, with `error`/`error_type`. No fourth column and no enum: the request already carries its own flag, and the pair cannot disagree because both are written by the same run. |
| D6  | The Qdrant payload | Gains `judge_state`, because the 2026-09-24 note measured that the point carries no `prompt_config` and a `null` there is ambiguous **by construction**. Additive payload key, no read path changes. |
| D7  | Judge model, this slice | `workspace_llm_configs.judge_model` (nullable). The judge runs with a copy of the extraction config that differs only in model: same provider, credential, temperature and budget. `judge_result.model` + `judge_result.model_source` (`workspace` \| `extraction`) record which model judged. |
| D9  | Judge as a second, independent LLM configuration (supersedes D7's non-goal on 2026-11-03, L6) | `workspace_llm_configs` gains `judge_provider`, `judge_api_key` (encrypted by the repository, the only place that touches credentials) and `judge_base_url`, alongside `judge_model`. Each field falls back **independently** to the extraction value; the judge is "separately configured" when any of the four is set. When `judge_provider` differs from the extraction provider the extraction credential and endpoint are **never** reused — a key for one provider must not be sent to another — so `judge_api_key` / `judge_base_url` decide, with the provider default endpoint (Ollama host included) as the only implicit value. Readiness is the existing rule (`missing_llm_config_fields`) applied to the judge's own provider, model, credential and endpoint; an incomplete judge block is a **classified judge failure, not a refused extraction** (the extraction has no dependency on the judge). The verdict gains `provider` and `model_source` reads `"workspace"` for any separately configured judge and `"extraction"` only when nothing is configured. Cross-provider needs no probe path: the settings form does not test the judge, the first judged run does. |
| D8  | Default posture | `run_validation` stays `false` by default on the API and becomes an explicit per-run switch in the UI. The judge costs one extra LLM call per extraction; nothing turns it on implicitly. |

## Non-goals

- **A configurable approval threshold.** The design never asks for one; D3 derives it from the rubric
  maximum, which is the thing that actually varies.
- ~~Cross-provider judging~~ — **promoted to a requirement on 2026-11-03** (S10/D9), so it is no longer a
  non-goal. A judge-only readiness surface in the settings page and a probe button stay out of scope:
  the verdict records `provider`/`model`, and a bad judge configuration fails as a judged failure.
- **Judging manual runs** — manual runs do not exist yet
  (`tasks.extraction_id` is `NOT NULL` since `0028` and `POST /tasks/` answers `410`); when the
  manual-mode slice lands, the judge must accept `provider = "manual"` as input, and that slice owns
  it.
- **The blind-evaluation mode** for experts (E2 is judged in an external form) and the study session
  with its clock.

## Verification

Independent read-only review over the whole branch (`gentle-ai-verify`, 2026-11-03), claim by claim.
Ten claims held on behavior — three states, a failed judge never failing the run, the arithmetic, the
clamp matrix, the model swap, prompt blindness, legacy rows, the two additive migrations, the settings
semantics, and no silent contract break — and one **blocker** plus five advisories came out of it. All
six are closed in T6, each with the test that would have caught it:

| # | Finding | Closed by |
| --- | --- | --- |
| F1 | `tsc --noEmit` red: `tas`/`ifi` typed as numbers while failed records carry `null` and legacy rows omit them | Types say `number \| null`; the fixtures are `satisfies` assertions, so `tsc` is the pin (exit 0 measured) |
| F2 | A judge-model lookup that raised escaped the judge's error handling and failed the whole extraction | Lookup moved inside the `try`; a raising lookup leaves a completed run with a classified failure (new test observed RED then GREEN) |
| F3 | A legacy record rendered its retired `format` criterion last | Rendered in the fourth position; the label order is pinned |
| F4 | Six comments still described `judge_model` as full-replace | Reworded; behavior untouched |
| F5 | The route docstring's doubled backticks leaked into the published API page | Single backticks, pages regenerated, `test_api_reference` green |
| F6 | A run asked to judge whose own extraction failed leaves `judge_result` null — a fourth reading nobody had written down | Named in the spec and in `docs/api.md`, with the rule that analysis filters on `status`, never on `validate` alone |

Measured at the tip: backend **1559 passed, 45 skipped**, `ruff check`/`format` clean, `tsc --noEmit`
exit 0, frontend **980 passed**, `eslint` clean. The 45 skips are the Docker-gated migration-chain and
testcontainers suites plus the live Ollama/Qdrant opt-ins — the same set as before this feature, which
means **`0033` and `0034` have never been executed against a real Postgres in this environment**; CI's
chain test is their first execution. That is the one piece of proof this environment cannot produce.

## Delivery

Chained PRs, three slices, base `main` @ `b36258d`, branch `feat/llm-judge-instrument`:

| PR | Tasks | Size | Slice boundary |
| --- | --- | --- | --- |
| 1 | T1 — contract + persistence | **1,090 authored lines** (≈430 code, ≈600 tests, migration `0033`): over the ~400 budget | `d0cbc85`, measured after the commit |
| 2 | T2 + T3 — judge model + rubric | ~600 authored lines | `158f3c3` + `c39361e` |
| 3 | T4 — UI, plus the settings field the mirror guard forced | ~700 authored lines (frontend + its tests) | this slice |
| 4 | T5 — docs and specs | docs only | `5409040` |
| 5 | T6 — review findings | ~180 authored lines | `25b1dde` |
| 6 | T7 + T8 — the judge as a second LLM configuration (S10) | ~1,000 authored lines (backend + migrations + settings form) | `8d9e5af` + this slice |

PR 1 is deliberately not split further, and the reason is structural rather than stylistic: the RAG payload
keyword and the judge block live in the same file (`extraction_task.py`), so a split by file leaves an
intermediate commit that raises `TypeError` at runtime, and a split by hunk keeps both halves green only by
duplicating the test scaffolding that the split is supposed to make reviewable. Reviewer focus for PR 1 is
narrow: the judge block in `extraction_task.py`, the coercion in `JudgeResult`, and `0033`.

## Specs

S1 — The rubric, verbatim from the 2026-10-17 design, one rubric for experts and judge, 1-7 anchored
at 1, 4 and 7:

| Dimensión | Pregunta | 1 | 4 | 7 | Juez |
| --- | --- | --- | --- | --- | --- |
| Coherencia | ¿Todas las tareas pertenecen a la historia? | La mayoría está fuera de alcance | Alguna sobra | Todas pertenecen | coherence |
| Completitud | ¿Alcanzan para terminar la historia? | Falta lo esencial | Falta algo importante, no crítico | No falta nada | completeness |
| Factibilidad técnica | ¿Son correctas y realizables? | Hay pasos imposibles o ilógicos | Alguna hay que corregirla | Todas son correctas | feasibility |
| Claridad | ¿Se entiende qué hacer sin preguntar? | No se entiende | En algunas hay que preguntar | Se entiende todo | format |
| Granularidad | ¿El tamaño es adecuado? | Demasiado grandes o atómicas | Algunas mal dimensionadas | Todas adecuadas | granularity |
| Dependencias | ¿El orden y las dependencias son correctos? | Faltan o están mal | Incompletas | Correctas | — |
| Utilidad global | ¿Lo usarías en un sprint tal cual? | No | Con cambios importantes | Tal cual | — |

S2 — Indices, verbatim: "**TAS** = promedio de coherencia y factibilidad técnica: si son las tareas
correctas y si están bien planteadas." / "**IFI** = promedio de claridad, granularidad y
dependencias, que es como lo define la tesis." / "**Completitud** queda sola: es la contraparte
humana del TCR automático."

S3 — "**El juez usa esta misma rúbrica y la escala 1-7.** El acuerdo juez vs expertos se calcula
sobre las 5 dimensiones compartidas sin reescalar."

S4 — "**El juez no debe ser uno de los modelos que se comparan en E1.** Si lo es, puntúa sus propias
tareas y la autopreferencia contamina la comparación de modelos."

S5 — "**Lo persistido tiene que distinguir TRES estados, no dos.**"

S6 — "**Un input no coercible es un fallo clasificado**, no uno tragado." plus the clamp: the score
is always a defined value inside the rubric's own range.

S7 — "**El juez es ciego por construcción**: el prompt sólo recibe la historia y las tareas
(`single_judge.j2`), no el proveedor. Hay que mantenerlo así cuando se lo pase a la rúbrica."

S8 — The switch is per run and visible: the owner's choice on 2026-11-03 was
"Juez completo: cortes 1→3 y después UI", and the UI shows the seven items plus TAS/IFI.

S10 — The judge may run on the extraction's provider and credential with another model, **or** on
another provider with another credential and another model; both MUST be coverable. The owner's words,
verbatim: "el juez pude tener el mismo proveedor y credencial que el dela extraccion aunque sea otro
modelo pero tambien pude ser otro proveedor con otra credencial y otro modelo y eso tambien se debe
poder cubir"

S9 — Repository convention (not a user requirement): every new command, option or message updates the
docs that describe it, and every behavior change ships with its test.

## Tasks

| ID | Task | Spec | Route | Commit |
| --- | --- | --- | --- | --- |
| T1 | Judge output contract: `JudgeOutputError`, rubric-aware `JudgeResult`, `judge_result` column + migration `0033`, terminal write, API exposure, Qdrant `judge_state` | S5-S7 | inline | `d0cbc85` |
| T2 | Judge model separation: `judge_model` setting, migration `0034`, resolution + `model`/`model_source` in the record | S4 | inline | `158f3c3` |
| T3 | Rubric 1-7: prompt rewrite, parser, TAS/IFI persisted, confidence derived from the rubric maximum | S1-S3 | inline | `c39361e` |
| T4 | UI: per-run switch + judge panel with the seven items and TAS/IFI, both locales — extended with the settings field (L4) | S8 | inline | this slice |
| T5 | Docs and specs: `openspec/specs/llm-as-a-judge/`, `docs/api.md`, `AGENTS.md` row 6 | S9 | inline | `5409040` |
| T7 | Judge as a second LLM configuration: `judge_provider` / `judge_api_key` / `judge_base_url` + migration `0035`, independent fallback, no credential crossover, readiness as a judged failure, `provider` in the verdict | S10, S4 | inline | `8d9e5af` |
| T8 | UI: the judge block in the settings form (provider, model, credential, endpoint) with the "empty = same as extraction" rule | S10 | inline | this slice |
| T6 | Review findings: the `tsc` blocker, the judge-model lookup outside the judge's error handling, legacy `format` order, stale "full replace" prose, docstring markup in the published page, the undocumented fourth reading | S5-S7, S9 | inline | this commit |

## Log

L1 — the owner's request, verbatim (2026-11-03): "Sigamos con la validación de este proyecto, teniendo
en cuenta la validación de la tesis también y un tema importante es lo del tema de los jueces dentro
de la aplicación que actualmente no está implementada y creo que sería muy necesario implementarla.
Pero primero un análisis completo, actualizando también la documentación en Sequence Braining para
mantener este baúl actualizado"

L2 — the owner's answer to the scope question, verbatim: "Juez completo: cortes 1→3 y después UI".

L3 — measured correction of the parent's own instruction: the delegation for T2 said the PUT was a full
replace and that an omitted `judge_model` clears it. That is false for this payload — `LLMConfigRequest`
is a partial update (`extra="forbid"`, every field optional) and the existing contract test pins
"an omitted field leaves the stored value alone". The route and the schema comment were corrected to
the payload's real convention: omitted keeps, an explicit empty string clears. The comment that
carried the wrong wording is corrected in the same slice as this entry.

L6 — the owner asked for the judge to be able to run on another provider with another credential, not
just another model: "el juez pude tener el mismo proveedor y credencial que el dela extraccion aunque
sea otro modelo pero tambien pude ser otro proveedor con otra credencial y otro modelo y eso tambien se
debe poder cubir" (2026-11-03). Recorded as S10 and D9, which retires D7's cross-provider non-goal and
adds T7 (backend) and T8 (settings form).

L5 — the independent verification found one blocker and five advisories; all six are closed in T6 with
the evidence in `## Verification`. The blocker was the frontend type gate: the client typed `tas`/`ifi`
as numbers, the failed record carries `null`, and the fixtures that pin the wire shape were the ones
`tsc` refused — the failed and legacy shapes were the untested axis, exactly where the record type had
been written from the ok shape alone.

L4 — scope extension recorded by the parent during T4: the `judge_model` field was added to the
settings form (`LLMConfigEditor.tsx`) and to the client mirror. Two reasons, both measured: the
`llm-config-readiness-mirror` guard fails on purpose for any new bounded backend field, so the frontend
either mirrors it or records it as unknown; and a setting that could only be written with curl left the
judge unusable for the experiments it exists for. The field keeps the payload's convention by always
sending the value explicitly, so clearing works.
