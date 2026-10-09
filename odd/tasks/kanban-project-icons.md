# The project's own icon on the board's context chips

> Increment of the `versioning-visibility` branch, 2026-10-08. Owner's request: use each project's
> own icon instead of always drawing the same `FolderKanban`.

## Problem

The board draws the same folder for every project, while the rest of the app draws each project's
chosen icon: `ProjectDetail` and `ProjectsList` both render `<IconDisplay name={project.icon} />`, and
`ProjectForm` seeds new projects with `'folder-kanban'`. So the board is the one surface where a
project's identity is flattened, and the icon that the picker let the owner choose is ignored exactly
where several projects share one column set.

## Decisions

| #  | Decision | Choice |
|----|----------|--------|
| D22 | Which icon the chips and rows use | The project's **own** icon when it has one, through the same `IconDisplay` the project pages use, and `FolderKanban` when it does not — which is the app's own default for a project without an icon (`ProjectForm` seeds `'folder-kanban'`), so the fallback is not a second opinion. The story keeps the fingerprint: stories have no icon. |
| D23 | How the treatment carries an icon | As a **name plus a fallback component**, rendered by `IconDisplay`, rather than as a resolved component. Two reasons: the project's icon is data (a kebab-case name from the picker), and the story's is a fixed component that the shared icon map does not contain — `'fingerprint'` is absent from `ICONS` while `'folder-kanban'` is present, so a purely name-based treatment would render the wrong fallback for the story. One renderer, one definition, no entry added to the picker's icon map for an icon nobody can pick. |
| D24 | Where the card's copy of the icon comes from | **The backend, in the batched read that already resolves the project label.** The board does hold the workspace's projects, so a store lookup was the smaller path, and it is not taken: `fetchProjects` is capped at 100 rows, so a larger workspace would silently draw the fallback for reasons nobody could see, and the card would depend on a list it does not own. One more column of a statement that already runs, the same precedent D14 and D19 set. The project **select** keeps using the icon name it already has on the project it lists: same treatment, data at hand. |

## Non-goals

- No new endpoint and no change to what the select lists or how it filters.
- No icon for the story chip: stories carry actor, feature and benefit, and no icon column exists.
- No change to the app's icon picker or its catalogue.
- No change to the version chip.

## Tasks

- [x] **WU19 — The project's icon on the task read (backend)** → `efb0639`: the batched story → project read also
  returns `project_icon`; `TaskResponse` gains it; projected on every construction site; the
  statement-count pins updated; API-reference drift test run.
- [x] **WU20 — Data-driven icons in the treatment (frontend)** → `996dd40`: `ContextTreatment` carries the icon
  name and the fallback and both surfaces render `IconDisplay`; `Task`/`mapTaskItem` carry
  `projectIcon`; the project select passes the icon of the project it lists; tests for a project with
  an icon, one without, and the story's fingerprint.
- [x] **WU21 — Spec and closure** → `780f004` plus this document's closing commit: the requirement says the chips and rows use the project's own icon
  with the app's default as fallback; closure with the browser evidence.

## Verified facts (with evidence)

| Fact | Evidence |
|------|----------|
| Projects store an icon | `ProjectModel.icon: String(100) \| None` (`database/models/project.py`); `Project.icon?: string \| null` in `frontend/src/types/project.ts` |
| The app already renders it, with a fallback | `IconDisplay` (`ui/icon-display.tsx`): `name` plus an optional `fallback`, defaulting to `FolderKanban`; used by `ProjectDetail.tsx:95` and `ProjectsList.tsx:175` |
| The default is the same folder the board hardcodes | `ProjectForm.tsx:47`: `useState(initialData?.icon ?? 'folder-kanban')`; and `'folder-kanban'` is in `IconDisplay`'s private map |
| `'fingerprint'` is **not** in that map | The map has `'folder-kanban'` and no fingerprint entry, so a name-only treatment would fall back to a folder for the story |
| The card cannot get the icon from the store safely | `fetchProjects` requests `page=1&size=100`, so a workspace past 100 projects would render the fallback with nothing to explain it |

## Limits and follow-ups

- **Two sources for one icon.** The card's comes from the task read and the select's from the project
  row it lists; they can disagree only if a project is renamed or re-iconed between the two reads,
  which is the same staleness every projection in this feature already accepts.
- **`IconDisplay` resolves names from a private map**, so a project icon saved under a name the map
  does not know draws the fallback silently. That is the app's existing behaviour everywhere else and
  is not changed here; it is stated because this increment makes the board depend on it too.

## Closure

Branch `feat/versioning-visibility`, on top of the tooltip increment's commits.

| Commit | Unit |
|--------|------|
| `efb0639` | WU19 — the project's icon joins the batched read |
| `996dd40` | WU20 — the treatment carries a name plus a fallback; both surfaces render it |
| `780f004` | WU21 — the requirement rewritten |

Gates, run by the orchestrator on the full tree: backend `ruff check` clean, `ruff format --check`
clean, `python -m pytest -q` **1342 passed, 45 skipped**; frontend `pnpm exec tsc --noEmit` exit 0 and
`npm test` **77 files / 894 tests**.

### Verified in the browser, by changing the data

The dev workspace's only project stores `folder-kanban`, which is also the fallback — so a passing
screenshot would have proved nothing. The check therefore moved the data:

- the card drew `lucide-folder-kanban` with the project's stored icon `folder-kanban`;
- setting the project's icon to `rocket` through the API and reloading made the card draw
  **`lucide-rocket`** — the icon can only have come from the payload, because nothing in the
  component mentions that name;
- restoring `folder-kanban` put the card back to the folder.

The wire agrees with the column: `project_icon` on the task read equals the project's own `icon`, and
both surfaces read it through the same `IconDisplay`, so their agreement is structural rather than a
second observation. The project's icon was restored to its original value, verified by reading it
back.

### Reviewer's corrections on top of the workers

- **A type that lied about its own values.** `StoryCardContext.story_raw_text` was annotated `str`
  while the mapping already answered `None` for an empty sentence, and nothing here catches it: this
  repo type-checks the frontend and lints the backend but does not run mypy. Fixed by hand, in
  `efb0639`, with the reason next to the annotation.
- The independence rule the previous increment had to be corrected for was **not** re-broken: the
  icon is nullable while the name is not, only the icon degrades, and both the repository and the API
  pin it.

### Limits and follow-ups

- The two limits recorded above stand and were not softened by the verification: one icon read twice
  can disagree through staleness, and an icon name the renderer does not know falls back silently.
- **The verification needed a data change to be meaningful**, and that is worth remembering for any
  future "use the value from the database" change: when the stored value equals the fallback, a green
  screenshot is indistinguishable from a hardcoded one.
