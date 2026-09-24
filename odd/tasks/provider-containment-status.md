# ODD Feature: provider-containment-status

> **Status**: **Implemented on branch `fix/provider-containment-status`, tree left dirty for the
> operator's review. No commits made — staging, committing and landing belong to the operator.**
> **Created**: 2026-09-24
> **Workflow**: Organic Driven Development (ODD)

## Problem

The repository held **two incompatible written definitions of 403**, and both were deliberate —
that is what made this a decision and not a bug:

| Definition | Where | Says |
|---|---|---|
| Containment is reported | `backend/src/storico/api/routes/projects.py:95-101` and `backend/src/storico/api/routes/extraction.py:134-139` | 403 = "the row exists but belongs to another workspace". Existence and containment are different facts, because the path declares the workspace. |
| Containment is collapsed into absence | `backend/tests/test_api/test_workspace_settings_providers.py` (docstring around lines 501-508) and `backend/src/storico/api/routes/workspace_settings.py:348-350` (the `rename_custom_provider` handler and its docstring) | 404 = "that row does not exist **or is not reachable**", so a foreign provider id reads as absent **on purpose, so that it cannot be probed for existence**; 403 = "authenticated but not a member or an admin". |

The test asserted the second reading; the two sibling routes implemented the first. A client hitting
`PATCH /workspaces/{id}/settings/providers/{providerId}` with a foreign id got a different answer
than a client hitting a foreign project or story id, and the divergence was intentional on both
sides.

## Decision

**The operator chose the first reading (issue #5, 2026-09-24): containment is 403 everywhere.**
A row that exists but is not reachable from the workspace in the path reports 403, not 404. The
anti-probing rationale is therefore **retired on purpose, not accidentally** — every sentence that
stated the old rule has been updated, and the accepted cost is recorded here rather than hidden.

### The accepted cost, in plain words

A foreign provider id is now **distinguishable from an absent one**: an absent id answers 404 and a
foreign id answers 403 with a detail naming the workspace mismatch. That retires the anti-probing
rationale the rename test explicitly asserted — a caller can now probe whether a given provider id
exists *somewhere* by comparing 404 against 403. The operator judged this acceptable because it is
the same exposure `projects.py` and `extraction.py` already carry, and uniformity of the API
contract outweighs the probe channel for this resource.

## What lands

| File | Change |
|---|---|
| `backend/tests/test_api/test_workspace_settings_providers.py` | `test_rename_cannot_reach_another_workspaces_provider` renamed to `test_rename_reports_a_foreign_provider_as_forbidden`, its assertion flipped to 403 and its docstring rewritten to the new contract — keeping the assertion that the foreign row is untouched, which is the property that matters for a write path. The docstring of `test_an_absent_row_outranks_a_reserved_target_name` rewritten to the new rule (its own random-UUID → 404 assertion unchanged, still correct). |
| `backend/src/storico/api/routes/workspace_settings.py` | `rename_custom_provider` split: the genuinely absent row keeps the **byte-identical** 404 (same status, same detail `"Custom provider not found"`); the foreign case adds 403 with `"This custom provider does not belong to the specified workspace"`, mirroring the sibling routes' style. The `renamed is None` 404 further down is untouched — a true absence race guard. Handler docstring states the new rule and that the old rationale was **replaced**, not refuted. |
| `docs/api.md` | The provider paragraph now says a foreign `providerId` answers `403`. The "Contrato de existencia (404 vs 403)" paragraph states the rule once, uniformly, naming the three implementations, and the exception paragraph is deleted — replaced by a short historical note dating the retirement (2026-09-24, issue #5) and naming the accepted cost. The argument that unifying to "404 for everything" would be an API-contract decision and not a fix is kept — it is why this was decided by the operator and not by an agent. |
| `odd/tasks/provider-containment-status.md` | This record. |

## Evidence

TDD, run before and after the source change, on `backend/tests/test_api/test_workspace_settings_providers.py`:

**RED** — `cd backend && .venv/bin/pytest tests/test_api/test_workspace_settings_providers.py -q`
(tests changed, source untouched):

```
>       assert renamed.status_code == 403
E       assert 404 == 403
E        +  where 404 = <Response [404 Not Found]>.status_code

tests/test_api/test_workspace_settings_providers.py:550: AssertionError
FAILED tests/test_api/test_workspace_settings_providers.py::TestCustomProviderRegistry::test_rename_reports_a_foreign_provider_as_forbidden
1 failed, 41 passed in 2.52s
```

**GREEN** — same command after the source change:

```
42 passed in 2.48s
```

No Docker or external service was needed: this test module runs against the test fixtures
(`seed_workspace`, `db_session`) and the in-repo app client, all local.

### The three-way answer on other sites of the old rule

Grepped `backend/tests/`, `backend/src/`, `docs/`, `frontend/src/` for
`reads as absent|cannot be probed|probed for|belonging to another workspace reads`, and
`backend/tests/` for `== 404`:

- The only statements of the old rule were the two test docstrings and the handler docstring —
  all updated here.
- All other `== 404` assertions in `backend/tests/` (`test_stories.py`, `test_projects.py`,
  `test_tasks.py`, `test_extraction.py`, `test_extractions.py`, `test_export.py`,
  `test_workspace_settings_llm_status.py`, and the random-UUID assertions in this file) test
  **genuinely absent rows** — the new rule answers them 404 too. None asserts a foreign row
  reading as absent.
- `frontend/src/components/react/LLMConfigEditor.tsx:441` matches "reads as absent" but is about a
  whitespace-only *value* normalizing to absent, unrelated to the status rule.
- **The frontend does not branch on this endpoint's status.** `frontend/src/lib/custom-providers-api.ts`
  propagates the `ApiRequestError` untouched, and
  `frontend/src/components/react/CustomProviderDialog.tsx:126` branches only on `err.status === 409`. A
  403 therefore lands on the same generic save-error message the old 404 produced: no user-visible
  change. Corrected after the independent verification pointed out that this claim was originally
  narrower than the grep behind it.

## Review

**The native review could not complete. No candidate was admitted, no authority was burned, nothing was
corrected.** This change is gated but **not natively reviewed**, and that must not be rounded up to
"done".

Lineage `review-de3bd6f5044ede24`, started 2026-09-24 against commit `366ed6e`: tier `medium`, one lens,
`review-reliability`, 182 changed lines, correction budget 91. The projection was correct — exactly the
four files of this work unit, with no accumulated drift from the other batches, because this branch
carries one commit off `main`.

The reviewer slot was captured once, after the operator authorised the forecast run (one model run, one
lens). It failed in the transport, not in the review:

```
outcome: pi-host-relay-transport-failure
failure: {kind: reviewer-empty-output, stage: pi, exit_code: null, timed_out: false,
          elapsed_ms: 58917, timeout_ms: 923639, reviewer: {stopReason: length}}
reason:  "Reviewer produced no text for review-reliability (stopReason: length)."
mutation_performed: false
```

The model ran for about 59 seconds and returned **no text at all**: the output budget was exhausted before
any artifact existed. `mutation_performed: false` on every attempt, and a fresh `STATUS` reoffered the
same slot against the same revision, so the native state stayed consistent — the failure lives entirely in
the relay, not in the review authority.

This is the **second observed failure mode of the same `pi_host_relay` step**. The first is recorded in
`odd/tasks/prod-honesty-followups.md`: four attempts, each around 55 seconds, ending in
`Expected property name or '}' in JSON at position 1`, also with no artifact and no burned authority. Two
distinct failure shapes in one relay step mean the relay is the blocker, not the candidate.

The operator decided on 2026-09-24 to publish this change under the repository's ordinary policy with the
review recorded as **not run**, rather than leave it unpublished while the relay is broken. That decision
is the operator's; this record does not treat a missing review as an approval, and re-running the review
later stays open.

## Deliberately not done

- `projects.py` and `extraction.py` already implement the chosen rule — untouched.
- No `EntityNotFound` dependency introduced into the provider handler: the existing 404 response
  stays byte-identical.
- The frontend is untouched: the only status branch on this path is
  `CustomProviderDialog.tsx:126` (`err.status === 409`), and a 403 falls through to the same generic
  error the old 404 produced.
- `prod.todo.md`, `AGENTS.md`, `CONTRIBUTING.md` and the version manifests are untouched.
- Unifying to "404 for everything" (the opposite direction) was **not** taken and would need its own
  API-contract decision if ever revisited; this record does not relitigate it.
