# Onboarding Flow Specification

## Purpose

First-login onboarding that guides new users through workspace setup, tool orientation, and optional LLM configuration before reaching the dashboard.

## Requirements

### Requirement: `is_first_login` flag on auth sync

`POST /api/v1/auth/sync` MUST include `is_first_login: bool` in the response body.

| Condition | `is_first_login` value |
|-----------|------------------------|
| Step (c) — new user + workspace created | `true` |
| Step (a) — returning user, existing session | `false` |
| Step (b) — returning user, new OAuth link | `false` |

`UserResponse` schema SHALL include `is_first_login: bool` as a required field.

#### Scenario: New user gets `is_first_login: true`

- GIVEN a user authenticates for the first time with Google
- WHEN `POST /api/v1/auth/sync` executes step (c)
- THEN the response contains `is_first_login: true`

#### Scenario: Returning user gets `is_first_login: false`

- GIVEN a user has completed onboarding in a previous session
- WHEN `POST /api/v1/auth/sync` executes step (a)
- THEN the response contains `is_first_login: false`

### Requirement: Onboarding completion endpoint

`PATCH /api/v1/users/me/onboarding` MUST mark the authenticated user's onboarding as completed.

- The endpoint MUST be idempotent — calling it multiple times SHALL NOT error.
- After calling the endpoint, `GET /api/v1/users/me` MUST return `is_first_login: false`.
- The endpoint SHALL accept an optional JSON body `{ "workspace_name": string }` to rename the auto-created workspace.

#### Scenario: Complete onboarding with workspace rename

- GIVEN a new user with `is_first_login: true`
- WHEN they call `PATCH /api/v1/users/me/onboarding` with `{ "workspace_name": "My Team" }`
- THEN onboarding is marked completed
- AND subsequent `GET /api/v1/users/me` returns `is_first_login: false`
- AND the workspace is renamed to "My Team"

#### Scenario: Skip onboarding (no rename)

- GIVEN a new user with `is_first_login: true`
- WHEN they call `PATCH /api/v1/users/me/onboarding` with no body
- THEN onboarding is marked completed
- AND the workspace retains its auto-created name

#### Scenario: Idempotent re-call

- GIVEN onboarding is already completed
- WHEN the same user calls `PATCH /api/v1/users/me/onboarding` again
- THEN the endpoint returns 200 OK
- AND `is_first_login` remains `false`

### Requirement: Frontend onboarding detection

The frontend MUST detect first-login state and conditionally render the onboarding modal.

- `authStore` SHALL store `isFirstLogin: boolean` from the auth sync response.
- `authStore` SHALL expose `setOnboardingDone()` that sets `isFirstLogin = false`.
- `Dashboard.tsx` MUST render `<OnboardingModal>` when `isFirstLogin === true`.
- `Dashboard.tsx` MUST NOT render `<OnboardingModal>` when `isFirstLogin === false`.

#### Scenario: Onboarding renders on first login

- GIVEN `authStore.isFirstLogin` is `true`
- WHEN the Dashboard component mounts
- THEN `<OnboardingModal>` is rendered as a modal overlay

#### Scenario: Onboarding hidden for returning users

- GIVEN `authStore.isFirstLogin` is `false`
- WHEN the Dashboard component mounts
- THEN `<OnboardingModal>` is NOT rendered

### Requirement: Onboarding modal behavior

The modal MUST be a multi-step flow with skip-at-any-point support.

| Step | Content | Behavior |
|------|---------|----------|
| 1 — Rename workspace | Text input pre-filled with auto-created workspace name | Editable; skip leaves name unchanged |
| 2 — Tutorial cards | 3 cards: What is Storico, How extraction works, Workspaces | Read-only informational; skip proceeds |
| 3 — LLM config | Provider/model selector defaulting to Ollama | Optional; skip uses defaults |
| Final | "Get Started" button | Calls `PATCH /me/onboarding`, then closes modal |

- A progress bar SHALL display the current step (1/3, 2/3, 3/3).
- Every step MUST include an "X" close button and a "Skip" link.
- Clicking "Skip" or "X" on any step SHALL call `PATCH /api/v1/users/me/onboarding` (without workspace rename) and close the modal.
- Clicking "Get Started" on the final step SHALL call `PATCH /api/v1/users/me/onboarding` with the workspace name (if changed) and close the modal.

#### Scenario: Full completion

- GIVEN a new user on step 1
- WHEN they rename the workspace, view tutorial cards, configure LLM, and click "Get Started"
- THEN `PATCH /me/onboarding` is called with `workspace_name`
- AND the modal closes
- AND subsequent dashboard visits show no modal

#### Scenario: Skip from any step

- GIVEN a new user on step 2
- WHEN they click "Skip"
- THEN `PATCH /me/onboarding` is called with no body
- AND the modal closes
- AND the workspace name is unchanged

### Requirement: Internationalization

All onboarding text MUST be available in both English and Spanish.

| Key | English (`en.json`) | Spanish (`es.json`) |
|-----|---------------------|---------------------|
| `onboarding.title` | "Welcome to Storico" | "Bienvenido a Storico" |
| `onboarding.step1.title` | "Name your workspace" | "Nombra tu espacio de trabajo" |
| `onboarding.step2.card1` | "What is Storico" | "¿Qué es Storico?" |
| `onboarding.step3.title` | "Configure your LLM" | "Configura tu LLM" |
| `onboarding.skip` | "Skip" | "Saltar" |
| `onboarding.get_started` | "Get Started" | "Comenzar" |

#### Scenario: Spanish locale shows Spanish translations

- GIVEN the user's locale is `es`
- WHEN the onboarding modal renders
- THEN all onboarding text reads from `es.json` keys
