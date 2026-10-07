# SDD Archive Report — extraction-versioning-prompt

> **Written by hand, not by `openspec archive`.** The CLI is neither installed on this machine nor a
> dependency of this project. The owner asked for the merge and the move, executed as a manual
> transformation on 2026-10-07, mirroring the sibling archive of `extraction-versioning-api`. Everything
> the tool would have computed automatically is measured here rather than assumed, and the one check
> that could not run is named at the end.

## Archive Status

**PASS with one caveat.** The change was delivered to `main` and released before being archived.
Canonical specs were written for all four domains by transforming the delta files — eighteen
requirements appended (`ADDED`), four replaced in place (`MODIFIED`), zero `REMOVED` — and the active
change folder was moved, unchanged, to the dated archive at
`openspec/changes/archive/2026-10-07-extraction-versioning-prompt/`. **No source code was modified by
the archive step.**

**Caveat: `openspec validate` did not run.** The merge was instead guarded by mechanical checks run
before and after: per-capability requirement and scenario counts, a duplicate-requirement-title check
over every merged canonical file (empty result), an assertion that every delta requirement title is
present in its canonical file exactly once, and an exact-match assertion on every `MODIFIED` title
before its canonical block was replaced. Those are formatting guarantees, not the tool's semantic one.

## Final State

- **Tasks:** every checkbox task in `tasks.md` is closed — measured 2026-10-07: **47 checkbox lines,
  all `[x]`, 0 unchecked** (`grep -cE '^\s*- \[ \]'` → 0). A naive string count reads **2** hits for
  `[ ]`, and both are **prose quoted inside dated `[WU3 part …]` notes, not open boxes**: the note at
  the 3.1/3.2/3.3 tasks ("**3.1, 3.2 and 3.3 stay `[ ]`**") and the note at task 3.9 ("**3.9 stays
  `[ ]`**") are earlier snapshots describing an interim state — all four of those boxes are checked
  today. The box-count is the fact; the note-text is not.
- **Verification:** the report is `verify-report.md` (this change's own artifact, not the sibling's
  `verification.md`), and its structure is the verdict — §1 the honest split of what ran where (1282
  passed + 45 skipped locally, 1303 + 24 in CI, reconciled as 1327 collected; 21 Docker-gated cases
  ran in CI; the live-Qdrant layer ran **22 passed** on this machine against Qdrant Cloud and cannot
  run in CI, so its evidence is this run's), §2 the no-shortcut sweep over the extraction path (the
  story text reaches the prompt whole; `max_tokens=2048` is an output budget in every adapter;
  neither context read is paginated), §3 the two production defects the live layer found and fixed
  (below), §4 the four provider usage rows — two confirmed against real responses, two *not
  confirmed*, §5 the 1/50/200 bench ladder and the mandatory 1000-story project, both run against
  production's database with vector points pinned to the dev collection, §6 what the version row
  records, §7 the disclosure of the data the benches wrote to production's database and its measured
  removal (nine bench workspaces deleted under an interlock; production's vector collection untouched,
  0 points before and after), and §8 the bottom line. It carries no numeric requirement-coverage
  verdict, and none is invented here; the counts below are measured from the delta files themselves.
- **Spec coverage, counted now:** **22 requirements and 59 scenarios across four capabilities**
  (**18 `ADDED` / 4 `MODIFIED` / 0 `REMOVED`**). One capability (`extraction-context`) is new to the
  store; `extraction-versioning`, `few-shot-retrieval` and `vector-store-isolation` already existed
  and grew or were replaced in place.
- **Open defects at archive time**, read from this change's own artifacts (`verify-report.md`,
  `apply-progress.md`, `tasks.md`):
  - **D10 — closed.** The slice's named cross-slice dependency: the vector validity flag and the
    fail-closed retrieval filter. `apply-progress.md` §W3-C records its closure — the mark and revoke
    handlers refresh `has_invalid_tasks` (refresh before the relational write, per the accepted
    correction), the search filter carries the exclusions, and the live-Qdrant layer proved both
    against the real service. Its residual is **named, not absorbed**: the revoke path's stale-count
    window — two concurrent revokes of two different marks on the same extraction each count with only
    their own mark excluded, so the flag can stay `true` after both land — the same check-then-act
    class slice (b) already carries on the mark side.
  - **D7 — closed.** The negative-example block fed by (b)'s marks. WU1 shipped the block's slot
    empty; WU2 wired (b)'s `list_active_on_other_versions` read and the composition, so the prompt of
    version `n+1` carries every mark of all previous versions of the story, capped at 20, most recent
    first, deduplicated, self-announcing on truncation, with the omitted count in the snapshot.
  - **Closed mid-stream, recorded for the next reader:** the live run exposed two production defects
    no unit test could — the filtered search excluded on `user_story_id` with **no payload index** on
    it, which Qdrant refused with `400 Index required but not found` and graceful degradation turned
    into an **empty list** (few-shot retrieval silently disabled with every unit test green; fixed by
    indexing `user_story_id` as `KEYWORD` — the design's index list named three fields, the filter
    used four), and an absent-point `set_payload` that the unit layer had assumed quiet but the live
    server answers `404` (the setter now honours the no-op by shape). The three unit index pins that
    were red at that head were resolved by the close-out under explicit authorization; the final
    verification table in `apply-progress.md` is all green.
  - **Still open at archive time:**
    - **The OpenAI and Anthropic usage rows are *not confirmed*** — no credential in this environment,
      which `verify-report.md` §4 states as that and not as "absent from the provider". The rule holds
      either way: no container, no `usage` key, never zero-filled.
    - **The no-op catch string-matches the server's error body** (`"No point with id"`); a Qdrant
      version that rewords the message would reintroduce the raise. Accepted trade-off, disclosed
      rather than absorbed.
    - **Two product findings from the real provider calls**, product-relevant beyond tests: the repo's
      pinned Gemini model names (`gemini-2.0-flash`, `gemini-2.5-flash`) answer **404 "no longer
      available to new users"** while `client.models.list()` still lists one of them — a picker built
      from `list()` would offer dead models; and a thinking model can consume the whole output budget
      (`max_output_tokens=64` → `finish_reason=MAX_TOKENS`, zero parts). This matters for the owner's
      pending action **D-a-6** (production has no LLM configuration; `resolve_llm_config` falls back to
      an Ollama that does not exist there): when the configuration is recreated, a 2.x model name will
      fail on the first extraction. D-a-6 remains outside this slice's evidence.
- **Implementation:** merged to `main` on **2026-10-03** as ten PRs — **#40, #41, #42, then #44
  through #50**; #43 was closed unmerged and re-opened as #44 — released in
  **`v0.11.0`**. The head the change's own report verified is `55e9949` plus the report commit on the
  WU3-D branch (PR #50), as recorded in `verify-report.md`.
- **Production state verified read-only on 2026-10-07**, by which time later releases had also
  landed: `/api/v1/health` reports `version: 0.12.0` with `database` and `schema` `ok`, and
  `/api/v1/health/ready` responds 200.

## Artifacts Read

`proposal.md`, `design.md`, `tasks.md`, `apply-progress.md`, `state.yaml`, `verify-report.md`,
`explore.md`, and all four `specs/*/spec.md` deltas. The transformation was applied from the delta
files, not from memory.

## Domains Synced

| Capability | Mode | Delta reqs (scenarios) | Resulting file |
| --- | --- | --- | --- |
| `extraction-context` | new capability (`ADDED` ×8) | 8 (20) | `openspec/specs/extraction-context/spec.md` — 8 reqs / 20 scenarios |
| `extraction-versioning` | `ADDED` ×7 | 7 (17) | `openspec/specs/extraction-versioning/spec.md` — 22 reqs / 70 scenarios |
| `few-shot-retrieval` | `MODIFIED` ×1, `ADDED` ×1 | 2 (7) | `openspec/specs/few-shot-retrieval/spec.md` — 3 reqs / 9 scenarios |
| `vector-store-isolation` | `MODIFIED` ×3, `ADDED` ×2 | 5 (15) | `openspec/specs/vector-store-isolation/spec.md` — 6 reqs / 16 scenarios |

Per capability: `extraction-context` did not exist in `openspec/specs/` and was **created** from its
delta in the canonical format. `extraction-versioning` was **pure append** — seven blocks added after
its last existing requirement, growing 15/53 → 22/70. `few-shot-retrieval` was **one in-place
replacement** (`Unified few-shot prompt section`, 2 scenarios → 5) plus **one append**, growing 2/4 →
3/9; the untouched `Retrieval respects config` kept its position. `vector-store-isolation` was **three
in-place replacements** (`Workspace-scoped retrieval` 2→5 scenarios, `Legacy points excluded` 1→2,
`Payload index` 1→1) plus **two appends**, growing 4/5 → 6/16; the untouched `Seed migration` kept its
position. Every `MODIFIED` replacement was matched on its exact `### Requirement:` title before the
canonical block was touched; no title required guessing, and no canonical text outside the replaced
blocks was altered. Delta files moved to the archive unchanged.

## Active Same-Domain Change Warnings

Sibling slice (b) `extraction-versioning-api` is **already archived** at
`openspec/changes/archive/2026-10-07-extraction-versioning-api/`, and this change depends on it
(`state.yaml` lists `extraction-versioning-schema` and `extraction-versioning-api` as dependencies).
With both (b) and this change archived, no same-domain change remains active in `openspec/changes/`.
**Task IDs are not renumbered by this archive**, and both slices' artifacts stay readable at their
archived paths. This slice hands nothing downstream — it was the last of the three slices to land —
but it leaves one standing operational fact: until D-a-6 is closed, extraction cannot run in
production, and when the configuration is recreated it must use a Gemini model name that still
accepts new users.

## Unchecked Implementation Tasks

None open. Measured 2026-10-07: 47 checkbox lines, all `[x]`, 0 unchecked. The two `[ ]` strings a
naive grep finds are prose inside dated notes describing an interim state (see Final State).

## Structured Status and actionContext Findings

**Not available.** These are produced by `openspec` itself; with the CLI absent they are not
reproduced here by hand, because a hand-written imitation of a machine-generated status is exactly the
kind of evidence that should not exist in an archive report.

## Delivery Strategy Resolution

Delivered as ten merged PRs — **#40, #41, #42, then #44 through #50**; #43 was closed unmerged and
re-opened as #44 — merged 2026-10-03 and released in `v0.11.0`, with **#44 the
re-opened WU2 split**. Per-unit diffstats are recorded in `apply-progress.md` where each unit closed
(for example, W3-C's 496+/6− code+tests, W3-D's 465+/4−); this report does not restate a chain-wide
size. Whether receipt-driven development mode was on at merge time is session state, not an artifact
of this change; no artifact here records it, and this report does not invent it.

## Archived Path

`openspec/changes/archive/2026-10-07-extraction-versioning-prompt/` — the folder date is the archive
date (2026-10-07); the merge date (2026-10-03) is carried by this report above.
