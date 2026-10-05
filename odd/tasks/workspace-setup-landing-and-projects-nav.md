# ODD Feature: workspace-setup-landing-and-projects-nav

> **Status**: done — T1-T4 implemented and independently verified; left uncommitted in the working tree
> **Created**: 2026-10-05
> **Workflow**: Organic Driven Development (ODD)
> **Receipt-driven development**: off in this clone.

## Problem

Two user-reported defects on the authenticated shell.

1. **The user never lands on workspace settings after a workspace is set up.** A brand-new user has
   a personal workspace auto-created by the backend at first login
   (`backend/src/storico/api/routes/auth.py` → `CreateWorkspaceUseCase`), then goes through the
   three-step `OnboardingModal`, which renames it via `PATCH /users/me/onboarding`. When onboarding
   finishes — by *Get Started* or by *Skip* — the modal merely closes and the user stays on whatever
   page they were on (normally `/dashboard`). Settings is the logical next step after a workspace is
   created, because that is where the LLM provider/credentials are configured and, with an empty
   workspace, nothing else is actionable. The create-workspace path in `team-switcher.tsx:63-74`
   already navigates to settings; onboarding is the missing half of the same rule.

2. **`Projects` renders as a collapsible even when the workspace has no projects.** In
   `app-sidebar.tsx:80-98` the `items` array is always populated because it always prepends the
   `All Projects` sub-item, so `NavMain` (`nav-main.tsx:36`) always takes the collapsible branch:
   chevron plus a nested list that holds a single duplicate of the parent link. With zero projects
   the entry should be a plain link to `/projects`; from one project up it should stay the
   collapsible it is today.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Where onboarding lands | Navigate to the current workspace settings route after `completeOnboarding` resolves, for **both** terminal actions (*Get Started* and *Skip*). Settings is the post-workspace-creation destination regardless of which way the modal is dismissed. |
| D2 | How the workspace id is resolved | Read `useWorkspaceStore.getState().currentWorkspace?.id`; when it is still null (store hydrating on a first login) `await fetchWorkspaces()` and read it again. Navigate only when an id exists and `workspaceSettingsPath(locale, id)` returns a non-null path. The helper already rejects ids that are unsafe to interpolate. |
| D3 | Router | `navigate` from `astro:transitions/client`, the same call `team-switcher.tsx` and `nav-user.tsx` already use under the app's View Transitions. |
| D4 | Flat vs collapsible trigger | `app-sidebar.tsx` passes `items` **only when `projects.length > 0`**, `undefined` otherwise. `NavMain` already renders a flat `SidebarMenuButton` link when `items` is absent; no change to `NavMain`. |
| D5 | Submenu shape with projects | Unchanged: `All Projects` plus one entry per project. No change to `nav-main.tsx`, `team-switcher.tsx`, or i18n. |

## Non-goals

- No change to the create-workspace dialog in `team-switcher.tsx`; its settings navigation already
  exists and is covered by `team-switcher.test.tsx`.
- No change to the backend onboarding endpoint or the workspace auto-creation.
- No new i18n keys — `nav.projects` and `nav.allProjects` already exist in `en.json` and `es.json`.
- No loading-state gating for the sidebar entry: with an empty `projects` slice the entry is flat,
  which is the correct render for the zero-projects state and converges to collapsible once the
  fetch lands. Adding a `loaded` flag to `projectStore` is out of scope.
- No commit is created by this task (working on `chore/issue-forms`, and delivery/commit remains the
  owner's decision).

## Established facts (verified in code)

- `frontend/src/components/react/OnboardingModal.tsx` finishes onboarding in `handleSkip` (line 82)
  and `handleComplete` (line 96); neither navigates.
- `frontend/src/components/team-switcher.tsx:72-74` already does
  `navigate(workspaceSettingsPath(locale, created.id))` after a successful create.
- `frontend/src/components/app-sidebar.tsx:88` is the unconditional `items:` array.
- `frontend/src/components/nav-main.tsx:36` branches to the collapsible only when
  `item.items && item.items.length > 0`.
- `frontend/src/lib/workspace-nav.ts` exposes `workspaceSettingsPath(locale, id)` and
  `isSafeWorkspaceId`.
- Tests live in `frontend/src/components/__tests__/` and
  `frontend/src/components/react/__tests__/`; `astro:transitions/client` is aliased to a no-op stub
  by `frontend/vitest.config.ts` and is replaced by a spy in tests that observe navigation.
- `frontend/src/stores/workspaceStore.ts` persists only `currentWorkspace`; the list is refetched per
  load, which is why the id can be null while the sidebar is still hydrating.

## Tasks

- [x] **T1 — RED**: add `frontend/src/components/__tests__/app-sidebar.test.tsx` covering the flat
  entry with zero projects and the collapsible with one project; extend
  `frontend/src/components/react/__tests__/OnboardingModal.test.tsx` with the settings-landing
  assertions for *Get Started*, *Skip*, and the late-hydration case. Observed 6 failures before the
  source edits (3× no `link` named "Projects"; 3× `navigate` call count 0).
- [x] **T2 — GREEN**: implement D1-D4 in `app-sidebar.tsx` and `OnboardingModal.tsx`; focused tests
  pass 12/12.
- [x] **T3 — Verify** (independent, `gentle-ai-verify`): `npx vitest run` 58/58 files, 672/672 tests,
  0 failed, 0 skipped; `npx tsc --noEmit` exit 0; scope check confirms only the three expected
  tracked files changed (plus the pre-existing unrelated `frontend/astro.config.mjs`).

## Evidence

- RED (before source edits): `npx vitest run src/components/__tests__/app-sidebar.test.tsx
  src/components/react/__tests__/OnboardingModal.test.tsx` → 6 failed / 6 passed.
- GREEN (after source edits): same command → 12/12 passed.
- Full suite + typecheck + scope: verified by `gentle-ai-verify` as recorded in T3.
- Commits: `eb75686` (onboarding landing, source + test) and `ebb71e7` (Projects nav shape,
  source + tests) on `chore/issue-forms`.
- Commit: none. Work was done on `chore/issue-forms` with a pre-existing dirty
  `frontend/astro.config.mjs`; committing remains the owner's decision.
- T4 evidence: `npx vitest run src/components/__tests__/app-sidebar.test.tsx` 5/5 after GREEN;
  full suite 58/58 files and 673/673 tests, `npx tsc --noEmit` exit 0, verified independently.

## T4 — collapsed sidebar must navigate, not toggle (owner follow-up 2026-10-05)

- [x] **T4** In icon/collapsed mode the `Projects` entry is still a `CollapsibleTrigger`, so
  clicking the icon toggles a submenu that CSS hides and appears to do nothing. Render the entry as
  a plain link to its own `url` whenever the sidebar is collapsed (`!isMobile && state ===
  'collapsed'` from `useSidebar()`), keeping the collapsible branch only when expanded. Applies to
  any nav item with sub-items, not just Projects. Done in `nav-main.tsx:35-38,42`; RED confirmed
  (`getByRole('link', { name: 'Projects' })` not found), GREEN 5/5, then independently re-proven
  non-vacuous by removing `&& !collapsed` in a `/tmp` copy (1 failed | 4 passed).

### Diagnostic note (2026-10-05)

The owner reported that Projects still rendered as a collapsible with "no projects created".
Measured against the dev database (Supabase, the same URL in `.env`, `backend/.env` and
`frontend/.env`): the single workspace `Angel's Workspace` holds exactly 1 project,
`Version Test`, created 2026-10-04. So the collapsible render was correct for that data, and the
remaining gap is the collapsed-mode click behaviour above. The running dev server already serves
the new `app-sidebar.tsx` (confirmed by fetching the transformed module from Vite), but the dev
log shows no page load after the 12:20 source edit — a browser reload is required to see D4.

## Follow-ups (non-blocking, from the verifier)

- `navigate(path)` is intentionally not awaited; a rejected promise from the real Astro
  `navigate` would surface as an unhandled rejection. It cannot change the onboarding outcome.
- The sidebar tests assert `data-active` (the only observable active contract on the Base UI
  button) rather than `aria-current`, which the component does not emit.

## Review workload

Two source edits plus two test files; expected well under a 400-line budget with no split needed.
