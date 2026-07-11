# Delta Spec: Account Linking

## Overview

Email-based OAuth account linking. Separates provider accounts from `users` into a new `user_accounts` table and rewrites `/auth/sync` with a 3-step linking flow. Covers both the new `account-linking` capability and the modified `user-auth` endpoint.

---

## ADDED Requirements

### Requirement: FR-001 — Account Linking by Email

When a user authenticates with a provider whose email matches an existing user (different provider), the system MUST create a `user_account` row linking the new provider to that existing user instead of raising a duplicate error.

#### Scenario: Google user links GitHub account

- GIVEN a user exists with email `a@b.com` via Google
- WHEN the same user authenticates via GitHub with email `a@b.com`
- THEN the system creates a `user_account` row with provider=`github` linked to the existing user
- AND the user can log in with either provider

#### Scenario: New user signs up

- GIVEN no user or user_account exists for provider P, provider_id I, or email E
- WHEN a new user authenticates via provider P with email E
- THEN the system creates a new `users` row
- AND creates a `user_account` row linking provider P to the new user

### Requirement: FR-002 — Migration of Existing Accounts

The migration SHALL create `user_accounts`, copy existing `auth_provider`/`auth_id` data from `users`, then drop those columns. The migration MUST be atomic — full rollback if any step fails.

#### Scenario: Existing data migrated correctly

- GIVEN existing users with `auth_provider` and `auth_id` set
- WHEN the migration runs
- THEN a `user_account` row exists for each user preserving the same provider and id
- AND the `auth_provider`/`auth_id` columns no longer exist on `users`

#### Scenario: Users with null auth columns are skipped

- GIVEN a user with `auth_provider IS NULL` (pre-migration edge case)
- WHEN the migration runs
- THEN no `user_account` row is created for that user
- AND the user remains intact

### Requirement: FR-003 — Sync Endpoint 3-Step Flow

The `/auth/sync` endpoint MUST implement: (a) find by `(provider, provider_id)` → update profile; (b) fallback to `find_by_email` → link accounts; (c) neither → create user + link account.

#### Scenario: Returning user logs in

- GIVEN a `user_account` exists for provider P with provider_id I
- WHEN the user authenticates via provider P
- THEN the sync endpoint updates the user's profile (name, avatar)
- AND returns the existing user without linking

#### Scenario: Existing user logs in with new provider

- GIVEN a user exists with email E via Google
- WHEN the same user authenticates via GitHub with email E
- THEN step (a) finds nothing, step (b) finds user by email
- AND the system creates a `user_account` linking GitHub to the existing user

### Requirement: FR-004 — User Response from Session Provider

The `UserResponse` DTO MUST derive `provider` and `provider_id` from the current session's `user_account`, not from the `User` entity (which no longer has those fields).

#### Scenario: Response reflects login provider

- GIVEN a user has Google and GitHub accounts linked
- WHEN the user logs in via GitHub
- THEN `UserResponse.provider` is `github`
- WHEN the user logs in via Google
- THEN `UserResponse.provider` is `google`

### Requirement: FR-005 — Backward Compatibility

Existing users MUST continue to work without re-authentication after migration. The `User` entity no longer has `auth_provider`/`auth_id` — all existing references to those fields MUST be removed.

#### Scenario: Same provider, different emails

- GIVEN two distinct users with emails `a@b.com` and `c@d.com`, both via Google
- WHEN both authenticate
- THEN each remains a separate user with their own `user_account` row

#### Scenario: Existing session token works post-migration

- GIVEN a user has a valid JWT with `user.id` before migration
- WHEN the migration runs
- THEN the same JWT continues to authenticate the user
- AND the user can call `/auth/sync` successfully

---

## ADDED Non-Functional Requirements

### Requirement: NFR-001 — Migration Data Integrity

The migration SHALL execute inside a transaction. If any step fails (create table, insert, drop columns), the entire migration MUST roll back. No partial state.

### Requirement: NFR-002 — No Re-auth Required

Existing users MUST NOT be prompted to re-authenticate after migration. The JWT payload references `user.id` — preserved unchanged.

### Requirement: NFR-003 — Concurrent Request Safety

The sync endpoint SHOULD handle concurrent auth requests for the same email without creating duplicate users. The `UNIQUE(provider, provider_id)` constraint on `user_accounts` SHALL be the final safeguard against race conditions. The repository MUST catch integrity violations and retry the find step.

---

## Out of Scope

- **Frontend** "linked accounts" management UI (settings page)
- **Unlinking** or removing a provider from an existing user
- **Primary account** selection or management
- **Multi-provider** unique constraint customization
- **Non-OAuth** authentication strategies
