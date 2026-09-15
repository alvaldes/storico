# SDD Archive Report — us-decomposition

## Archive Status

**PASS.** The verified and synced change `us-decomposition` was archived successfully. The active change
folder was moved to the dated archive at `openspec/changes/archive/2026-09-14-us-decomposition/`. No source
code was modified by this phase.

Archive executed under the authoritative native `gentle-ai.sdd-status` v2 projection
(`nextRecommended: archive`, `dependencies.archive: ready`, `taskProgress.allComplete: true`,
`blockedReasons: []`) and explicit parent authorization in the final-state handoff. Archive-time sync
fallback was **not** needed: a successful `sync-report.md` already exists and the canonical specs are
committed.

## Control Gates

| Gate | Result |
| --- | --- |
| Verify report resolves at locator | ✅ `openspec/changes/us-decomposition/verify-report.md` (in-tree) |
| Verdict clearly passing | ✅ `pass_with_warnings`, `blockers: 0`, `critical_findings: 0`, 17/17 requirements, 21/21 scenarios |
| Unresolved `FAIL` / `BLOCKED` / `CRITICAL` / verification blockers | ✅ none |
| Required artifacts present | ✅ proposal, 4 per-domain specs, design, tasks, verify-report, sync-report |
| Legacy flat `spec.md`-only condition | ✅ not present (restructured to `specs/{domain}/spec.md`) |
| File-backed canonical sync complete | ✅ `sync-report.md` reports `synced`; commit `a93a215` |
| Same-domain canonical overwrite risk | ✅ none — all four canonical specs were created new |
| Destructive merge (REMOVED / large MODIFIED) | ✅ not applicable — all deltas are `## ADDED` |
| Unchecked implementation tasks | ✅ none — `grep '^\s*- \[ \]' tasks.md` returns no matches (23/23 checked) |
| Stale-checkbox reconciliation performed | ✅ no — no unchecked lines existed, so no repair was needed or done |
| Task completion gate re-read immediately before report write and move | ✅ 23/23 checked, unchanged |
| Ownership / allowed edit roots | ✅ all move targets resolve inside `/Users/alvaldes/Developer/storico`; `actionContext.mode: repo-local` |
| Working tree clean before archive | ✅ all change artifacts (spec restructure, verify-report, sync-report) committed |

## Artifacts Read

- `openspec/changes/us-decomposition/proposal.md`
- `openspec/changes/us-decomposition/specs/{extraction-workflow,kanban-board,task-editor,export-download}/spec.md`
- `openspec/changes/us-decomposition/design.md`
- `openspec/changes/us-decomposition/tasks.md`
- `openspec/changes/us-decomposition/verify-report.md`
- `openspec/changes/us-decomposition/sync-report.md`
- `openspec/config.yaml` (no `rules.archive` and no `rules.sync` defined, so no extra archive rules applied)
- Native status projection `gentle-ai.sdd-status` v2 for `us-decomposition`

## Domains Synced

| Domain | Canonical file | Requirements | Scenarios |
| ------ | -------------- | ------------ | --------- |
| `extraction-workflow` | `openspec/specs/extraction-workflow/spec.md` | 3 | 5 |
| `kanban-board` | `openspec/specs/kanban-board/spec.md` | 5 | 5 |
| `task-editor` | `openspec/specs/task-editor/spec.md` | 4 | 5 |
| `export-download` | `openspec/specs/export-download/spec.md` | 5 | 6 |
| **Total** | | **17** | **21** |

All four canonical files were created by `sdd-sync` (commit `a93a215`) from the corresponding delta specs:
`## ADDED Requirements` normalized to the canonical `## Requirements` header, the `> **Change**:
us-decomposition` annotation dropped, requirement/scenario blocks copied byte-identically. Counts
re-confirmed at archive time: `grep -c '^### Requirement:'` over the four canonical files returns
3/5/4/5 = 17, matching the verify report.

## ADDED / MODIFIED / REMOVED Requirement Names

All deltas were `## ADDED`. **No** `MODIFIED`, `REMOVED`, or `RENAMED` requirements were present, so the
merge was purely additive and no canonical requirement was replaced or deleted.

- **extraction-workflow (ADDED):** Workspace-Scoped Extraction Client; Extraction Error Surfacing; Unauthorized Access Handling.
- **kanban-board (ADDED):** Kanban Page Route; Kanban Board Component; Kanban Task Fetching; Kanban Drag-and-Drop Status Update; Kanban Empty States.
- **task-editor (ADDED):** Task Editor Component; Task Editor Trigger; Task Editor Persistence; Labels and Dependencies Validation.
- **export-download (ADDED):** Export Page Route; Export Panel Component; Backend Export Endpoint; Export Format Schemas; Export Error Handling.

## Active Same-Domain Change Warnings

**None.** `relationships.sameDomainActiveChanges` and `collisions` are empty in native status, and
`openspec/changes/` contained exactly one non-archive change (`us-decomposition`) before this move. No other
active change touches `extraction-workflow`, `kanban-board`, `task-editor`, or `export-download`.

## Destructive Merge Approvals / Blockers

**None required, none outstanding.** No `REMOVED` requirements, no large `MODIFIED` blocks, no `RENAMED`
requirements, and no overwrite of an existing canonical file. No destructive-sync approval was needed, so
none was consumed.

## Final State (post-verify fixes — authoritative over the verify snapshot)

The persisted `verify-report.md` (`pass_with_warnings`, 17/17 requirements, 21/21 scenarios, 0 blockers)
was written **before** three follow-up fixes. Those three WARNING-level spec-fidelity deviations it recorded
are now **RESOLVED in code**, with evidence:

1. **Markdown export dependencies** — the endpoint previously rendered `→ {dep}` verbatim from the stored
   dependency value. It now resolves each dependency to the referenced task's title (by id, else by title
   case-insensitively, else falls back to the raw value). Commit `6c7816d`
   (`backend/src/storico/api/routes/export.py`, `backend/tests/test_api/test_export.py`). Evidence:
   `cd backend && conda run -n storico python -m pytest tests/test_api/test_export.py` → 9 passed.
   Resolves residual deviation #2.
2. **TaskEditor dependencies input** — previously a free-text chip input. It is now a multi-select of
   sibling tasks in the same story keyed by `task.id`, excluding the edited task and hiding
   already-selected siblings, which also satisfies the same-story restriction. Commit `e68c020`
   (`frontend/src/components/react/TaskEditor.tsx`, i18n, tests). Evidence: `cd frontend && pnpm test`
   → 55 passed (incl. 3 new dependency tests + 1 new ExportPanel test). Resolves residual deviation #1.
3. **Empty-workspace export** — `ExportPanel` previously disabled Download when the workspace had no tasks.
   It is now enabled whenever a workspace is selected (the backend returns valid empty content: `[]` for
   JSON, an empty Markdown header). Commit `e68c020`. Resolves residual deviation #3.

Earlier remediation already reflected in the verify snapshot: commits `82d36d0` (export Markdown grouped by
story) and `66b9675` (401 auth handling, kanban drag lock, kanban zero-tasks empty state).

### Current evidence (final state)

- Backend full: `cd backend && conda run -n storico python -m pytest` → **395 passed, 1 skipped, 14 failed**.
  The 14 failures are **PRE-EXISTING** (`test_extraction.py` (4), `test_extractions.py` (4),
  `test_tasks.py` (6)); the verify phase reproduced the identical failure set on the committed baseline
  worktree (`d11b0b8`) and on the pre-implementation commit (`ca04f83`). They are unrelated to this change
  and were never blockers.
- Frontend: `cd frontend && pnpm test` → **55 passed**; `pnpm exec tsc --noEmit` → exit 0.
- Sync: four canonical specs created under `openspec/specs/`; `sync-report.md` written and committed
  (`a93a215`); 17 requirements / 21 scenarios.

## Known Gaps and Carried Deviations (recorded, non-blocking)

1. **Missing `apply-progress.md` (strict-TDD apply evidence)** — `openspec/config.yaml` declares
   `strict_tdd: true`, and the strict-TDD verify module instructs that a missing `TDD Cycle Evidence` table
   be flagged CRITICAL. This is **structural, not a protocol breach**: the change artifacts and the
   implementation landed together in the single historical commit `eb71c3b` (2026-07-20, 49 files), so no
   SDD apply phase ever ran to emit apply-progress and that evidence cannot be produced retrospectively.
   The verify phase recorded it as a disclosed, non-blocking WARNING under explicit parent authority, and
   the parent's final-state handoff authorized archive with this gap recorded. What is verifiable was
   verified: every relevant test file exists, was read, and passes on execution. **This is a recorded
   exception, not a stale-checkbox repair** — there were no unchecked task boxes to reconcile.
2. **`design.md` filename drift** — `design.md` names the export filename
   `storico-tasks-{id}.{ext}` while the implementation uses `tasks-export-{workspace.id}.{ext}`. The
   canonical `export-download/spec.md` does not mandate a basename, so the implementation satisfies the
   authoritative spec; this remains a design-artifact note for the design owner.
3. **Delivery vs. forecast** — `tasks.md` forecast 750–850 changed lines with `400-line budget risk: High`
   and chained PRs recommended, while session preflight selected `ask-on-risk` with a deferred chain
   strategy; no `size:exception` was accepted. The original implementation landed historically as one
   commit (`eb71c3b`), and this session added 6 focused remediation/artifact commits under
   `stacked-to-main` review units. Recorded as a process WARNING carried from the verify report, not an
   archive blocker.

## Unchecked Implementation Task Lines

**None.** `openspec/changes/us-decomposition/tasks.md` has 23/23 implementation tasks checked
(`- [x]`), and a scan for `^\s*- \[ \]` returns no matches — re-read immediately before this report was
written and again before the folder move. No stale-checkbox reconciliation was required or performed.

## Non-Critical Partial Archive Approval

**Not applicable.** No partial archive: all required artifacts exist (proposal, four per-domain specs,
design, tasks, verify-report, sync-report) and all 17 requirements were synced canonically. No
intentional-partial-archive approval was needed.

## Structured Status and actionContext Findings

Native `gentle-ai.sdd-status` v2 consumed unchanged as the sole archive-readiness authority — no
recomputation from OpenSpec or memory artifacts:

- `changeName: us-decomposition`; `artifactStore: openspec`; `planningHome.mode: repo-local`.
- `changeRoot: /Users/alvaldes/Developer/storico/openspec/changes/us-decomposition`.
- `taskProgress: {total: 23, completed: 23, pending: 0, allComplete: true}`.
- `artifacts: {proposal: done, specs: done, design: done, tasks: done, applyProgress: missing,
  verifyReport: done}`; `applyState: all_done`.
- `dependencies: {proposal: all_done, specs: all_done, design: all_done, tasks: all_done, apply: all_done,
  verify: all_done, archive: ready}`; `nextRecommended: archive`; `blockedReasons: []`.
- `actionContext: {mode: repo-local, workspaceRoot: /Users/alvaldes/Developer/storico,
  allowedEditRoots: ["/Users/alvaldes/Developer/storico"]}` — every archive/move target resolves inside the
  authoritative workspace and allowed edit roots; ownership proven; no `workspace-planning` mode, no active
  change selection ambiguity, no store-specific bypass.
- `remediationState.required: false` — no failed-evidence accounting was open.

## Archived Path

```text
openspec/changes/us-decomposition/
  -> openspec/changes/archive/2026-09-14-us-decomposition/
```

Moved with `git mv` on the ISO date 2026-09-14 (existing archives: `2026-07-11-account-linking`,
`2026-07-13-workspaces`, `2026-07-15-first-login-onboarding`, `2026-09-14-few-shot-examples`,
`2026-09-14-few-shot-qdrant`). The folder is retained unmodified as the audit trail; nothing was deleted.
Archived contents: `proposal.md`, `specs/` (4 domains), `design.md`, `tasks.md`, `verify-report.md`,
`sync-report.md`, `archive-report.md` (this file). No `apply-progress.md` (see Known Gaps #1).

## Memory Observation IDs

Not applicable. The active artifact store is `openspec`, so this phase's artifact is the file
`archive-report.md` moved into the archive; no Engram artifact observation was required or created for this
change's archived record. The canonical merge layer for this change lives in the file-backed
`openspec/specs/` tree, not in a memory topic.

## Next Recommended Phase

**None (change closed).** `us-decomposition` is archived. Optional follow-ups outside SDD: re-align
`design.md`'s export filename if a design artifact refresh is desired, and address the 14 pre-existing
backend failures as separate remediation work (unrelated to this change).
