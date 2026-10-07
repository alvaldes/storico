---
title: Story import from CSV
description: The two CSV shapes Storico accepts, the limits it enforces, the duplicates it skips, and every reason a file is refused.
---

Importing is a way to **create user stories** from a file instead of typing them one by one. It is not extraction: it creates the stories, and each one still has to be extracted on its own afterwards. The entry point is **Import CSV** on the stories page, which asks for a project and a file; the import adds the stories to that project.

Restating one boundary, because the names look alike: this is **story creation**, not `POST /batch`. Storico has no batch *extraction* endpoint and each extraction is one story.

## The request

`POST /api/v1/workspaces/{workspace_id}/stories/import`, sent as `multipart/form-data` with two fields: `project_id` and `file`. A successful import answers **HTTP 201** with:

| Field | Meaning |
| --- | --- |
| `created` | How many stories were written |
| `skipped` | How many rows were skipped as duplicates |
| `total_rows` | How many non-blank data rows the file held |
| `duplicates` | One entry per skipped row: its line, the reason, and the story it matched |
| `story_ids` | The ids of the stories that were created |

The project must belong to the workspace in the path; a project from another workspace is refused with HTTP 403 and `PROJECT_NOT_IN_WORKSPACE`, and an unknown one with HTTP 404 and `ENTITY_NOT_FOUND`.

## The file

| Rule | Value |
| --- | --- |
| Encoding | UTF-8; a leading byte-order mark is tolerated, anything else is `invalid_encoding` |
| Delimiter | The first line decides: comma, semicolon, or tab. If it has none of the three, the file is read as a **single column** and each line is kept whole |
| Header | Mandatory — the first line names the columns. It is matched case-insensitively and with surrounding whitespace ignored |
| Size | At most 2 MB |
| Rows | At most 1000 data rows; blank rows are skipped and do not count |
| Extra columns | Allowed and ignored |

Because a file with no delimiter anywhere in its first line is read as one column, the canonical story text — which contains commas by construction — survives intact instead of being cut at its first comma.

## The two accepted shapes

### One column of stories

The header names a single column, and each row is a complete story:

```csv
story
"As a user, I want to reset my password, so that I can regain access to my account."
```

The accepted header names are `story`, `input` and `raw_text`. Each row is parsed into its actor, feature and benefit, so it is stored the same way a story typed into the form is.

### Three columns of parts

The header names the three parts, and each row carries them separately:

```csv
actor,feature,benefit
user,reset my password,regain access to my account
```

All three are required — a header with only one or two of them is refused as `header_unrecognized`. The text the model sees is then built from the parts with a fixed template:

```text
As a(n) {actor}, I want {feature}, so that {benefit}
```

You can add a fourth column, `raw_text`, to supply that text yourself instead: when the cell is present and not blank it is used verbatim, internal line breaks included, and the template is not used for that row.

## Field limits

| Field | Maximum |
| --- | --- |
| `actor` | 100 characters |
| `feature` | 300 characters |
| `benefit` | 300 characters |
| `raw_text` | 2000 characters |

In the one-column shape the raw text is capped at 2000 characters and each part it parses into is checked against its own limit.

## One bad row refuses the whole file

An import is **all or nothing**. If any row has a problem, nothing is written and the response is HTTP 422 with the error code `IMPORT_VALIDATION_FAILED`. The dialog lists the offending lines so the file can be fixed and uploaded again.

| Reason | What it means |
| --- | --- |
| `field_count_mismatch` | The row has a different number of values than the header declares. This check runs first, because when the counts disagree the column mapping is unreliable and every per-field complaint on that row would be noise |
| `parts_look_like_a_full_story` | Under a three-column header, the cells joined together read as one complete canonical story — the tell-tale of a whole story pasted into the parts columns. An `actor` cell that already begins with "As a …" is refused for the same reason: the app renders it as `As a(n) {actor}`, so the fix is to write the actor alone |
| `missing_field` | A required cell does not exist on the row |
| `empty_field` | A required cell exists but is blank |
| `too_long` | A value exceeds the limit in the table above; the response names the field, its length and the maximum |
| `unparsable_story` | A one-column row does not match the accepted story format |

Rows are checked in that order and a row reports at most one reason.

A file can also be refused before any row is examined — the response is then HTTP 422 with `IMPORT_FILE_REJECTED`:

| Reason | What it means |
| --- | --- |
| `empty_file` | The file has no content, or only whitespace |
| `invalid_encoding` | The bytes are not valid UTF-8 |
| `header_unrecognized` | The first line names neither a full-story column nor all three parts columns |
| `too_many_rows` | More than 1000 data rows |
| `malformed_csv` | The file could not be parsed as CSV |

And a file over 2 MB is refused with HTTP 413 and `IMPORT_FILE_TOO_LARGE` before it is read.

## Duplicates are skipped, not refused

Two rows count as the same story when their trimmed `(actor, feature, benefit)` are **exactly** equal — no case folding and no whitespace normalisation. A duplicate is not an error: it is skipped and reported in `duplicates`.

- `duplicate` — the story already exists in the project, and the entry carries the existing story's id.
- `duplicate_in_file` — an earlier row of the same upload already claimed it, and the entry carries that row's line number.

Re-uploading the same file is therefore harmless: it answers HTTP 201 with `created` 0 and every row reported as skipped.

## One more caveat

Import creates stories; it does not extract tasks. Nothing in this path runs a model, and the automatic validation described on the [LLM providers](/en/docs/llm-providers) page still does not run for the extractions you start from the app afterwards.
