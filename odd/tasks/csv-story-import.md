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
| D2 | Endpoint | `POST /api/v1/workspaces/{workspace_id}/stories/import`, multipart, `project_id` and `file` as form fields. Named `import` and not `batch` (see scope boundary). **Revised twice** — see the two path corrections below |
| D3 | CSV format | Auto-detected by header, case-insensitive and trimmed: `actor` + `feature` + `benefit` → parts mode (optional `raw_text` column, used verbatim when present); `story` / `input` / `raw_text` → full-story mode, parsed to parts. Any other header is a file-level error |
| D4 | Partial failure | **Errors block everything; duplicates are skipped and reported.** Every row is parsed and validated first, and a full report with line numbers comes back. With at least one error nothing is written (`created: 0`, HTTP `422`) |
| D5 | Duplicates | Skip and report, against both the project and the file itself. Importing the same file twice is idempotent: `created: 0`, every row reported as a duplicate |
| D6 | Destination project | The project selected in the UI, carried by the URL path. Reuses the existing gating in `StoriesList` (the create button is already disabled without a project) |
| D7 | Caps | 2 MB rejected at the handler, 1000 rows counted during parsing. Each cap has its own reason code, never a timeout. **Corrected**: the first version of this row said "before reading the body", which is false — see the verification finding V2 |
| D8 | Over-long text | Reject the row with `reason: "too_long"`, carrying `field`, `length` and `max`. No silent truncation, for the reason in the correction above |
| D9 | In-file duplicates | Non-blocking, consistent with D5: the second identical row is skipped and reported with `duplicate_in_file` plus the first line. **Judgment call taken by consistency — overridable by the maintainer** |
| D10 | Auto-extraction after import | **Out of scope for v1.** The endpoint contract is designed so adding it later does not change the response shape. It needs its own concurrency-limit decision and its own conversation, not a paragraph hidden here |

## The contract

```
POST /api/v1/workspaces/{workspace_id}/stories/import
Content-Type: multipart/form-data     fields: project_id (form), file (.csv)

201 — nothing to block on. Re-uploading the same file is idempotent.
{ "created": 41, "skipped": 3, "total_rows": 44,
  "duplicates": [ { "line": 19, "reason": "duplicate", "existing_story_id": "..." },
                  { "line": 31, "reason": "duplicate_in_file", "first_line": 12 } ],
  "story_ids": [ ... ] }

422 — at least one blocking error. Nothing written.
{ "detail": { "detail": "The file has rows that must be fixed.",
              "error_code": "IMPORT_VALIDATION_FAILED", "created": 0, "total_rows": 44,
    "errors": [
      { "line": 7,  "reason": "missing_field", "field": "feature" },
      { "line": 19, "reason": "too_long", "field": "benefit", "length": 340, "max": 300 },
      { "line": 23, "reason": "unparsable_story" },
      { "line": 31, "reason": "field_count_mismatch", "observed": 4, "expected": 3 },
      { "line": 40, "reason": "parts_look_like_a_full_story" } ],
    "duplicates": [ ... ] } }

413 — over the byte cap
{ "detail": { "detail": "The file is too large.",
              "error_code": "IMPORT_FILE_TOO_LARGE", "size": 3145728, "max": 2097152 } }

422 — the file itself cannot be read at all
{ "detail": { "detail": "The file could not be read.",
              "error_code": "IMPORT_FILE_REJECTED", "reason": "header_unrecognized" } }
```

Two nesting levels, both deliberate: `HTTPException(detail={...})` produces the outer `detail`, and
the inner `detail` string is the human sentence — the same shape the extraction route already uses
for `LLM_CONFIG_INCOMPLETE`. The first version of this block showed only the outer level, which is
finding V3 of the verification below; the API tests read it through one `_error_envelope` helper so
the envelope is asserted in a single place.

### The reason codes, complete

Blocking, per row, and each carries only the fields it needs:

| reason | extra fields | meaning |
|---|---|---|
| `missing_field` | `field` | the cell is absent |
| `empty_field` | `field` | the cell is present but whitespace-only |
| `too_long` | `field`, `length`, `max` | over the schema limit; never truncated |
| `unparsable_story` | `field` | a full-mode row that is not a user story |
| `field_count_mismatch` | `observed`, `expected` | the row's field count disagrees with the header |
| `parts_look_like_a_full_story` | none | the parts together read as one complete story |

Non-blocking, reported in `duplicates` with `reason` `duplicate` (plus `existing_story_id`) or
`duplicate_in_file` (plus `first_line`). File-level rejections use `IMPORT_FILE_REJECTED` with a
`reason` of `invalid_encoding`, `header_unrecognized`, `too_many_rows` or `empty_file`, and the byte
cap uses `IMPORT_FILE_TOO_LARGE` with `size` and `max`.

### Spec inconsistency found and resolved: where `duplicate_in_file` lives

The first version of this block listed `duplicate_in_file` inside `errors`, which contradicts
D9 — and D9 was chosen to agree with D5. D9 wins: **only** `missing_field`, `empty_field`,
`too_long` and `unparsable_story` block the import. Both duplicate kinds — the one already in the
project and the one repeated inside the upload — live in `duplicates` with their `reason`, and the
key that tells them apart is `reason` plus the presence of `existing_story_id` or `first_line`.

### Deviation from the promised duplicate shape

The 201 example originally showed `actor` and `feature` on each duplicate entry. They are not there.
`RowDuplicate` carries only the line, the reason and whichever identifier applies, and the user
fixing a rejected file has the file in front of them — the line number is the actionable datum, and
`existing_story_id` says which story was matched. Adding the parts would mean widening the domain
model for display sugar. Recorded as a deliberate narrowing, not an oversight.

Delimiter and encoding: decoded as UTF-8 with the BOM stripped; an invalid encoding is a
file-level error. The delimiter is read off the **header line**, and a header carrying no delimiter
means the file has one column, returned whole — see the two spec corrections below.

## Spec correction (second round): a one-column file must be read as one column

The first fix above replaced the data sniff with a header read, but kept **comma as the fallback**
when the header carried no delimiter. That fallback is wrong, and it broke the most natural shape of
this feature: the canonical story text contains commas by construction.

```
FALSIFY comma, header='story', delimiter chosen: ','
  row0 in : 'As a user, I want A0, so that B0'
  row0 out: 'As a user'                # _build_row keeps only column 0
  commas intact: False -> corrupted: 30/30
```

End to end that file is rejected with `422 IMPORT_VALIDATION_FAILED` and `unparsable_story` on every
row — the exact symptom the first fix claimed to have eliminated.

**Why the test suite missed it, which is the part worth keeping.** The suite pinned
`test_a_story_text_containing_a_semicolon_is_not_split` and nothing else. A semicolon is not the
delimiter, so that test could not fail for this reason; the canonical text carries **commas**, not
semicolons. A fix aimed at one delimiter says nothing about the others, and the test named the one
character that was already safe. The suite was green while the primary upload shape was broken.

**The fix**: when the header carries no candidate delimiter, the file has one column, and that
column is returned whole. The reader is given a delimiter that cannot occur (`\x00`), so the entire
line is a single field while CSV quoting is still honoured — a quoted row is unwrapped, including
one spanning several physical lines.

The rationale stated in the first correction ("the header is authoritative because the recognized
vocabulary is delimiter-free") was right. What was wrong was what to do with that fact: it implies
*one column*, not *comma*.

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
- [x] 4. The `import` route: membership, caps, `201`/`422` report, API tests
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

## Spec correction (third round): the import belongs under its workspace

The second correction moved the route to `POST /api/v1/stories/import`. That fixed reachability
and was still the wrong home, because it put a new feature on the **legacy** flat stories router.

Every newer scoped feature in this API is workspace-scoped — `projects_router` is
`/api/v1/workspaces/{workspace_id}/projects`, `extraction_router` is `.../extract`, and `export`
and `settings` follow — and `docs/api.md` states for extraction that "la única ruta vigente es la
workspace-scoped". The top-level `/api/v1/stories` and `/api/v1/tasks` tables in that document are
the legacy set. Reachability was the symptom; the missing workspace scope was the disease, and only
fixing the first left the second in place.

The route is now **`POST /api/v1/workspaces/{workspace_id}/stories/import`**, with `project_id` still
a multipart form field:

- `extraction_router` keeps the workspace in the path and its child resource id (`user_story_id`) in
the body, and `create_story` takes `project_id` in the payload rather than the path. Both precedents
agree on the form field.
- Membership resolves through the established `get_workspace_for_user` dependency, which defines its
own 401/403/404, instead of a hand-rolled project→workspace→member lookup.

**Containment is a separate check and is required.** Naming a workspace in the path proves the caller
belongs to it, and says nothing about the project named in the form: without the extra check a member
of workspace A could import into a project of workspace B. It mirrors the 403 containment check in
`routes/extraction.py`, and a test seeds two workspaces the caller belongs to and imports across
them.

## The comma, resolved in four layers (the fourth one refuted and corrected)

The user's question was how the comma problem gets solved. It turned out there were three separate
ways for a comma to corrupt an import, not one, and the count check that closed the second one
deliberately cannot see the third.

| # | Shape | Behaviour |
|---|-------|-----------|
| 1 | `story` header, one canonical story per line, unquoted | **Works.** The header carries no delimiter, so the file has one column and the whole line is the field. Commas, semicolons and tabs all survive. |
| 2 | Any header, properly quoted values | **Works.** CSV quoting is honoured by `csv.reader`, including a field spanning several physical lines. |
| 3 | Row field count ≠ header column count | **Refused** — `field_count_mismatch` with `observed` and `expected`. A row that cannot be mapped to columns is never partially mapped. |
| 4 | A whole story inside the parts columns | **Refused** — `parts_look_like_a_full_story`. See below. |

### Why layer 3 is not enough, which is the whole point

The canonical story contains **commas by construction**: `As a user, I want A, so that B` has exactly
two. Under a three-column header it therefore yields exactly **three** fields — the counts **agree**
and the count check is silent. The row was mapped into a plausible-looking garbage story:

```
header 'actor,feature,benefit' + row 'As a user, I want A, so that B'   (unquoted)
   before -> creates actor='As a user', feature=' I want A', benefit=' so that B'   no error
```

Nothing was reported and a story was written. Layer 4 closes it without guessing about content: in
`parts` mode the row's own fields are joined with `", "` and the result is asked to parse as a
canonical story using the module's existing `parse_user_story`. Three values that together read as one
complete story are not three parts — the row contradicts its own header. Measured against six cases,
**only the corruption is flagged**:

```
FLAG  ('As a user', ' I want A', ' so that B')        the corruption
ok    ('user', 'log in', 'access')
ok    ('admin, senior', 'export, save', 'share, collaborate')     commas inside parts
ok    ('As a user', 'log in', 'access')               needs "I want"; not flagged
ok    ('user', 'log in', 'so that users retry')       not flagged
ok    ('power user', 'I want reports', 'see data')    "As a" away from the start
```

No per-field prefix heuristics were added, and nothing constrains what a part may contain.

### Refuted: the first version of layer 4 was bypassed, and it over-refused

The second independent verification falsified this section, and the correction is recorded here
rather than quietly applied. The first version joined **only the three parts** and used
`parse_user_story`, which uses `re.search`. Two consequences, both measured:

**Bypass, silent corruption (HIGH).** Under an `actor,feature,benefit,raw_text` header — a supported
shape, since the `raw_text` column is optional — the canonical story with one extra comma yields
exactly **four** fields, so the count guard is silent; the three-cell join was
`"As a user, I want A, B"`, which has no `so that`, so it did not parse and was not flagged, and a
garbage story was written with no error at all:

```
bytes in: b'actor,feature,benefit,raw_text\nAs a user, I want A, B, so that C\n'
before -> STORED actor='As a user' feature='I want A' benefit='B' raw_text='so that C'
```

It reproduced the same way with a five-column header and with `;` as the delimiter. The four layers
were three layers plus a rule that only held for a three-column header.

**Over-refusal (MEDIUM).** Because the match was unanchored, a legitimate row was refused whenever
any part merely *quoted* a story:

```
bytes in: b"actor,feature,benefit\nuser,\"build the page that parses As a user, I want X, so that Y\",access\n"
before -> 422 parts_look_like_a_full_story
```

The precision table above was measured against six cases and none of them contained a part whose own
text was story-shaped, so it did not show this.

**The corrected rule**: join **every cell present on the row** — `actor`, `feature`, `benefit`, and
`raw_text` when it is present and not blank — and require the match **anchored at the start**
(`_STORY_PATTERN.match`, not `parse_user_story`). `parse_user_story` keeps `search` on purpose: it is
the port of the frontend parser, it asks whether a text *contains* a story, and the guard asks
whether the whole row *is* one. That difference is exactly what stops a quoted story inside a part
from being refused.

| cells | result |
|---|---|
| `('As a user', ' I want A', ' so that B')` — 3-column header | **refused** |
| `('As a user', ' I want A', ' B', ' so that C')` — 4-column header, the bypass | **refused** |
| `('As a user', ' I want A', ' B', ' so that C', ' D')` — 5-column header | **refused** |
| `('user', 'log in', 'access', '<canonical text>')` — legitimate, only when quoted | accepted |
| `('user', 'build the page that parses As a user, I want X, so that Y', 'access')` | accepted |
| `('admin, senior', 'export, save', 'share, collaborate')` | accepted |
| `('user', 'log in', 'so that users retry')` | accepted |
| `('power user', 'I want reports', 'see data')` | accepted |
| `('As a service owner', 'I want metrics', 'so that I monitor')` | **refused — intended** |

The last row stays refused deliberately and it is not a residual to fix: the app renders an actor as
`As a(n) {actor}`, so an actor carrying the story opening is malformed for this model and would be
stored as `As a(n) As a service owner`. The user's fix is to write `service owner`. The earlier
version of this section called the false-positive trade "narrow" and gave the `As a service owner`
case as its justification; that understated it, because the real over-refusal was a quoted story
inside a part, which has nothing to do with pasted prefixes.

### Defect found by the same pass: two inputs answered `500`

Neither was related to the comma, and both were pre-existing to the two corrections but introduced
with this parser at `901bb89`:

```
b"actor,feature,benefit\ruser,log in,access\r"     -> 500   (classic-Mac CR-only line endings)
b"story\n" + b"x" * 200_000 + b"\n"                -> 500   (a field past csv's 131072 limit)
```

Both are `csv.Error` escaping the parser uncaught, so a malformed upload looked like a server fault
instead of any contract status. Three changes: `newline=""` on the `StringIO`, which is `csv`'s
documented requirement and is what makes CR-only files parse at all; `csv.field_size_limit` raised
once at import to `MAX_FILE_BYTES`, so a very long field is read and then reported by the normal
length rule as `too_long` with its exact `length` and `max` rather than failing to parse; and a
`csv.Error` backstop raising `story_csv.malformed_csv`, which after the first two is unreachable from
real input and exists so no `csv` failure can ever become a 500 again. Raising the process-global
limit is bounded and deliberate: the body is already capped at the same number, and this module is the
only `csv` consumer under `src/` (checked). Both are pinned at the HTTP layer, because that is where
the 500 was observed — a parser-level assertion alone would not have caught it.

## Spec correction: the published path was unreachable, and the prefix behind it is poisoned

> **Superseded in part.** The finding below is still accurate and still matters — the prefix *is*
> poisoned, and the nested path *is* permanently 410. What is superseded is its conclusion: it moved
> the route to the flat legacy `/api/v1/stories/import`, which fixed reachability and missed that a
> new endpoint should not live on the legacy router at all. See the third correction above.

The approved contract put the route at `POST /api/v1/projects/{project_id}/stories/import`.
That path **can never be served**, and the implementation proved it rather than the review
doing so: the first full run of the API tests came back with **14 failures, every one a `410
Gone`** carrying the retirement message.

`routes/projects.py:39` declares a legacy catch-all — `@router.api_route("/{path:path}",
methods=[...], status_code=410, include_in_schema=False)` under `prefix="/api/v1/projects"` —
because non-workspace-scoped project routes were retired on purpose. `app.py` registers it at
line 169, before every real router. FastAPI matches in registration order, so the catch-all
answered first. Measured directly:

```
POST /api/v1/projects/{id}/stories/import   -> 410  {'detail': 'This endpoint has been removed. ...'}
POST /api/v1/stories/import                 -> 401  {'detail': 'Invalid or missing authentication token'}
```

The 401 is the useful half: it proves the flat path reaches the handler and fails only on auth.
Note what the 410 looked like from outside — the app started cleanly, and the route was listed in
the OpenAPI schema at the nested path it could never serve. A silent, self-describing lie.

The route moved to **`POST /api/v1/stories/import`**, with `project_id` as a multipart form field.
Three reasons, in order of weight:

1. The retired prefix *means* "gone". A live route under it contradicts the decision that put the
   catch-all there. The alternative — registering the import before the catch-all — works but makes
   correctness depend on registration order, which is the exact invisible mechanism that produced
   the 410 in the first place.
2. It needs no new router and no `app.py` registration at all: it sits on the existing
   `stories.router`, whose only other `POST` path is `/`.
3. It matches the sibling it belongs to. `create_story` is `POST /api/v1/stories/` and also takes
   `project_id` in the payload, so the project id arrives the same way it always has. D6 is
   untouched: the project still comes from the selector in the UI; only its position in the request
   changed.

The nested path is not shadowed "for now" — it is permanently retired, so no future route should
be placed under `/api/v1/projects/...`. That is recorded as a follow-up below rather than fixed
here: reordering the retirement's registration is its own change, with its own justification.

## Four defects found in the first draft of the API tests

The writer produced a solid file and then stopped correctly when every request 410'd. Reviewing it
found four defects of its own, all repaired before the suite went green:

| Defect | Effect | Fix |
|---|---|---|
| Path pointed at the unreachable nested URL | every test 410 | flat path plus `project_id` as form data |
| A local `canonical_text` retyped the sentence as `As a {actor}, ...` | the parts-mode assertion expected the wrong prompt text | the helper now formats `CANONICAL_RAW_TEXT_TEMPLATE` imported from the domain module, so a test-side copy cannot drift from the contract again |
| `seed_workspace(stories=1)` seeds `use seeded feature 0`, the test looked for `1` | the "existing story is a duplicate" test would not have exercised a duplicate | corrected to `0` |
| `assert not data["errors"]` on a 201 body | `KeyError`: the success shape has no `errors` key at all | `assert "errors" not in data`, which also pins that only the blocked path carries errors |

Separately, the tests initially read `error_code` off the top level while the route nests the typed
payload under `detail` — the shape this record published, and the one the extraction route already
uses for `LLM_CONFIG_INCOMPLETE`. The route was right and the tests were wrong; a single
`_error_envelope` helper now unwraps it, so the envelope is asserted in one place.

## The route introduced two fresh deprecation warnings, and fixed them

The first run of the API tests emitted `StarletteDeprecationWarning` for
`HTTP_422_UNPROCESSABLE_ENTITY` and `HTTP_413_REQUEST_ENTITY_TOO_LARGE`. A grep over `src/` showed
the three usages were **all new, all in this route** — the rest of the codebase never used those
constants. Renamed to `HTTP_422_UNPROCESSABLE_CONTENT` and `HTTP_413_CONTENT_TOO_LARGE`, and the
warnings are gone. Worth recording because the repo's own `docs/testing.md` notes that nothing gates
on warnings, so a new one would have sat there quietly.

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
| Import API tests | `conda run -n storico python -m pytest -q tests/test_api/test_stories_import.py` | **14 passed**, no warnings after the status-constant rename |
| Everything but integration, after | `conda run -n storico python -m pytest -q -m "not integration"` | **844 passed** (+14), 109 deselected, 2 warnings |
| Everything but integration, after the verification fixes | `conda run -n storico python -m pytest -q -m "not integration"` | **848 passed** (+4), 109 deselected, 1 warning |
| Parser tests after the single-column fix | `conda run -n storico python -m pytest -q -m unit tests/test_unit/test_story_csv.py` | **24 passed** (21 from before, 3 added for the comma, quoted and multi-line cases) |
| Mutation check, V2 | delete the `file.size` guard, re-run | `test_an_oversized_upload_is_refused_without_being_read` **fails**; restored and green |
| Parser and validation units, after the structural guards | `conda run -n storico python -m pytest -q -m unit tests/test_unit/test_story_csv.py tests/test_unit/test_story_import.py` | **69 collected**, 69 passed — the earlier `60` in this table counted test *functions*, not parametrized cases |
| Import API tests, after the workspace scoping | `conda run -n storico python -m pytest -q tests/test_api/test_stories_import.py` | **19 passed** |
| Everything but integration, after the second verification | `conda run -n storico python -m pytest -q -m "not integration"` | **885 passed**, 109 deselected |
| Parser and validation units, final | `--collect-only -q` filtered by `::` | **82 collected** |
| Import API tests, final | `--collect-only -q` filtered by `::` | **21 collected** |
| Mutations, second round | delete `newline=""` and the `field_size_limit` call, re-run the API tests | **both new `TestImportHostileInput` tests fail**; restored and green at 21 |
| Everything but integration, final | `conda run -n storico python -m pytest -q -m "not integration"` | **870 passed**, 109 deselected, 2 warnings |
| The route really moved | `POST /api/v1/workspaces/{id}/stories/import` unauthenticated | **401** — the scoped path is served. `POST /api/v1/stories/import` now answers **405**: the flat registration is gone |
| The corruption is dead on the wire | multipart POST of `story\nAs a user, I want A, so that B\n` | **201, `created: 1`** — the natural shape imports intact |
| | multipart POST of `actor,feature,benefit\nAs a user, I want A, so that B\n` | **422** — `{"line": 2, "reason": "parts_look_like_a_full_story"}`, `created: 0` |
| | multipart POST of `actor,feature,benefit\nAs a user, I want A, B, so that C\n` | **422** — `{"line": 2, "reason": "field_count_mismatch", "observed": 4, "expected": 3}`, `created: 0` |
| Mutation check, the project 404 | delete the `project is None` branch, re-run the API tests | `test_an_unknown_project_in_a_known_workspace_gets_404` **fails**; restored and green at 19 |
| Lint and format, whole tree | `conda run -n storico python -m ruff check src tests` and `ruff format --check src tests` | All checks passed; 244 files already formatted |
| The warning is not ours | `conda run -n storico python -m pytest -q -m "not integration" 2>&1 \| grep -B4 warnings summary` | raised by `test_custom_provider_repo.py::test_list_is_empty_for_a_fresh_workspace`, a file this feature never touches. Pre-existing, and `docs/testing.md` records that nothing gates on warnings |
| Lint | `conda run -n storico python -m ruff check src/storico/infrastructure/parsers tests/test_unit/test_story_csv.py` | All checks passed |
| Formatting | `conda run -n storico python -m ruff format --check ...` | 3 files already formatted |

## Follow-ups this surfaced, recorded rather than bundled

1. **`/api/v1/projects/...` is a poisoned prefix.** The legacy catch-all on `projects.router` is
   registered before every real router, so any future live route under that prefix is silently
   answered `410 Gone` — while still appearing in the OpenAPI schema. Nothing is broken today
   (the only route there is the retirement itself), which is exactly why it is easy to step on.
   The fix is to register the catch-all last, or to keep every real route off the prefix. It is a
   change to a deliberate retirement, so it deserves its own slice and its own test.
2. **The two `RuntimeWarning: coroutine 'Connection._cancel' was never awaited` warnings are
   pre-existing**, both raised by `tests/test_repositories/test_custom_provider_repo.py`, a file
   this feature never touches. They are the same aiosqlite teardown artefact attributed to
different tests across runs. `docs/testing.md` records that nothing gates on warnings.
3. **An actor carrying the story opening is refused on purpose.** `actor='As a service owner'`,
   `feature='I want metrics'`, `benefit='so that I monitor'` is refused as
   `parts_look_like_a_full_story`, and it stays that way. Three cells that read as the three clauses
   of a story are indistinguishable from a story the header split, and the app renders an actor as
   `As a(n) {actor}`, so this value would be stored as `As a(n) As a service owner`. The user's fix is
   to write `service owner`. Recorded so the behaviour is not mistaken for a bug.
4. **A header with a trailing column whose rows omit it is refused.** Header `…,notes` with rows
   ending `…,` is fine, but rows that omit the trailing comma answer `field_count_mismatch`
   (`observed 3, expected 4`). Kept deliberately: the header declares four columns and the row has
   three, the error names both numbers, and the remedy is one character. Tolerating it would mean
   inventing a rule that trailing missing columns are empty, which is the kind of silent
   interpretation the rest of this feature refuses.

## First independent verification (read-only) over `901bb89..2e2a8d4`

The native review did not run: the user-owned switch is effectively **off** — the CLI reports
`global: on`, `clone-local: off`, and the effective mode is `off (decided by clone_local)`. Following
this repository's own precedent in `rich-store-errors.md`, an independent read-only verification ran
instead, because this record was written by the same session that wrote the code and is therefore the
least trustworthy source about it. Whether that is an adequate substitute for the native review is
the maintainer's call, not this record's.

It was worth it. Six claims were confirmed, four findings landed, and **two of them were real defects
plus a false claim in this record**.

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| V1 | **high** | A one-column `story` file with unquoted commas was split at the first comma on **30/30 rows**, and the whole file was then rejected as `unparsable_story`. The canonical story format contains commas, so the primary upload shape was broken. The suite missed it because the only delimiter test used semicolons. | **Fixed** — the header-with-no-delimiter case is now a genuine single-column read via a `\x00` sentinel; three tests added, including the comma case that was missing. Reproduced fixed at 30/30 intact. |
| V2 | medium | **D7's claim was false.** The handler read the full 3,145,750-byte upload *before* rejecting it, and the 413 body's own `size` field proves the read happened. Starlette's multipart parser has already consumed the body before the handler runs, so "validated before reading the body" could not be true. | **Fixed both ways** — `file.size` is now checked first, so an oversized upload is refused without a second copy into this process, and the claim is corrected in D7, the route comment and the contract. A test patches `UploadFile.read` to explode and asserts the 413 still happens; **mutation-verified**: deleting the `file.size` check fails that test. |
| V3 | low | The 422/413 envelopes carry an extra inner `"detail"` string that this record's contract examples do not show: `{"detail": {"detail": "...", "error_code": ...}}`. | **Corrected in the contract below.** The nesting is intentional and matches the extraction route's existing `LLM_CONFIG_INCOMPLETE` shape, and the API tests read it through one `_error_envelope` helper. |
| V4 | low | The Evidence table attributed both `Connection._cancel` warnings to `test_custom_provider_repo.py::test_list_is_empty_for_a_fresh_workspace`. The verifier's runs attributed them to two *different* tests in that file, and running that file alone produced **zero** warnings. `docs/testing.md` even claims the attributed test is stable. | **Corrected**: the attribution is not reproducible per test; what holds is that both warnings come from that untouched file and that nothing gates on warnings. |

Confirmed without correction: prompt-text parity between the backend template and `StoryForm.tsx`
(verified by executing the real TypeScript expression through Node, not by eye); errors blocking with
the database checked directly; `duplicate` never reaching `errors`; one statement for
`list_parts_by_project`, one statement and one commit for `save_many`, and no input found that
partially writes; the flat path reachable and the nested one permanently 410; line numbers correct
across quoted multi-line fields, embedded blank lines, CRLF and a missing trailing newline; the field
limits equal to the Pydantic schema's; and no `infrastructure` import in the domain module (confirmed
by AST, which is stronger than the module's own substring test).

Two residual risks it surfaced, acknowledged rather than fixed: the duplicate rule is
application-level, so two concurrent imports can still race into duplicates (a race, not a partial
write — and pre-existing, since there is no `UNIQUE` constraint on those columns); and `save_many`
returns the input entities, which is only correct while `UserStory.id` is pre-generated by
`default_factory=uuid7`.

## Second independent verification (read-only) over `a38f18f..HEAD`

Run for the same reason as the first, and it paid the same way. Three findings, two of them defects
in code that the first pass had already blessed, and one of them a contradiction of this record's own
central claim.

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| W1 | **high** | The split-story guard was bypassed on any parts header with **four or more columns**: the four-field story matched the header count by coincidence, the three-cell join had no `so that`, and a garbage story was written with no error. | **Fixed** — the guard joins every cell present on the row, `raw_text` included, and anchors the match. Three refused cases and six accepted ones now pin it. |
| W2 | medium | The same guard **over-refused** a legitimate row whose part merely quoted a story, because the match was unanchored. | **Fixed** by the same anchoring. The precision claim above was rewritten: the earlier "narrow trade" framing was wrong about which case was at risk. |
| W3 | medium | **Two inputs returned `500` instead of any contract status**: a classic-Mac CR-only file, and any field past `csv`'s 131072-character limit. | **Fixed** — `newline=""`, the field-size limit raised to the byte cap, and a `csv.Error` backstop. Pinned at the HTTP layer with two tests, **mutation-verified**: reverting the two changes fails exactly those two. |

Also confirmed without correction: the route move in full (13 request shapes covering membership, containment in both directions, unknown workspace, unknown project, and auth), both structural guards firing **end to end** rather than only from unit tests with the database checked directly, layer 3 not misfiring on quoted parts files, single-column files, or trailing empty columns, and eleven other hostile shapes — `\r\n`, BOM, doubled quotes, mixed quoting, mid-field quotes, delimiters inside quoted values, NUL bytes — all intact with no silent corruption found.

One number was refuted and corrected: this record said `60` unit tests where pytest collects **69**, because `60` counted test functions and not parametrized cases. The warning count also differs between runs (1 vs 2), which the first pass's V4 already recorded as unstable attribution.

The verifier also reported a tooling trap worth keeping: `conda run … python - <<'PY'` **silently discards stdin**, so a heredoc probe is a no-op that looks like a pass. Its first mutation attempt was lost that way and redone with script files. The probes in this record's evidence tables are all file-based (`/tmp/probe_*.py`) and therefore reproducible, but a heredoc probe must be written to a file first or it will report nothing and look fine — this session hit the same wall earlier and worked around it the same way without realising what it was.

## Task log

| Task | Commit | Evidence |
|------|--------|----------|
| 1 | `901bb89` | 21 unit tests, ruff clean |
| 2 | `26bfab5` | 27 unit tests, 187 unit tests whole suite, ruff clean |
| 3 | `3f55d07` | 19 repository tests, 830 tests with integration excluded, ruff clean |
| 4 | `288f855` | 14 import API tests, 844 tests with integration excluded, ruff clean |
| verification fixes | `a38f18f` | 848 tests with integration excluded, 24 parser tests, 15 API tests, ruff clean, mutation-verified |
| comma guards | `f67896c` | 866 tests with integration excluded, 60 unit tests across the parser and the domain |
| workspace scoping | `446cf2e` | 870 tests with integration excluded, 19 API tests, mutation-verified |
| second verification fixes | `f928568` | 885 tests with integration excluded, 82 unit + 21 API tests, mutation-verified |
