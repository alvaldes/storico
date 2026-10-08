# ODD Feature: open-findings-closure

> **Status**: **open** — authorized by the owner on 2026-10-07, in the same session that read the
> agenda. Branch `fix/open-findings-closure`, cut from `main` at `1d350fa`.
> **Created**: 2026-10-07
> **Workflow**: Organic Driven Development (ODD)
> **Receipt-driven development**: off in this clone.
> **Source**: `odd/tasks/docs-pass-open-findings.md` (the review agenda). This feature closes what
> that agenda left open: item C, which is `odd/tasks/csv-story-import.md` follow-ups 6, 10 and 11;
> item B; and item D. Item A was already closed by `fix/llm-test-workspace-scoped`.

## Problem

Four open items sat in two documents and none of them was in flight. The owner read the agenda on
2026-10-07 and decided each one, so nothing here is inferred: every work unit below names the
decision it implements.

| Item | Decision (owner, 2026-10-07) | Nature |
| --- | --- | --- |
| C / follow-up 10 | Implement it | Code |
| C / follow-up 6 | Implement it | Code |
| B | **Keep** the behaviour, close the item as re-confirmed | Record only |
| D | **Correct** the four drifted locations | Docs |
| C / follow-up 11 | Attempt the real production upload | External measurement |

## What each item was, measured before anything changed

All five measurements were taken on `main` at `1d350fa`, which is the branch point.

**Follow-up 10 — the accessible-name collision is live in four components.**
`ErrorDisplay` accepts an optional `retryLabel` (`frontend/src/components/react/ErrorDisplay.tsx:26`).
Four call sites give the retry button the same accessible name as another button rendered in the same
state:

- `StoryForm.tsx:526` — `retryLabel={initialData ? t.common.save : t.common.create}`, the identical
  expression the footer submit renders (`:543`); both reach `handleSubmit`. The exact shape
  follow-up 9 fixed inside the import dialog.
- `TaskEditor.tsx:557` — `retryLabel={t.taskEditor.save}` against a footer that renders
  `t.taskEditor.save` whenever `saving` is false; both call `handleSave`.
- `StoryDetail.tsx:720` — the extraction error card and the header extract button both take
  `t.stories.extraction_retry` in the failed state; both call `handleExtract`.
- `ExportPanel.tsx:169` and `:181` — both take `t.common.retry`, but the first refetches the
  workspace's tasks (`fetchTasksForWorkspace`) and the second re-runs the download (`handleDownload`).
  This is the worse subclass: one name over two different actions.

**Follow-up 6 — no client-side size pre-check.** `ImportStoriesDialog.tsx` has no `file.size` read and
no local cap. The cap lives in the backend at
`backend/src/storico/infrastructure/parsers/story_csv.py:24` (`MAX_FILE_BYTES = 2 * 1024 * 1024`) and
the `413` is only read back from the response. Two pieces the fix needs already exist and are reused
rather than reinvented: the exported `formatFileSize(bytes)` (`ImportStoriesDialog.tsx:96-107`, binary
units, returns `2 MB` for `2097152`) and the `stories.import_file_too_large` key, which the `413` path
already renders (`:361`). No new i18n key is required.

**Item B — the admin reads the stored key back decrypted.** Deliberate. Recorded in
`docs/security.md:88` with the trade-off named, and pinned by
`test_the_admin_reads_back_the_key_it_saved`
(`backend/tests/test_api/test_workspace_settings_llm_config.py:375-394`). Nothing to change; the
item closes as re-confirmed. The `member`-readable `GET /settings/llm/status` remains narrow and
never returns a value.

**Item D — the Docker Compose drift, in four locations.** Section 4's stack row
(`AGENTS.md:249`, "Dev: Docker Compose"), ADR-005's decision and context (`AGENTS.md:320-321`), the
feature row 40 (`AGENTS.md:579`), and `docs/deployment.md`'s heading plus prerequisites (`:6-10`)
with `:68` documenting the Supabase reality on the same page. Measured 2026-09-30: `docker` is not
installed on this machine and the development `.env` points at the Supabase pooler.
`docker-compose.yml` exists and does define `postgres:16-alpine`.

**Follow-up 11 — the production composition has never carried a real upload.** `frontend/src/lib/api.ts`
pins `BASE_URL = ''` so every request goes through `frontend/src/pages/api/v1/[...path].ts`, which is
a Vercel serverless function in production (`frontend/astro.config.mjs:8`). That runtime has its own
request-body ceiling, separate from the backend's `MAX_FILE_BYTES`, and nothing in the repository
verifies where it sits.

## Non-goals

- **Not** re-opening item A. It is closed and its record is `odd/tasks/llm-test-workspace-scoped.md`.
- **Not** a redesign of `ErrorDisplay`. The prop stays; only the four labels and the guard change.
- **Not** a frontend mirror of `MAX_ROWS` or of any other parser limit. Follow-up 6 names the file
  size cap only, and the row cap is a different contract with a different unit (rows, not bytes).
- **Not** a rewrite of any historical measurement in `AGENTS.md`, `docs/deployment.md` or
  `odd/tasks/csv-story-import.md`. History is annotated, never overwritten.
- **Not** a code change for items B or D. Both are records.

## Allowed edit surfaces

- `frontend/src/components/react/StoryForm.tsx`
- `frontend/src/components/react/TaskEditor.tsx`
- `frontend/src/components/react/StoryDetail.tsx`
- `frontend/src/components/react/ExportPanel.tsx`
- `frontend/src/components/react/ImportStoriesDialog.tsx`
- `frontend/src/lib/stories-api.ts`
- `frontend/src/i18n/en.json`
- `frontend/src/i18n/es.json`
- `frontend/src/components/react/__tests__/`
- `frontend/src/lib/__tests__/`
- `AGENTS.md`
- `docs/deployment.md`
- `odd/tasks/docs-pass-open-findings.md`
- `odd/tasks/csv-story-import.md`
- `odd/tasks/open-findings-closure.md`

Anything outside this list is a separate decision.

## Tasks

### WU1 — Follow-up 10: no two buttons in one state share an accessible name

Code. Closes the collision in the four components and lands the guard the follow-up asked for.

- `StoryForm.tsx`, `TaskEditor.tsx`: the error card's retry sits beside the form's own submit, so per
  the rule the follow-up states, it takes `t.common.retry` and never the submit's copy.
- `StoryDetail.tsx`: the extraction error card's retry stops reusing `t.stories.extraction_retry`,
  which the header button already owns in that state. It takes `t.common.retry`.
- `ExportPanel.tsx`: the two call sites must end with **different** accessible names, because they are
  different actions. The store-error retry keeps `t.common.retry`; the download retry is renamed to
  name the download. If no existing key names it, one is added to both locales — the parity guard and
  the neutral-Spanish guard must stay green, and the Spanish must be neutral, never voseo.
- Guard: a test that fails, against the pre-fix tree, on all four sites. Rendering every dialog in one
  file is preferred if it is tractable; otherwise one test per component in the same new file, with a
  shared assertion helper so the rule lives in one place. The criterion is the RED, not the shape:
  removing any of the four fixes must turn it red again.

**Acceptance**: the new guard is RED on `1d350fa` for the four sites and GREEN after; the pre-existing
suites for the four components still pass.

### WU2 — Follow-up 6: refuse an oversized file locally

Code. Small, and it reuses what exists.

- A single frontend constant mirroring `MAX_FILE_BYTES`, with the value `2 * 1024 * 1024`.
- A **mirror test** that reads `backend/src/storico/infrastructure/parsers/story_csv.py` from the test
  process and asserts the two numbers are equal. A hardcoded duplicate expectation is not a mirror
  test; it is a second number that can drift the same way.
- `ImportStoriesDialog.tsx` refuses a file over the cap before the request leaves the browser, using
  the existing `stories.import_file_too_large` key and the existing `formatFileSize`.
- The backend keeps its own check. This is a UX pre-check, not a replacement, and the `413` path stays
  reachable and tested.

**Acceptance**: selecting a file over the cap renders the too-large message and never calls the
import; the mirror test fails if either number moves.

### WU3 — Item D: correct the Docker Compose drift

Docs only. Four locations, and the honest shape is the one the agenda already wrote down: the Compose
path exists in the repository and is one way to run dev; the environment this team measures runs on
Supabase; say which is canonical. The unsupported part — that Compose must be the only dev path —
goes.

- `AGENTS.md` section 4 row (`:249`), ADR-005 (`:320-321`), feature row 40 (`:579`).
- `docs/deployment.md` heading and prerequisites (`:6-10`), so the first screen stops contradicting
  `:68`.
- `AGENTS.md:10`, the note that declared this drift **not corrected**: it becomes a record of what was
  found and when it was corrected, not a live claim.

**Acceptance**: no location in either file still asserts that development runs on Docker Compose, and
no new claim is made about machines nobody measured.

### WU4 — Item B: close it as re-confirmed

Record only. `odd/tasks/docs-pass-open-findings.md` item B moves from "ALREADY DECIDED" to closed,
with the owner's 2026-10-07 re-confirmation and the reason it was re-confirmed rather than changed.
No behaviour, no test, no doc in `docs/security.md` needs to move — that file is already true.

### WU5 — Follow-up 11: measure the production upload path

External measurement. This is the only unit that cannot be finished from the repository.

- Pre-flight, shown to the owner before anything is sent: which deployed host, which workspace and
  project, and **what real rows the upload will create in production**.
- One real multipart upload against the deployed frontend, through the Vercel function into the
  backend, with a session the owner authenticated.
- The size that matters is one near the cap, because the open question is whether the Vercel ceiling
  sits below the backend's 2 MB.
- Evidence recorded in `odd/tasks/csv-story-import.md` follow-up 11: host, file size, the observed
  status and body, and whether the ceiling was ever reached.
- Cleanup: if the upload created stories, they are removed and the removal is recorded.

**Outcome is one of three, and all three close the item**: the hop carries the file (the page's
contract holds in production), the hop refuses it below 2 MB (the contract is wrong in production and
follow-up 6's pre-check is justified and needs the other number), or the owner stops before sending
(it stays open with the reason).

## Evidence

| Work unit | Commit | What gates it |
| --- | --- | --- |
| WU1 | — | — |
| WU2 | — | — |
| WU3 | — | — |
| WU4 | — | — |
| WU5 | — | — |
