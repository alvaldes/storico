# ODD Feature: provider-literal-and-copy-drift

> **Status**: implemented on `fix/provider-literal-and-copy-drift` (off `main` @ `a38b943`), not
> pushed. The code half and the copy half are done and green; the independent verification is
> recorded below. Receipt-driven development is **off** in this clone, so no native review ran.
> **Created**: 2026-09-19
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/provider-literal-and-copy-drift`.
>
> **Execution**: the exploration and every decision below were the parent's; the implementation was
> delegated to a writer, whose report is the source of the "what the writer found" section. The
> parent closed the one deviation the writer flagged and added the code-half guard the writer
> identified as missing.

## Problem — two halves, and the code half was the serious one

### The code half: a third hand-kept provider list, unguarded

The canonical list is `KNOWN_PROVIDERS: tuple[str, ...] = ("ollama", "openai", "anthropic",
"gemini")` in `backend/src/storico/api/schemas/custom_provider.py:32`, mirrored at
`frontend/src/lib/llm-providers.ts:10` and frozen deliberately in migration `0021` — both guarded
by tests. But `backend/src/storico/api/schemas/settings.py` held a **third, unguarded** copy:

```python
provider: Literal["ollama", "openai", "anthropic", "gemini"]
```

Because `POST /api/v1/llm/test` takes that model, a workspace-registered custom provider name got
a pydantic `422` before the route body ran — while `_build_llm_port`
(`infrastructure/tasks/extraction_task.py`), `_probe_models`
(`api/routes/workspace_settings.py`) and the readiness rule all route that same name to the
OpenAI-compatible adapter. It also made the route's tail — the `"adapter not yet implemented"`
branch — **unreachable**.

So the surface that tests a connection was the only surface that disagreed with the rest about
which providers exist, and the branch written to handle the disagreement could never run.

### The copy half: eight strings that omit Gemini

Confirmed by walking the parsed JSON in both locales:

| Path | Line | Was |
|------|------|-----|
| `landing.faq.a6` | 88 | `"... Cloud models (OpenAI, Anthropic) are also supported."` |
| `pages.privacy.collection_llm` | 588 | `"... a cloud provider (OpenAI, Anthropic) ..."` |
| `pages.privacy.transfers_body` | 617 | `"... a cloud LLM provider (OpenAI, Anthropic) ..."` |
| `pages.status.llm_runner_desc` | 721 | `"Ollama / OpenAI / Anthropic"` |

Plus `pages.docs.llm_backend_openai` (`:686`), stale for a different reason: it advertised
`"GPT-3.5, GPT-4"`, two models nothing in the code names.

**Three of these five paths were wrong in the first version of this document.** The reconnaissance
reported `pages.docs.llm_runner_desc` (it is `pages.status`), and `privacy.collection_llm` /
`privacy.transfers_body` (both are `pages.privacy`). The keys were real; the namespaces were not.
They were re-derived by walking the parsed JSON, and that correction is what the writer was given —
a plan's path is what the next reader acts on, and this one was already being handed onward before
it was checked.

### Docs: the same false statement in three more files

`docs/architecture.md:19` and `:102` omitted Gemini. `docs/deployment.md:75` and `:91` claimed the
**OpenAI adapter was pending implementation** — it exists and has for a while.
`README.md:60` omitted Gemini.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | The copy strings | Sweep all 8, and the stale model list. The privacy pair was included rather than deferred: same class of false statement, previously deferred only because it rode an unrelated slice. |
| D2 | How the copy names providers | Name the four first-class providers, and keep the "or any OpenAI-compatible endpoint" escape hatch explicit, because custom providers are a real supported path. That is exactly what `pages.status.llm_runner_desc` now says. |
| D3 | The `Literal` | `provider: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)`, importing the canonical bound from `custom_provider.py` — so the fix removes the third copy rather than re-typing it in a different form. |
| D4 | The dead fallthrough | It becomes reachable: a custom name without a `base_url` is a **refused test** (a `LLMTestResponse(success=False, ...)` naming the provider), and with one it is probed through the OpenAI-compatible adapter — the same rule `_build_llm_port` applies. No branch that cannot be taken, and the `"not yet implemented"` message is gone. |
| D5 | The placeholders's home | The keyless-endpoint credential is defined **once**, in `infrastructure/llm/openai_adapter.py`, as `CUSTOM_PROVIDER_PLACEHOLDER_KEY`, exported from `storico.infrastructure.llm`. It is owned there because the OpenAI SDK is what forces it to exist. |
| D6 | The drift guard | Two guards, one per half. The writer added the **copy** guard (`frontend/src/i18n/__tests__/provider-copy.test.ts`, deriving "cloud" from the backend's readiness rule rather than declaring it) and the onboarding select guard. The parent added the **code** guard the writer identified as missing: `provider-name-mirror.test.ts` now fails if any `Literal` in `api/schemas/settings.py` re-lists two or more built-in names, and pins that the field's bound is the shared constant. |
| D7 | Scope | No new adapter, no change to `KNOWN_PROVIDERS` membership, the migration `0021` frozen copy, or the reservation rule. |

## What the writer found that the brief did not know

All of these are worth keeping — a brief is a hypothesis, and these are the measurements.

1. **The repo-wide ruff invocation is not the CI one.** The writer reported `ruff check .` and
   `ruff format --check .` red on `api/index.py` and `spec-tasks-api-endpoints.md`, and proved them
   pre-existing. Both are real, and **both are outside what CI runs**: `.github/workflows/ci.yml:36`
   and `:40` invoke `ruff check src tests` and `ruff format --check src tests`, scoped so that
   `backend/api/` (a Vercel entrypoint) and a stray planning markdown are never linted. Re-run
   scoped: **`All checks passed!` and `214 files already formatted`**. The writer's reading was
   correct and its conclusion was conservative; the resolution is that the commands in the brief
   were broader than the gate.
2. **The `es.json` / `en.json` escape conventions are the opposite of the intuitive guess.**
   `en.json` uses `\u2014` escapes; `es.json` uses literal em dashes. One edit had to be resubmitted
   in the escaped form to keep the diff minimal.
3. **`OnboardingModal`'s provider options cannot be read as values in jsdom.** `@base-ui/react`'s
   `SelectItem` renders neither `value` nor a value-derived attribute. The guard therefore asserts
   the option **label** set plus a selection read-back, and strips `<svg>` subtrees before reading
   text — because `anthropicBlack.tsx` carries an `<title>Anthropic</title>`, so the raw
   `textContent` of that option is `"AnthropicAnthropic"`.
4. **`docs/deployment.md:79` and `:87` (and `docs/security.md:108`, `docs/README.md:26`) reference
   `prod.todo.md`, which does not exist** in the repository and is not gitignored. Four dead links,
   out of this feature's scope; recorded as a follow-up rather than fixed here.
5. **Gemini's built-in branch has no positive-construction test.** `TestBlankCredential[gemini]`
   covers its blank-credential refusal only. Pre-existing gap, not duplicated by this change.
6. **`_probe_models` already agreed with the fix**: its custom branch returns `[]` when `base_url`
   is absent. So after this change all three surfaces — extraction, model probe, connection test —
   state the same endpoint requirement; the connection test is the only one that answers with a
   message rather than an empty list, because it is the only one that is a question.
7. **The placeholder has a security dimension worth naming**: `None` would let the SDK read the
   ambient `OPENAI_API_KEY`, so a workspace-scoped call could quietly use a server credential. The
   constant's docstring now says so, which is better than the brief asked for.

## The one deviation, and how it was closed

The writer could not satisfy "exactly one definition" fully, and said so rather than quietly
leaving it: `backend/tests/test_unit/test_llm_port_selection.py:206` asserted through
`extraction_task._CUSTOM_PROVIDER_PLACEHOLDER_KEY`, and that test file was outside the delegated
edit surface. The writer kept a private alias pointing at the promoted constant.

The **parent closed it**: the test now imports `CUSTOM_PROVIDER_PLACEHOLDER_KEY` from
`storico.infrastructure.llm`, the alias is deleted, and the string literal is defined in exactly one
place. The test's other copy of the literal (`"no-key-required"` at `:242`, an expected-value
fixture) is deliberately kept: it pins the value that actually reaches a gateway, which is the
contract, not the constant's name.

## Evidence

| Check | Command | Result |
|-------|---------|--------|
| Backend tests | `python -m pytest -q` | **649 passed, 1 skipped** (646 passed / 1 skipped before, +3) |
| Backend lint (CI scope) | `ruff check src tests` | `All checks passed!` |
| Backend format (CI scope) | `ruff format --check src tests` | `214 files already formatted` |
| Route tests | `pytest tests/test_api/test_llm_test_route.py -v` | 10 passed (3 new in `TestCustomProviders`) |
| Frontend suite | `pnpm vitest run` | **36 files, 418 passed** (35 / 406 before; +1 file, +12 tests) |
| Types | `pnpm exec tsc --noEmit` | exit 0 |
| Copy guard is real | revert `a6` and `llm_runner_desc` to omit Gemini | `must name every cloud provider; missing: gemini` (both keys) |
| Onboarding guard is real | remove the Gemini `<SelectItem>` | `expected [ 'Anthropic', 'Ollama (Local)', …(1) ] to deeply equal [ 'Anthropic', 'Gemini', …(2) ]` |
| Code guard is real | reintroduce `Literal["ollama", "openai", "anthropic", "gemini"]` | **2 tests fail**, including the named offender; green again on restore |
| CI-equivalent lint is green | `ruff check src tests` / `ruff format --check src tests` | both exit 0 (the repo-wide invocation is red on `backend/api/index.py`, which CI never lints) |
| Pre-existing analyzer noise | Pyright on `api/app.py` | `reportArgumentType` on `add_exception_handler` — classic FastAPI false positive, file untouched, and nothing in CI or pre-commit runs Pyright |

## Follow-ups this surfaced, recorded rather than bundled

1. **`prod.todo.md` is referenced in four places and does not exist**: `docs/deployment.md:79`,
   `:87`, `docs/security.md:108`, `docs/README.md:26`. It is not gitignored, so it is a genuine
   missing file rather than a local-only artifact. A production checklist that is linked from four
   documents and absent is worse than one that is not linked at all.
2. **`backend/api/index.py` fails `ruff check`** (I001, one fixable import order) and
   `backend/spec-tasks-api-endpoints.md` fails `ruff format` on its embedded Python blocks. Neither
   is linted by CI because both sit outside `src tests`. Either widen the CI scope or fix them; a
   gate that does not cover a real file is a gate with a hole in it.
3. **Gemini's built-in branch has no positive-construction test** in `test_llm_test_route.py`.

## Tasks — all closed

- [x] Confirm every one of the 8 strings and the 4 doc claims against the current tree (three paths corrected by parsing the JSON).
- [x] Fix the `Literal` and resolve the dead fallthrough.
- [x] One definition of the keyless-endpoint placeholder, shared by both call sites.
- [x] Sweep the 8 i18n strings in both locales, plus the stale model list.
- [x] Add the drift guards, one per half, both mutation-proven.
- [x] Correct `docs/architecture.md`, `docs/deployment.md` and `README.md`.
- [x] Run backend `ruff check src tests`, `ruff format --check src tests`, `pytest -q`; frontend `tsc --noEmit` and `vitest run`.
- [ ] Work-unit commits on the feature branch — **pending**.
- [ ] Independent verification — **pending**.
- [ ] Fast-forward into `main`, delete the branch, re-gate — **pending**.
