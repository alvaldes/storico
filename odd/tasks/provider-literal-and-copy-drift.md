# ODD Feature: provider-literal-and-copy-drift

> **Status**: planning — no commit, no evidence yet.
> **Created**: 2026-09-19
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/provider-literal-and-copy-drift` (to be created off `main` @ `6174f5a`).
> **Receipt-driven development**: off in this clone.

## Problem

The "4 stale provider enumerations" recorded as a follow-up are four user-facing copy strings
that omit Gemini, in both locales (8 strings total):

| Key | `en.json` / `es.json` | Current value |
|-----|----------------------|---------------|
| `pages.docs.llm_runner_desc` | `:721` | `"Ollama / OpenAI / Anthropic"` |
| `landing.faq.a6` | `:88` | `"... Cloud models (OpenAI, Anthropic) are also supported."` |
| `privacy.collection_llm` | `:588` | `"... a cloud provider (OpenAI, Anthropic) ..."` |
| `privacy.transfers_body` | `:617` | `"... a cloud LLM provider (OpenAI, Anthropic) ..."` |

Plus one model list that is stale for a different reason: `llm_backend_openai` (`:686`) still
advertises `"GPT-3.5, GPT-4"`.

**And a real code defect the audit surfaced, which is the more serious half.** The canonical
list of first-class providers is
`backend/src/storico/api/schemas/custom_provider.py:32` (`KNOWN_PROVIDERS`), mirrored at
`frontend/src/lib/llm-providers.ts:10` and both guarded by tests. But
`backend/src/storico/api/schemas/settings.py:78` holds a **third, unguarded, hand-kept copy**:

```python
provider: Literal["ollama", "openai", "anthropic", "gemini"]
```

Because `POST /api/v1/llm/test` takes that model, a custom provider name — `deepseek`, and the
same names `_build_llm_port` (`extraction_task.py:260-265`) and `_probe_models`
(`workspace_settings.py:626-629`) happily route to the OpenAI-compatible adapter — is rejected
with a pydantic `422` before the route body runs. That makes the fallthrough at
`backend/src/storico/api/routes/settings.py:267-272` unreachable dead code, and makes the
connection-test surface the only surface that disagrees with the rest.

Docs carry the same drift: `docs/architecture.md:19` and `:102` omit Gemini,
`docs/deployment.md:75`/`:91` claim the OpenAI adapter is unimplemented (it exists), and
`README.md:60` omits Gemini.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | The copy strings | Sweep all 8 to name the providers the code actually supports. The privacy-policy pair is included here rather than deferred: it is the same class of false statement, and it was only deferred because it rode on an unrelated slice. |
| D2 | How the copy names providers | Name the four first-class providers, and keep the "or any OpenAI-compatible endpoint" escape hatch explicit, because custom providers are a real supported path. |
| D3 | The `Literal` | Widen it to `str` with the same length bound the rest of the contract uses, so validation matches every other surface instead of contradicting it. |
| D4 | The dead fallthrough | Decide explicitly: either it becomes reachable (a custom provider reaches the OpenAI-compatible branch instead) or it goes. Do not leave a branch that cannot be taken. |
| D5 | Guard the drift | The three hand-kept copies are the root cause; the fix is not only the copy. Add the missing guard so a fifth first-class provider cannot leave a surface silently behind — extending the existing mirror test rather than inventing a new mechanism. |
| D6 | Frontend duplicates | `OnboardingModal.tsx:257-288` and `provider-icon.tsx:19-30` are unguarded hand-kept copies with no test file. Decide per site; at minimum record what is left unguarded. |
| D7 | Docs | Correct the stale provider claims in `docs/architecture.md`, `docs/deployment.md` and `README.md` in this slice, since they are the same statement in a different file. |

## Non-goals

- No new provider adapter.
- No change to `KNOWN_PROVIDERS` membership, to the frozen copy in migration `0021`, or to the
  reservation rule that keeps those four names out of the custom-provider namespace.
- `AGENTS.md`'s historical ADR phrasing ("luego agregar OpenAI y Anthropic") is a record of a
  decision as taken; correct only if it reads as a current claim.

## Tasks

- [ ] Confirm every one of the 8 strings and the 4 doc claims against the current tree.
- [ ] Fix the `Literal` and resolve the dead fallthrough.
- [ ] Verify against the running route that a custom provider name now behaves like every other
      surface (this is the observable proof the `Literal` fix landed).
- [ ] Sweep the 8 i18n strings in both locales.
- [ ] Add the drift guard(s); record any site left unguarded.
- [ ] Correct the docs.
- [ ] Run backend `ruff check`, `ruff format --check`, `pytest -q`; frontend `tsc --noEmit` and
      `vitest run`.
- [ ] Work-unit commits on the feature branch (code and copy are separable work units).
- [ ] Independent verification.
- [ ] Fast-forward into `main`, delete the branch, re-gate.

## Evidence

_None yet._
