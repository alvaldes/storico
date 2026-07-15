# Proposal: First Login Onboarding Flow

## Intent

New users sign up (auth step c), get an auto-created workspace, but land on a generic dashboard with zero onboarding. No way to personalize workspace name, learn about the tool, or configure the LLM before first use. This change adds a guided first-login flow.

## Scope

### In Scope
- Backend: `is_first_login: bool` on `UserResponse` — true only for brand-new users (step c)
- Frontend treat `is_first_login` in `authStore`, render `<OnboardingModal>` on dashboard
- Modal: 3 steps — rename workspace, tutorial cards, optional LLM config
- Modal skippable at any point (X button / "Skip" link)
- i18n keys for both `en.json` and `es.json`

### Out of Scope
- Full product tour / interactive walkthrough
- Email verification
- User preferences (separate feature)
- Tutorial progress across sessions

## Capabilities

### New Capabilities
- `onboarding-flow`: First-login onboarding modal with workspace rename, tutorial cards, and optional LLM config

### Modified Capabilities
- None

## Approach

**Hybrid backend+frontend.** Backend keeps auto-creating workspace (backward compatible). `is_first_login=true` on step (c) response only. Frontend stores flag in `authStore`, mounts `<OnboardingModal>` on dashboard when true. Modal is multi-step with skip support. After completion or skip, `PATCH /api/v1/auth/me/onboarding` sets `is_first_login=false` server-side.

## Affected Areas

| Area | Impact |
|------|--------|
| `schemas/user.py` — `UserResponse` | Add `is_first_login: bool` |
| `routes/auth.py` — step (c) response | Set `is_first_login=True` |
| `routes/user.py` — `PATCH /me/onboarding` | New endpoint |
| `authStore.ts` — `AuthUser` + action | Add `isFirstLogin`, `setOnboardingDone` |
| `Dashboard.tsx` | Conditionally render `<OnboardingModal>` |
| `OnboardingModal.tsx` | New — 3-step modal component |
| `i18n/en.json`, `i18n/es.json` | Add `onboarding.*` keys |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| User skips without LLM config | Medium | Step is optional; default to Ollama (zero config). They can configure later in Settings |
| `is_first_login` false positive if step (c) fails mid-flow | Low | Flag only set on successful user+workspace creation. PATCH is idempotent |

## Rollback Plan

1. Remove `is_first_login` from `UserResponse` schema
2. Revert step (c) response in `auth.py`
3. Remove `<OnboardingModal>` from `Dashboard.tsx`
4. Remove `PATCH /me/onboarding` endpoint + revert i18n keys

## Dependencies

None — fully self-contained change.

## Success Criteria

- [ ] New user (step c) sees onboarding modal once on first dashboard visit
- [ ] User can rename workspace from modal and it persists
- [ ] User can skip modal at any point (no blockers)
- [ ] Returning user (steps a/b) never sees the modal
- [ ] `is_first_login` is `false` after completion or skip
- [ ] All onboarding text available in English and Spanish
