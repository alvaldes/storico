# Tooltips on the board's context chips, and the same treatment in the selects

> Increment of the `versioning-visibility` branch, 2026-10-08. Requested by the owner right after the
> card chips landed: hover must reveal the full project name, and the same for the story — on the
> card **and** in the cascade's selects.

## Problem

The chips truncate and the selects do not follow the card's treatment.

- The card's chips carry a native `title` attribute, which is a tooltip the browser shows late, looks
  nothing like the app, and cannot be styled. The owner asked for a real one.
- The story chip is a short id, so hovering it is currently the only way to learn *which* story it
  is — and that hover says nothing but the id.
- The cascade's selects are still plain text: no icon, no truncation, no tooltip. Three surfaces now
  name the same two things (project, story) and they agree by accident rather than by construction.

## Decisions

| #  | Decision | Choice |
|----|----------|--------|
| D16 | What a story looks like in the select | **Owner's choice (2026-10-08): the human label** — `${actor}: ${feature}` with the icon — not the short id. The owner took that option knowing its stated cost: the select and the card then name one story differently. The select must stay usable for *choosing*, which a list of uuid prefixes is not. |
| D17 | What the tooltips say | Project: the **full name**. Story: the story's **full sentence** (`raw_text`, the `As a …, I want …, so that …` the story list already shows). Both on both surfaces. |
| D18 | Which tooltip mechanism | The repo's `Tooltip` (Base UI) — this is its first real use, and it replaces the card chips' native `title` so hovering does not raise two tooltips. Inside the select's **listbox** the options keep a native `title` instead: a `Tooltip` per option fights the listbox's focus and keyboard navigation, and the listbox is not a place to add a second interactive layer. The **trigger** gets the real tooltip. |
| D19 | Where the card's tooltip text comes from | **The backend.** The story's sentence is not on a task and the frontend cannot resolve it for an unfiltered board — the same reason the project name needed a projection. The batched read added for the project label gains the story's `raw_text`: one more column in the same statement, no second query, no extra request. |
| D20 | The row order, after the owner's polish | **project → story → version → labels.** The owner moved the labels last, so the three context chips lead and the task's own attributes trail. The spec and the previous increment's documents still say labels-before-version and must follow. |
| D21 | Truncation in the select | The card caps the project name at 12 characters (`shortProjectTitle`'s default, the owner's). A select option row is far wider than a card chip, so the options pass a larger cap through the same parameter — that is what the parameter is for. Truncating a dropdown row to 12 characters would make choosing impossible without hovering every option, which is the failure this increment exists to remove. |

## Non-goals

- No change to the select's *behaviour*: the cascade, the resolution to one scope, the loaders and
  the empty states stay exactly as they are.
- No tooltip on the version chip: `v{n}` is complete, and a tooltip that repeats its content is noise.
- No new i18n key: a project name, a short id and a story's sentence are data.
- No change to `shortUUID`.

## Tasks

- [x] **WU16 — The story's sentence on the task read (backend)** → `a8a592f`: the batched read that resolves the
  project label also returns the story's `raw_text`; `TaskResponse` gains it; projected on every
  construction site; tests including the one-statement pin; API-reference drift test.
- [x] **WU17 — Tooltips and the selects (frontend)** → `149acbf`: one shared source for the icons, the labels and
  the tooltip text; the card chips switch from `title` to the real tooltip; the three selects adopt
  the treatment (icon, truncated label, tooltip), with the listbox options using a native `title`.
- [x] **WU18 — Spec and docs** → the spec commit below plus this document's closing commit: the order correction (D20) and the tooltip requirement in
  `openspec/specs/kanban-board/spec.md`, the same correction in the two feature documents, closure.

## Verified facts (with evidence)

| Fact | Evidence |
|------|----------|
| A real tooltip component exists and is unused | `frontend/src/components/ui/tooltip.tsx` (Base UI `@base-ui/react/tooltip`, with `TooltipProvider`/`Trigger`/`Content`); zero imports outside `components/ui` |
| The story's sentence is already available to the select | `listStories` returns full `UserStory` rows, whose `rawText` the story list renders; the board keeps them in `storyOptions` |
| The story's sentence is **not** available to the card | `TaskResponse` carries only `user_story_id`; the frontend has no story map for an unfiltered board |
| The owner's polish is committed and its test is aligned | `0fa72d3` — icons on both chips, labels last, `shortProjectTitle`, and the board's order pin updated to match |

## Limits and follow-ups

- **Two truncation rules now live on one chip**: `shortProjectTitle`'s character cap and the existing
  `max-w` + CSS ellipsis. The character cap can cut a name that would have fit and cannot adapt to
  the column width; the CSS bound is what protects the row. Both are kept because the owner added the
  helper deliberately, and the tooltip is what makes the visible loss harmless. Unifying them is a
  small follow-up, and the case for it is that a name is now reachable on hover either way.
- **A tooltip inside a draggable card is a hover target that moves under the pointer.** The tooltip
  must not open while the card is being dragged, or the drag preview carries a popup with it.

## Closure

Branch `feat/versioning-visibility`, on top of the card-context increment's four commits.

| Commit | Unit |
|--------|------|
| `a8a592f` | WU16 — the story's sentence joins the batched read |
| `149acbf` | WU17 — real tooltips on the chips, the shared treatment, the select rows |
| `ed4e5c2` | WU18 — the requirement rewritten for both surfaces |

Gates, run by the orchestrator on the full tree: backend `ruff check` clean, `ruff format --check`
clean, `python -m pytest -q` **1340 passed, 45 skipped**; frontend `pnpm exec tsc --noEmit` exit 0 and
`npm test` **77 files / 888 tests**.

### Verified in the browser

ego-browser, `/en/kanban`, against the dev stack — and the dev workspace turned out to have exactly
the data this needed: the project had been renamed **"Version Test LongTitle"**, 22 characters, long
enough to exercise the card's 12-character cap.

- Hovering the card's project chip, which renders `Version Test...`, shows **`Version Test LongTitle`**.
- Hovering the card's story chip, which renders `01a10dee`, shows the story's full sentence:
  `As a UI designer, I want to redesign the Resources page, so that it matches the new Broker…` —
  which is the new backend field arriving end to end.
- The project select's rows show the folder icon plus the name truncated at the wider cap, and carry
  the full name as a native `title`; the story select's row shows
  `UI designer: to redesign the Resources page` with the fingerprint icon and the sentence as its
  `title`. "All …" rows carry no icon, as designed.
- The project's trigger hover raises the real tooltip with the full name.
- **The drag suppression works**: with the chip tooltip open, starting a real drag (`You have lifted
  an item in position 1`) closes it — no popup travels with the pointer. Dropping the card back in
  its own column is a no-op, so that check wrote nothing.

### Reviewer's corrections on top of the workers

- **A coupling defect in the batched read.** It dropped the whole row when `raw_text` was falsy, so a
  story without a sentence would also have lost its project label — the card's project chip and its
  tooltip gone for an unrelated reason. `raw_text` has no `min_length` on the story schemas, so the
  case is reachable. The three values are independent facts; only the text degrades now, and the new
  pin fails with a `KeyError` against the old rule.
- **The treatment moved out of `utils.ts`.** It had landed in the module 41 other files import for
  `cn()`, carrying an icon library and per-surface truncation caps. It lives in
  `lib/context-treatment.ts` now.
- **`StoryCardContext` is exported from the ports package**, where its sibling read model already
  lives.

### Limits and follow-ups

- **The drag suppression has no test.** jsdom cannot drive a `hello-pangea` drag, so this behaviour is
  verified in the browser only, and a future change to the chip markup could break it silently. The
  same is true of every tooltip's *positioning*: the tests assert content and the disabled state, not
  where the popup lands.
- **The story label in the select has no cap while the project name does.** An asymmetry the
  implementer chose: `actor: feature` is a sentence-like string, and cutting it at a character count
  loses the part that distinguishes one story from another. The trigger clamps visually
  (`line-clamp-1`), but an option row with a very long feature widens the popup.
- **A tooltip is unreachable on touch.** The owner asked for hover, and hover is what this delivers;
  the chip's text and its accessible name are the only content a touch user gets, which is unchanged
  from before this increment.
- **`TooltipTrigger` overwrites the wrapped element's `data-slot`** with its own, so the chips are
  now identified in tests by `[data-base-ui-tooltip-trigger]` rather than by the Badge's slot. It is
  Base UI's render merge doing it, not this code, and it is worth knowing before someone "fixes" the
  assertion.
