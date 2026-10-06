---
title: Export
description: Download your workspace's tasks as JSON or Markdown.
---

## JSON and Markdown export

Export your tasks to JSON or Markdown with one click. Compatible with your existing workflow.

Open the export page, select a workspace, choose **JSON** or **Markdown**, and click **Download**. The backend returns the file as a download: JSON as an array of tasks, Markdown with one section per story. An empty workspace downloads a valid JSON array (`[]`) or a Markdown document with only the `# Tasks Export` heading.

These are the only two formats available — CSV and XML are not supported. Any other format value is refused with HTTP 400 and the error code `UNSUPPORTED_EXPORT_FORMAT`.

## The JSON format

The JSON export is a pretty-printed array of task objects, one per exported task, served as `application/json`. Each object carries exactly these fields:

| Field | Meaning |
| --- | --- |
| `id` | The task's identifier |
| `user_story_id` | The story the task belongs to |
| `title` | The task's title |
| `description` | The task's description |
| `status` | The task's Kanban state |
| `priority` | The task's priority |
| `labels` | The task's labels |
| `dependencies` | The task's dependencies |
| `created_at` | When the task was created |
| `updated_at` | When the task was last updated |

## The Markdown format

The Markdown export, served as `text/markdown`, starts with a `# Tasks Export` heading and has one `## {story}` section per story, where `{story}` is the story's raw text — or `Untitled story` when it has none. Inside a section, every task is one bullet built as `- **{title}** — {description}`, with the task's labels appended as `#label` markers and its dependencies appended as `→ {resolved title}`. A dependency resolves to the referenced task's title and falls back to the raw reference when no title matches.

## The download

The response carries a `Content-Disposition: attachment` header, so the browser downloads the file instead of rendering it: `tasks-export-{workspace_id}.json` for JSON and `tasks-export-{workspace_id}.md` for Markdown.

## What gets exported

Only tasks that belong to a **completed** extraction run are exported: a run that is still pending, or that failed, contributes nothing to the file. Of a story's completed runs, only the highest-numbered one is included — its **current** version, the one the story page's version selector marks as current. Tasks produced by superseded versions never reach the file. The export always takes the current version: picking another one in the story page does not change what a workspace export contains.
