# ODD Feature: advisory-closures

> **Status**: landed on `main` @ `841c7e0` (three commits, ff-merge). Native review
> `review-45ff50e217b6a3a5`: approved and burned, no correction; seven non-blocking advisories, listed below.
> **Created**: 2026-09-21
> **Workflow**: Organic Driven Development (ODD)

## Problem

The `prod-checklist-honesty` batch closed with three advisories open **by decision**, not by oversight: the
review's own closure says advisories are separate later work and never a reason to re-run review on the
candidate that produced them. Two of the three are this batch:

- `R3-waf-3` — `prod.todo.md`'s rate-limiting row recommends a "Vercel WAF" for a backend that the same
  batch documented as **not** being on Vercel. An internal contradiction the batch introduced.
- `R3-pubip-1` — the production VM's public address written into a tracked document, while the deploy
  workflow deliberately takes it from a `DEPLOY_HOST` secret.

The third, `R3-evid-2`, is cosmetic wording on the integration-test row and stays where it is.

One more item was decided into the same batch: a note in `docs/testing.md` recording what the backend
suite's warning actually is, why its count cannot be compared between runs, and the fact that **nothing
gates on it**.

## Scope, measured before writing

`git grep` over tracked files, because the instrument that answers "where is this claim stated" is not the
advisory id: each claim turned out to live in more than the one file the id named.

| Claim | Named by | Also stated as the document's own fact in |
|---|---|---|
| "Vercel WAF" for rate limiting | `prod.todo.md` (`R3-waf-3`) | `docs/security.md`, `todo.md` |
| The VM's public address | `docs/deployment.md` (`R3-pubip-1`) | `AGENTS.md` (ADR-005 Contexto) |
| Env-var audit "in Vercel" | — (found while measuring) | `docs/security.md` |

**Historical records are deliberately left as written.** `odd/tasks/prod-checklist-honesty.md` quotes both
claims while describing what was corrected, and `odd/tasks/schema-drift-reconciliation.md` states what was
true at the time. They are the evidence of the correction; rewriting them would erase it. The schema
document gets a dated **addendum** instead, which is how the rest of this repository supersedes without
deleting.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Blast radius of the address | **Operator-selected.** Fix `docs/deployment.md` **and** `AGENTS.md`; leave the record as written. Consequence accepted: the candidate becomes tier `medium` with one mandatory lens, because any edit to `AGENTS.md` is an executable change in the file that governs agents. |
| D2 | The env-audit row | **Operator-selected.** Fix it here: same defect class as `R3-waf-3`, and leaving it would leave the same contradiction one row down. |
| D3 | The extra locations of the WAF claim | **Extrapolated from D1**, and flagged: fix every live document that states the claim, never a historical record. A one-file fix would leave the repository contradicting itself, which is the exact defect class being cleaned. |

## What lands

- `prod.todo.md` — rate-limiting row and env-audit row.
- `docs/security.md` — the same two lines in its "Producción (pendiente)" list.
- `todo.md` — the rate-limiting line.
- `docs/deployment.md` — the backend host, replaced by the name of the secret that carries it.
- `AGENTS.md` — ADR-005's Contexto, same replacement.
- `docs/testing.md` — a new subsection on the suite's warning.
- `odd/tasks/prod-checklist-honesty.md` — both advisories marked closed, with the measured blast radius.
- `odd/tasks/schema-drift-reconciliation.md` — a dated addendum recording that the refusal path is now
  exercised by a test, superseding the paragraph that said only production could exercise it.

## The warning, and why the note is not "a warning exists"

Four runs of the whole suite on the candidate's base, in this order:

```
745 passed, 3 skipped, 1 warning   sqlalchemy/orm/loading.py:186
745 passed, 3 skipped, 1 warning   sqlalchemy/sql/compiler.py:7243
745 passed, 3 skipped, 1 warning   sqlalchemy/sql/compiler.py:7243
745 passed, 3 skipped, 1 warning   sqlalchemy/sql/compiler.py:7243
```

What is measured: the warning is a `RuntimeWarning: coroutine 'Connection._cancel' was never awaited`,
attributed in all four runs to the same test
(`tests/test_repositories/test_custom_provider_repo.py::test_list_is_empty_for_a_fresh_workspace`), while
the SQLAlchemy frame that reports it **moves between runs**. An earlier measurement of the same tree
produced counts of `1, 1, 1, 2`, so the count is not a property of the tree either.

That is why the note in `docs/testing.md` says what it says: the warning cannot be used as an instrument to
compare a candidate against its base, and **nothing gates on it** — `backend/pytest.ini` declares no
`filterwarnings`, CI runs `pytest -q` with no `-W error`, and no script compares counts. A new warning
breaks no gate; the only instrument that sees it is reading the output.

## Two harness defects that this batch's predecessor had to pay for

Recorded here because both are reusable, and neither was in the repository before: the previous session
left a candidate (`2252640`, the refusal-path test) **unreviewable**, and unblocking it took two separate
diagnoses.

1. **A mis-transcribed `subject_hash` wedges a lineage.** The reviewer must echo a 64-hex subject hash;
   the model returned 60 characters. Admission rejected it with `binding_mismatch` **without consuming the
   lens slot**, and the relay then replays the preserved rejected bytes instead of re-running the lens —
   measured twice, at 258 ms and 232 ms, both naming the same preserved artifact whose `attempt` field says
   `1`. A fresh START answers `action: replayed`, so no new lineage is minted while the target is unchanged.
2. **A `STATUS` before the candidate view exists poisons the session.** The facade indexes retained capture
   routes by the binding's identity, not by the lineage. A `STATUS` taken before the candidate view existed
   retained the route with `baseRef: undefined`; the `START` that then materialized the view retained the
   **same** binding with `baseRef: <base commit>` and the registration is rejected with
   `capture-route-registration-rejected` — thrown **before** the stale-route pruning in the same function,
   so the session never recovers on its own. The retained map is process memory only, so a session reload
   clears it; that is what unblocked it.

The prescribed order — `inspect → start → STATUS → capture` — avoids the second one, and the first is
recoverable with `abandon` (whose `reason` is an enum, `operator_disposition` | `retired_schema`, not free
text) followed by a fresh `START`, which does re-mint the lineage and reuses its id.

## Gates

This candidate's diff is documentation only — no file under `backend/src`, `backend/tests` or
`frontend/src` changes — so the code surface is byte-identical to the one measured on its base. The
measurements that apply, all taken on that identical code during this session:

| Gate | Result |
|---|---|
| `pytest -q` (whole backend suite) | 745 passed, 3 skipped, 1 warning — four runs, 29.29 s to 34.80 s |
| `ruff check src tests` | all checks passed |
| `ruff format --check src tests` | 231 files already formatted |
| Frontend `tsc` / `vitest` | not part of this candidate's surface; no frontend file changes |

The one warning is the subject of the `docs/testing.md` note above, and it is pre-existing: it reproduces on
the base and on the candidate alike, which is exactly why the note says the count cannot be used to
attribute it to a change.

## Review

Native review of the three commits as one candidate (`2252640..841c7e0`), lineage
`review-45ff50e217b6a3a5`: **approved and burned**, no correction opened,
`prepared_reviewers: 4, submitted_reviewers: 4`.

The tier is the part worth carrying forward. The diff is documentation only, yet the candidate came back
**`high` with four lenses** (`risk`, `resilience`, `readability`, `reliability`), and the reason names a file
rather than a change:

```
risk_reasons: [{code: hot_path, signal: security, path: docs/security.md}]
risk_evidence: ["security in docs/security.md"]
```

The edit in that file is two checklist bullets. The classifier keys on the **substring in the path**, which
makes `docs/security.md` a security hot path. Same family as the extension-keyed `process_boundary` recorded
in `release-versioning.md`: the tier comes from the path, not from the diff. Consequences for planning: any
edit to `AGENTS.md` is `medium` with a mandatory lens (it is the file that governs agents) and any path
carrying a hot-path signal is `high` with four lenses, whatever the diff contains. Not worth fighting — the
binding is opaque and the tier is the provider's — but worth budgeting **before** the work instead of
discovering it during review. The alternative, skipping the file, was rejected: leaving the stale claim in
place is the defect class this batch exists to clean.

### Advisories (seven, all `SUGGESTION` / informational)

None opened a correction. The closure's own words are that they are separate later work and never a reason to
re-run review on this candidate. It lists them by id and location **without their text**, so each row is the
whole record of it and the location is where the reviewer saw the concern:

| Id | Lens | Location |
|---|---|---|
| `R2-dup-warn-note` | readability | `docs/testing.md:116-129` |
| `R2-scope-mix` | readability | `odd/tasks/advisory-closures.md:77-100` |
| `R2-stale-status` | readability | `odd/tasks/advisory-closures.md:3` |
| `R3-unverifiable-gates` | reliability | `odd/tasks/advisory-closures.md:97-107` |
| `R3-warning-note-consistency` | reliability | `docs/testing.md:116-133` |
| `R4-doc-gate-1` | resilience | `docs/testing.md:116-130` |
| `R4-doc-recovery-1` | resilience | `odd/tasks/advisory-closures.md:104-112` |

`R2-stale-status` points at line 3, which is the status line rewritten by this commit; if that is what the id
meant, this commit closes it. The other six stay open on purpose and belong to whoever picks up the warning
note and this record next.
