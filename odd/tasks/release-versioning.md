# ODD Feature: release-versioning

> **Status**: implemented and committed on `main`; **nothing pushed**. Native review has
> **not** run for this candidate, deliberately: the review flow in this worktree is owned by
> the other session, and opening a second lineage on the same target is the drift source this
> change exists to avoid. See "Follow-ups".
> **Created**: 2026-09-21
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `main`, direct. This matches the existing practice for docs commits here.
> **Receipt-driven development**: on in this clone (decided by global).

## Problem

The repository released five tags with no tooling keeping the version fields honest, so the
three carriers disagreed with each other and with the tag. Measured per tag:

| tag | `backend/pyproject.toml` | `frontend/package.json` | `package.json` (root) |
| --- | --- | --- | --- |
| `v0.3.0` | `0.3.0` | `0.2.0` | did not exist |
| `v0.3.1` | `0.3.0` | `0.2.0` | did not exist |
| `v0.3.2` | `0.3.0` | `0.2.0` | did not exist |

No manifest ever carried `0.3.1` or `0.3.2`. There was no `.cz.toml`, no `CHANGELOG.md`, no
release workflow, and no bump target in the `Makefile`.

## Established facts (verified)

1. **`cz bump` fails silently when a version file lags the tag.** With
   `version_provider = "scm"` commitizen reads the current version from the git tag, searches
   each `version_files` entry for that exact string, and skips a file that does not contain
   it: no error, no warning, and the tag is created anyway. Measured three times with the same
   tag `v0.3.2` and only the manifests varied:

   | manifests start at | after `cz bump` | tag |
   | --- | --- | --- |
   | `0.3.2` (same as the tag) | all three rewritten to `0.4.0` | `v0.4.0` |
   | `0.3.0` | left untouched | `v0.4.0` |
   | `0.2.0` | left untouched | `v0.4.0` |

   This makes the drift self-perpetuating, and it is what produced the unreconciled
   `v0.4.0` on the first real bump of this change.

2. **`cz bump` commits every tracked change in the worktree**, staged and unstaged, plus the
   files it writes. Measured: an accidental bump in this worktree swept a `Makefile` and an
   unstaged `frontend/package.json` into its commit.

3. **The verified commit-to-version mapping** for `cz_conventional_commits` (commitizen
   4.18.1): `feat` MINOR; `fix`, `refactor`, `perf` PATCH; `docs`, `test`, `chore`, `style`,
   `ci`, `build` no bump; `!` or a `BREAKING CHANGE:` footer MAJOR. The scope never affects it.

4. **`major_version_zero = true` keeps breaking changes inside 0.x.** Measured with this
   repository's own `.cz.toml`: a `feat!` went from `0.3.2` to `0.4.0` with the option and to
   `1.0.0` without it.

5. **A bare `package.json` at the root is read by the starship `package` module** with no
   lockfile, and with `"private": true` when `display_private = true`. It does not break the
   astro/vite build (`make test-frontend` exits 0).

## Decisions

- **The git tag is the source of truth**; the three version fields are mirrors. Chosen over a
  file-based provider because the tags already existed and already preceded the manifests.
- **Lockstep**: one version for frontend and backend, decided by the owner. The repository
  already tagged globally.
- **`major_version_zero = true`**, so a `!` commit does not jump a 0.x project to `1.0.0`.
- **`docs` and `chore` for this change**, so adopting the tooling and documenting it does not
  itself consume a version. The pending increment stays available for real work.

## Non-goals

- Moving the pnpm workspace root. The root `package.json` carries a version and no
  `workspaces`, and pnpm is not run from the root.
- Pushing, opening a PR, or publishing. Those stay with the owner.
- Reviewing the historical `0.2.0`/`0.3.0` discrepancy in either half.

## Evidence log

| Commit | Content |
| --- | --- |
| `d3e97d6` | `chore(build)`: the guarded `make bump` target |
| `3ea6e02` | `docs`: the commit-to-version mapping, the workflow, and the agent rules |
| `0c45160` | `chore(release)`: `.cz.toml` and the root `package.json` |
| `b6aa4cb` | `chore(frontend)`: align the frontend version with the backend |
| `abe4c65` | `docs`: drop the emoji guidance from the commit command |
| `af91291` | `bump: version 0.3.2 -> 0.4.0` (cz-generated: `CHANGELOG.md`, 382 lines) |
| `433c248` | `chore(release)`: write the version fields the `v0.4.0` tag implies |
| `8f5409b` | `fix(build)`: refuse to bump when a version file lags the tag |
| (this commit) | `docs(odd)`: this record |

Guard behaviour, verified by extracting the recipe with `make -n bump` and running it in four
sandbox repositories, never by running the target:

| Condition | Result |
| --- | --- |
| clean tree, fields matching the tag | passes to `cz bump` |
| dirty tree (staged or unstaged) | blocks |
| a version field lagging the tag | blocks, naming the path |
| no tag at all | blocks |

## Follow-ups (not part of this change)

1. **Native review for these commits has not run.** RDD is on in this clone, so this candidate
   is reviewable, but the review flow belongs to the other session in this worktree. Whoever
   opens the lineage should do it once, on a stable tree.
2. **Nothing is pushed.** `main` is ahead of `origin/main` by the commits in the Evidence
   log above, and carries the local tag `v0.4.0`.
3. `CONTRIBUTING.md` lists `feat`, `fix`, `refactor`, `style`, `docs`, `test`, `perf`, `chore`
   as the commit types while the history also uses `ci` and `build`, both of which the mapping
   in this change already names. The list is cosmetic drift, not a behaviour gap.
