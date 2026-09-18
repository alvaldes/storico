# ODD Feature: custom-model-picker

> **Status**: done — 3 commits on `fix/custom-model-picker` (`353f1ac`,
> `9f3a3af`, `2a41fdc`); verified, NOT merged, not pushed
> **Created**: 2026-09-17
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/custom-model-picker`

## Problem

Reported after the always-visible list landed:

> "esto de los modelos descubiertos debe ser en un select porque si son muchos
> rompe la pagina"

The list added by `custom-model-list-visibility` renders every discovered model as
a wrapping button. For the reporting workspace the provider answers with **12**
entries, which the user pasted back as a wall of text:

```
Modelos descubiertos (12)
mimo-v2.5 qwen3.6 gemma4 qwen3.8-flash deepseek-v4-flash kokoro
whisper rerank qwen3-embedding glm5.3-flash flux-2-klein minimax-h3
```

A provider serving 50 or 200 models would flood the card. The list needs to be a
collapsed, scrollable dropdown — a select — not an inline block.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Primitive | base-ui **`Autocomplete`**, not the `Combobox` and not a native `<select>`. A native `<select>` is selection-only, which breaks the user-approved D3 of `custom-provider-model-discovery` (an id absent from the list, or a provider that exposes no `/models`, must stay configurable). An autocomplete is by definition "the typed text is the value, the list is a suggestion", so free text survives a dropdown. |
| D2 | Why not `Combobox` | The installed `@base-ui/react` 1.8.0 has no `allowCustomValue` anywhere (verified by grep of the whole package), and the previous feature **observed** typed text reverting on blur in the Combobox. `Autocomplete.Root` sets `selectionMode: "none"` (`autocomplete/root/AutocompleteRoot.js:80`), so there is no selected value to revert to — the revert risk is structurally absent rather than worked around. |
| D3 | No popup filtering | `filter={null}`. With the built-in filter, the popup narrows to the current value, so a workspace holding a saved model would open the list and see one entry — reintroducing the "I cannot see the models" complaint this whole thread started with. The popup is a catalogue browser; the list is always complete and scrolls. Trade-off accepted: typing does not narrow the list. |
| D4 | Item text is the id | The item's `value` is the id, and the rendered text is that same id, with the readable `name` appended as a muted suffix only when the two differ. **Corrected after verification:** the original rationale claimed the rendered text is what base-ui fills into the input. It is not — the fill goes through `stringifyValueLabel(item.value)` (`combobox/root/AriaCombobox.js:645-657`, `internals/resolveValueLabel.js`), so the `value` prop is authoritative and the rendered children never enter that path. The choice stands; the mechanism originally written here was wrong. |
| D5 | The trigger is the affordance | `Autocomplete` forces `openOnInputClick = false` and omits the prop from its public type (`AutocompleteRoot.js:24`, `AutocompleteRootProps`), so a click on the text does not open the list. A visible chevron `Autocomplete.Trigger` gives the one-click reveal the previous bug was about. |
| D6 | The datalist and the buttons are deleted | The native `<datalist>` caused the original invisibility in Firefox, and the button block caused this one. A single dropdown replaces both, so the count of suggestion mechanisms goes from three to one. |
| D7 | A separator in the entry's accessible name | An explicit `{' '}` text node sits between the id and the name suffix. JSX drops the whitespace around a line break, so the two text nodes ran together and the computed name was `deepseek-reasonerDeepSeek Reasoner`, which a screen reader would read as one word. **Honest limit:** `jsdom` computes `display: ""` for a `span`, and `dom-accessibility-api` inserts a separator around every non-inline element child, so the test suite cannot demonstrate the difference — removing the node keeps those assertions green there. It is kept as an explicit, harmless correction, not as something a test proves. |

## Non-goals

- No change to the probe, the endpoint, the backend, or the extraction path.
- No change to the known-provider `Combobox` path.
- No client-side capability filtering of the catalogue (decided and declined in
  `custom-model-list-visibility`, D5 there).
- No new persisted state: the dropdown is presentation only.

## Established facts (verified while planning, 2026-09-17)

- Installed version: `@base-ui/react@1.8.0` (`frontend/node_modules/@base-ui/react/package.json`).
- `allowCustomValue` appears **nowhere** in the package (grep across `node_modules/@base-ui/react`), and not in its `CHANGELOG.md`.
- `AriaCombobox.Props` does expose `inputValue` (line 97) as a controlled prop, so a creatable Combobox is *theoretically* reachable — rejected under D2 because the value/selection model still exists underneath.
- `Autocomplete.Root` hard-codes `openOnInputClick: false` and `selectionMode: "none"`, and `AutocompleteRootProps` **omits** `openOnInputClick`, `inputValue`, `onInputValueChange` and `itemToStringLabel`.
- `Autocomplete` re-exports the shared parts under its own names (`autocomplete/index.parts.d.ts`): `Root`, `Value`, `Trigger`, `Input` (=`ComboboxInput`), `InputGroup`, `Icon`, `Clear`, `List`, `Status`, `Portal`, `Backdrop`, `Positioner`, `Popup`, `Arrow`, `Group`, `GroupLabel`, `Item`, `Row`, `Collection`, `Empty`, `Separator`.
- `AutocompleteItem` renders a `<div>`, and accepts `value`, `index`, `disabled` and an `onClick` that fires on pointer click **and** on `Enter` for the highlighted item (`autocomplete/item/AutocompleteItem.d.ts`).
- `filter` accepts `null` to disable built-in filtering (`combobox/root/AriaCombobox.d.ts:154`).
- The repo has no `frontend/src/components/ui/autocomplete.tsx`; `ui/combobox.tsx` is the style reference for the shared parts, including the `group/combobox-content` class on the popup that `ComboboxEmpty`'s `group-data-empty/combobox-content:flex` depends on.
- `llmCustomModelsDiscovered` already exists in both locales (added by `custom-model-list-visibility`) and is reused as the trigger's accessible name instead of being left dead.
- Tests that stop being true: the native-suggestions test (`input[list]` + `<datalist>` options) and the three button tests added by `custom-model-list-visibility`. `getByLabelText('Model')` keeps working on the known-provider path, so the custom path must keep forwarding `id="llm-model"` to its input.

## Tasks

### T-001 — Frontend: the discovered models become a dropdown

- **Status**: done (commits `9f3a3af`, `2a41fdc`)
- **Files to create**: `frontend/src/components/ui/autocomplete.tsx`,
  `frontend/src/components/react/__tests__/` cases only in the existing editor suite
- **Files to modify**: `frontend/src/components/react/LLMConfigEditor.tsx`,
  `frontend/src/components/react/__tests__/LLMConfigEditor.test.tsx`
- **What**:
  - Add a minimal `ui/autocomplete.tsx` wrapping the base-ui Autocomplete parts,
    mirroring `ui/combobox.tsx`'s class strings so the field is visually identical
    to the known-provider combobox.
  - In the custom branch of the Model field, replace the `Input` + `<datalist>` +
    button block with one `Autocomplete` whose `value` is `llmConfig.model` and
    whose `onValueChange` writes the model directly (D1).
  - Item text is the model id, with the name appended when it differs (D4).
    `filter={null}` (D3). A chevron trigger is the click affordance (D5).
  - `AutocompleteEmpty` carries the existing `modelsError ?? noModelsMessage`
    text, and the input stays editable when the list is empty (D1's promise).
  - Delete the `<datalist>`, its `id` constant, and the button block (D6).
  - Keep the refresh button and the custom hint chain untouched.
- **Acceptance**: `pnpm exec tsc --noEmit` and `pnpm vitest run` pass; a saved
  model renders as the field's text; one click on the trigger lists every
  discovered model; choosing one writes its id; typing an id that is not in the
  list persists and saves; the popup is scroll-capped so a long catalogue cannot
  grow the card.
- **Allowed edit surfaces**: `frontend/src/components/ui/autocomplete.tsx`,
  `frontend/src/components/react/LLMConfigEditor.tsx`,
  `frontend/src/components/react/__tests__/LLMConfigEditor.test.tsx`

### T-002 — Verification gate

- **Status**: done
- **What**: run the repo gate and record the outcome.
- **Commands**:
  - `cd frontend && npx prettier@3.9.8 --check <every touched file>`
  - `cd frontend && pnpm exec tsc --noEmit`
  - `cd frontend && pnpm vitest run`
  - `cd frontend && pnpm run build`
- **Acceptance**: every command passes; any failure is reported as a blocker,
  never as a done task.
- **Depends on**: T-001

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| `AutocompleteItem` renders the item's text into the input on press, so a friendly name would be saved as the model | The workspace saves a display name the provider does not know, and extraction fails | D4 renders the id as the text; the name is only a suffix. A test asserts the saved value after choosing an item whose name differs from its id |
| `openOnInputClick` is false and not passable, so a click on the field reveals nothing | The original complaint returns in a new costume | D5 adds the chevron trigger; a test clicks the trigger and asserts the items appear |
| The empty-state styling depends on the popup's group class | The empty message renders invisible | Mirror `ui/combobox.tsx`'s popup class string exactly; a test asserts the empty text is present when the probe answers `[]` |
| Removing the datalist deletes a fallback some users rely on | Typing an unlisted id stops offering native suggestions | Accepted: the popup now lists everything with one click, which is strictly more discoverable than a prefix-filtered datalist |
| A new trigger button adds a second `aria-expanded` control to the settings page | Tests that query `{ expanded: false }` become ambiguous | Only the provider select and the known-provider combobox use that query today; the custom field's trigger is scoped by its accessible name |

## Evidence log

_(each completed task records its commit identity here — no row is written before
its command has actually run)_

| Task | Commit | Outcome |
|------|--------|---------|
| T-001 | `9f3a3af` | The custom model field is one base-ui `Autocomplete` backed by a new `ui/autocomplete.tsx` that mirrors `ui/combobox.tsx`'s class strings. `value`/`onValueChange` make the typed text the model; `filter={null}` keeps the popup a complete catalogue; `openOnInputClick` is turned back on because `Autocomplete.Root` defaults it to `false`. The `<datalist>`, its `CUSTOM_MODEL_LIST_ID` constant and the 31-line button block are gone. 4 obsolete tests deleted, 5 added. |
| T-001 | `2a41fdc` | The exact accessible-name assertion that replaced two regexes failed, and the failure was a real (if latent) defect: the id and the name suffix ran together as one accessible-name string. An explicit `{' '}` node separates them. Test file reflowed to satisfy prettier. |
| T-002 | — | Independent verification, twice. Final artifact: `prettier --check` exit 0, `tsc --noEmit` exit 0, `vitest run` **24 files / 255 tests passed** (baseline 253, minus 4 deleted plus 6 added), `pnpm run build` complete with the 3 known warnings from untouched `ErrorDisplay.tsx` and `zod@4.6.4`. Clean tree, 4 paths in scope, no backend file. |

## Verification findings

1. **The first gate failed, and it was the candidate's fault.** `LLMConfigEditor.test.tsx:844` was 108 characters against the repo's printWidth 100 — introduced by the very commit that added the exact-name assertion, because that edit was validated with `vitest` alone and never run through prettier. Reflowed; `prettier --check` now exits 0 on all three touched frontend files.
2. **The fill path is value-based, confirmed in source.** `stringifyAsLabel(item.value, itemToStringLabel)` with no `itemToStringValue` passed means the saved model is the item's `value` prop. The passing `writes the model id, not the displayed name` test is therefore backed by the mechanism, not only by its own assertion.
3. **Typing an unlisted id costs one extra click before Save.** `ComboboxInput.js:82` computes `focusManagerModal = !isInsidePopup || modal`, which is `true` here because the input sits outside the portal, so the popup's focus manager consumes the first outside click. This is **pre-existing on the known-provider `Combobox` path** — the test suite already carried an `{Escape}` workaround there — but it is **new for the custom field**, which used to be a plain `Input` with no popup. Accepted as parity with the sibling field; recorded because the main flow (click the field, pick an entry) closes the popup on selection and is unaffected.
4. **The name suffix is unreachable today.** `workspace_settings.py` builds `ModelInfo(id=..., name=...)` with `name == id` for both the Ollama path (line 389) and the OpenAI-compatible path (line 431) — which is the one every custom provider uses. Only Anthropic (`display_name`) and Gemini (`displayName`) return distinct names, and those render the known-provider field. So the id-vs-name distinction and D7's separator are latent in this branch: correct, tested, and currently invisible in production.
5. **A test that cannot fail is not evidence.** The three button tests deleted here included one that asserted an absence and would have passed on the pre-change code; it was kept as a guard last round and is now superseded. The two exact-name assertions added in `2a41fdc` do fail if the name suffix is removed, but they do **not** fail if only the separator space is removed (see D7) — stated so nobody reads them as more than they prove.

## Outcome

Done and independently verified on `fix/custom-model-picker`: the twelve models are
now a collapsed, scrollable dropdown instead of a block that flooded the card, the
field still accepts an id the provider never listed, and one click anywhere in the
field opens the catalogue. RDD is off in this clone, so no native review ran. Not
merged — the merge is the user's decision.

## Follow-ups (not part of this fix)

- The two-click-to-save behavior from finding 3 is parity with the known-provider
  field, but it is new for this one. If it is ever reported, the fix is not in this
  component: it comes from base-ui's focus manager for an input outside its portal.
- No test asserts the popup's scroll cap or the empty state's flex layout: `jsdom`
  has no layout engine, so both rest on the mirrored class strings.
- `npx prettier@3.9.8 --check` is not part of the repo gate (prettier is not an
  installed dependency). Every file touched here is clean, but nothing enforces it —
  which is exactly how finding 1 got through.
