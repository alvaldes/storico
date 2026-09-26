# ODD Feature: csv-story-import

> **Status**: in progress — branch `feat/csv-story-import`, stacked off `main` @ `4dcd4fc`.
> Backend first (tasks 1-4), then the UI (tasks 5-8), reviewable as a chained set. Nothing pushed.
> **Created**: 2026-09-25
> **Workflow**: Organic Driven Development (ODD)
> **Receipt-driven development**: off in this clone.

## Problem

Stories can only be created one at a time. `POST /api/v1/stories/` takes a single body, and the only
UI entry point is the `StoryForm` dialog in `StoriesList.tsx`. There is no file upload anywhere in
`frontend/src` — not one `input type="file"` — and no CSV library in `backend/pyproject.toml` or
`frontend/package.json`. A user with a backlog in a spreadsheet has to retype it story by story.

## Scope boundary: this is not `POST /batch`

`POST /batch` is closed as a non-goal (`docs/deployment.md:231`, `AGENTS.md` feature row 10,
`frontend/src/pages/[locale]/api.astro`): it was a **batch extraction** endpoint that never existed,
and "cada extracción es una historia" stays true. This feature is **story creation** from a file, a
different operation, and the endpoint is named `import` deliberately so the two are never confusable.
Nothing here reopens that decision.

## The correction that shaped the design

The exploration's first read of `raw_text` was **wrong**, and the error is worth keeping because the
whole three-column mode depends on getting it right. `raw_text` is not decorative: it is the text
that goes to the LLM.

- `domain/services/extraction_service.py:121` — `raw_text = getattr(user_story, "raw_text", str(user_story))`
- `domain/services/extraction_service.py:145` — `prompt_kwargs: dict[str, object] = {"user_story": raw_text}`

It also feeds the LLM-as-a-Judge (`infrastructure/tasks/extraction_task.py:407`) and the RAG payload
stored in Qdrant (`:559`). The extraction never sees `actor`/`feature`/`benefit`.

Consequences, which are requirements rather than niceties:

1. In three-column mode the `raw_text` this feature **generates is the prompt**. It has to be
   byte-identical to what `StoryForm` produces today —
   `` `As a(n) ${actor}, I want ${feature}, so that ${benefit}` `` with hardcoded English literals,
   independent of locale (ADR-008: stories are English-only, and the persisted text must not move
   with the UI language). This is pinned by a mirror test, following the existing convention
   (`frontend/src/lib/__tests__/llm-config-readiness-mirror.test.ts`,
   `provider-name-mirror.test.ts`).
2. Truncating `raw_text` to its 2000-char cap is not "losing a little text": it mangles the prompt
   sent to the model. Rejection with a reason is the only defensible behaviour, and it is what was
   chosen.

## Findings that constrained the design

| Finding | Evidence | Consequence |
|---|---|---|
| No `UNIQUE` on `(project_id, actor, feature, benefit)` | `infrastructure/database/models/user_story.py:46-49` — two `Index`, no `UniqueConstraint` | The duplicate rule is application-level only. It compares **exact** strings (no case or whitespace normalisation), and duplicates **within the uploaded file** must be caught too — at validation time nothing is in the database yet |
| `save()` commits per call | `repositories/user_story_repository.py:31` | Real atomicity needs a new `save_many` with a single commit. N `save()` calls are N transactions |
| `find_by_parts` is one query per row | `repositories/user_story_repository.py:124-134` | 1000 rows would be 1000 round-trips. Needs one query for the project's existing tuples. The repo already carries scar tissue for this (the `count(*) OVER ()` comment in `routes/stories.py`, "one statement for all workspaces, not one per workspace") |
| No CSV parser and no file input anywhere | `find`/`grep` over `backend/src` and `frontend/src` | The whole file path is new; there is no precedent to copy |
| `task_parser.py` lives in `infrastructure/llm/` | `infrastructure/llm/task_parser.py` | Parsers belong in `infrastructure/`, not in `domain/` |
| `python-multipart` already present, `csv` is stdlib | `fastapi[standard]>=0.115.0` in `pyproject.toml` | Zero new dependencies in the backend. Zero in the frontend: the browser uploads the `File` as-is |

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Where parsing happens | Backend, with the stdlib `csv` module. One source of truth for validation, membership and duplicates; no new frontend dependency and no hand-rolled parser |
| D2 | Endpoint | `POST /api/v1/projects/{project_id}/stories/import`, multipart, field `file`. Named `import` and not `batch` (see scope boundary) |
| D3 | CSV format | Auto-detected by header, case-insensitive and trimmed: `actor` + `feature` + `benefit` → parts mode (optional `raw_text` column, used verbatim when present); `story` / `input` / `raw_text` → full-story mode, parsed to parts. Any other header is a file-level error |
| D4 | Partial failure | **Errors block everything; duplicates are skipped and reported.** Every row is parsed and validated first, and a full report with line numbers comes back. With at least one error nothing is written (`created: 0`, HTTP `422`) |
| D5 | Duplicates | Skip and report, against both the project and the file itself. Importing the same file twice is idempotent: `created: 0`, every row reported as a duplicate |
| D6 | Destination project | The project selected in the UI, carried by the URL path. Reuses the existing gating in `StoriesList` (the create button is already disabled without a project) |
| D7 | Caps | 2 MB validated **before** reading the body; 1000 rows counted during parsing. Each cap has its own reason code, never a timeout |
| D8 | Over-long text | Reject the row with `reason: "too_long"`, carrying `field`, `length` and `max`. No silent truncation, for the reason in the correction above |
| D9 | In-file duplicates | Non-blocking, consistent with D5: the second identical row is skipped and reported with `duplicate_in_file` plus the first line. **Judgment call taken by consistency — overridable by the maintainer** |
| D10 | Auto-extraction after import | **Out of scope for v1.** The endpoint contract is designed so adding it later does not change the response shape. It needs its own concurrency-limit decision and its own conversation, not a paragraph hidden here |

## The contract

```
POST /api/v1/projects/{project_id}/stories/import
Content-Type: multipart/form-data     field: file (.csv)

201 — every row valid
{ "created": 41, "skipped": 3, "total_rows": 44,
  "duplicates": [{ "line": 19, "existing_story_id": "...", "actor": "...", "feature": "..." }],
  "story_ids": [ ... ] }

422 — at least one validation error. Nothing written.
{ "detail": { "error_code": "IMPORT_VALIDATION_FAILED", "created": 0, "total_rows": 44,
    "errors": [
      { "line": 7,  "reason": "missing_field", "field": "feature" },
      { "line": 19, "reason": "too_long", "field": "benefit", "length": 340, "max": 300 },
      { "line": 23, "reason": "unparsable_story" },
      { "line": 31, "reason": "duplicate_in_file", "first_line": 12 } ],
    "duplicates": [ { "line": 88, "existing_story_id": "..." } ] } }
```

Delimiter and encoding: decoded as UTF-8 with the BOM stripped; an invalid encoding is a
file-level error. The delimiter is read off the **header line**, not guessed from the data — see
the spec correction below.

## Spec correction: the delimiter is read off the header, not sniffed from the data

The approved design said `csv.Sniffer` over `,` `;` `\t`, falling back to comma. That was wrong,
and the reproduction is not subtle. A single-column `story` file whose stories each carry a
semicolon — text, not structure — was read as semicolon-delimited and **every story was silently
cut at its first `;`**:

```
delimitador elegido por el Sniffer: ';'
original[0] : 'As a user I want A0; so that B0'
leido[0]    : 'As a user I want A0'
historias corrompidas: 30/30
```

Downstream that surfaced as `unparsable_story` on rows the user had written correctly, so a valid
file was rejected with a diagnosis pointing at the wrong thing. Short files escaped only because
the sniffer gives up on them and falls back to comma — working by luck rather than by design.

The fix reads the delimiter off the header line and drops `csv.Sniffer` entirely. The header is
authoritative here because the recognized vocabulary is fixed and every name in it (`actor`,
`feature`, `benefit`, `story`, `input`, `raw_text`) is delimiter-free: a header containing no
candidate means the file genuinely has one column, and its punctuation belongs to the story text.
That is deterministic and content-independent, where the sniffer's verdict depended on what the
stories said.

Two further defects were found while reviewing the parser's output and fixed in the same slice:

- **A partial parts header was classified as full mode.** `actor,raw_text` was read as a full-mode
  file, took the story text out of the `raw_text` column, reported `actor` as `None`, and blamed
  the stories for not parsing. A header carrying some but not all of `actor`/`feature`/`benefit`
  is now a file-level `header_unrecognized`, which names the real fault: a missing column.
- **Quoted multi-line records reported the wrong line.** `reader.line_num` read after the fact is
  the record's *last* physical line, so a record starting at line 2 with an embedded newline was
  reported as line 3 — one line past where the user should look, and colliding with the next
  row's number. The reported line is now the record's first physical line.

## Tasks

- [x] 1. CSV parser, header-mode detection, unit tests —
      `infrastructure/parsers/story_csv.py`
- [x] 2. Port `parseUserStory` to Python, canonical `raw_text` builder and the validation
      report — `domain/services/story_import.py`. The frontend mirror test that pins parity with
      `StoryForm` lands with the frontend (task 7), since it is a Vitest file; PR 1 pins the
      constant's exact value on the backend side instead.
- [x] 3. Repository: one query for the project's existing tuples, plus `save_many` in a single
      commit — `list_parts_by_project` and `save_many` on the port and its only implementation
- [ ] 4. The `import` route: membership, caps, `201`/`422` report, API tests
- [ ] 5. `ImportStoriesDialog.tsx`: file input, upload, report with lines and reasons
- [ ] 6. `importStories` in the API layer plus the store action, with the `isScopeUnchanged` guard
      and a list refresh
- [ ] 7. i18n keys in `en.json`/`es.json`, neutral Spanish, key-parity test
- [ ] 8. Docs: `docs/api.md`, the public `api.astro` page, and this record

## Two corrections in the validation core

Both were found by reviewing the module's output rather than by any failing test, and both were
reproduced before being changed:

- **A project duplicate was labelled `duplicate_in_file` with no `first_line`.**
  `RowDuplicate.reason` had a default of `duplicate_in_file`, and the project-duplicate call site
did not pass one, so the report said a row repeated *inside the upload* while carrying an
`existing_story_id` and a null `first_line` — a self-contradictory entry the UI would have had to
guess at. `reason` now has no default and both call sites state it (`duplicate` / `duplicate_in_file`).
- **Full-mode text was stored untrimmed**, while `StoryForm` stores `fullText.trim()`. That made the
stored value diverge from the form for the same story, and it made the length check measure padding:
a padded 57-character story measured 2100 and was rejected as `too_long` on `raw_text`. The text is
now trimmed once and that same string serves the emptiness check, the length check, the parse and the
stored value. The provided `raw_text` cell in parts mode is trimmed at its ends for the same reason —
internal newlines survive.

### Consequence worth knowing: a 2000-character story cannot pass in full mode

The `raw_text` limit is 2000, but the parsed parts answer to 100/300/300. A full-mode story long
enough to approach 2000 therefore always exceeds one of the part limits and is rejected. This is
correct under D8 — reject, never truncate — and it is the deliberate difference from `StoryForm`,
which silently slices the parts to their maxima on its own path. The practical cap for a full-mode row
is roughly 730 characters, and the `raw_text` limit is unreachable there. Left as is, on purpose:
padding a prompt with text the user did not write is exactly the silent change this feature refuses.

## Evidence

| Check | Command | Result |
|-------|---------|--------|
| Delimiter defect (before the fix) | `conda run -n storico python /tmp/probe_a2.py` | sniffer chose `;`; **30/30 stories truncated** at the first semicolon |
| Partial parts header (before the fix) | same probe | `actor,raw_text` -> mode `full`, `actor: None` |
| Quoted multi-line record (before the fix) | same probe | record starting at line 2 reported as line 3 |
| Project duplicate reason (before the fix) | `conda run -n storico python /tmp/probe_import.py` | `reason='duplicate_in_file'`, `first_line=None` |
| Full-mode padding (before the fix) | same probe | stored untrimmed; a padded 57-character story measured 2100 and failed `too_long` |
| Parser unit tests | `conda run -n storico python -m pytest -q -m unit tests/test_unit/test_story_csv.py` | **21 passed** (17 from the writer, 4 added for the three defects above) |
| Validation unit tests | `conda run -n storico python -m pytest -q -m unit tests/test_unit/test_story_import.py` | **27 passed** (25 from the writer, 2 replaced/extended for the two defects above) |
| Whole unit suite | `conda run -n storico python -m pytest -q -m unit` | **187 passed**, 745 deselected |
| Repository tests | `conda run -n storico python -m pytest -q tests/test_repositories/test_user_story_repo.py` | **19 passed** (13 pre-existing, 6 new) |
| Everything but integration | `conda run -n storico python -m pytest -q -m "not integration"` | **830 passed**, 109 deselected, 1 warning |
| The warning is not ours | `conda run -n storico python -m pytest -q -m "not integration" 2>&1 \| grep -B4 warnings summary` | raised by `test_custom_provider_repo.py::test_list_is_empty_for_a_fresh_workspace`, a file this feature never touches. Pre-existing, and `docs/testing.md` records that nothing gates on warnings |
| Lint | `conda run -n storico python -m ruff check src/storico/infrastructure/parsers tests/test_unit/test_story_csv.py` | All checks passed |
| Formatting | `conda run -n storico python -m ruff format --check ...` | 3 files already formatted |

## Task log

| Task | Commit | Evidence |
|------|--------|----------|
| 1 | `901bb89` | 21 unit tests, ruff clean |
| 2 | `26bfab5` | 27 unit tests, 187 unit tests whole suite, ruff clean |
| 3 | this commit | 19 repository tests, 830 tests with integration excluded, ruff clean |
