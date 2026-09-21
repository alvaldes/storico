---
allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git commit:*), Bash(git diff:*), Bash(git log:*)
argument-hint: [message] | --no-verify | --amend
description: Create well-formatted commits with conventional commit format
---

# Smart Git Commit

Create well-formatted commit: $ARGUMENTS

## Current Repository State

- Git status: !`git status --porcelain`
- Current branch: !`git branch --show-current`
- Staged changes: !`git diff --cached --stat`
- Unstaged changes: !`git diff --stat`
- Recent commits: !`git log --oneline -5`

## What This Command Does

1. Unless specified with `--no-verify`, automatically runs pre-commit checks:
   - `pnpm lint` to ensure code quality
   - `pnpm build` to verify the build succeeds
   - `pnpm generate:docs` to update documentation
2. Checks which files are staged with `git status`
3. If 0 files are staged, automatically adds all modified and new files with `git add`
4. Performs a `git diff` to understand what changes are being committed
5. Analyzes the diff to determine if multiple distinct logical changes are present
6. If multiple distinct changes are detected, suggests breaking the commit into multiple smaller commits
7. For each commit (or the single commit if not split), creates a commit message using emoji conventional commit format

## Best Practices for Commits

- **Verify before committing**: Ensure code is linted, builds correctly, and documentation is updated
- **Atomic commits**: Each commit should contain related changes that serve a single purpose
- **Split large changes**: If changes touch multiple concerns, split them into separate commits
- **Conventional commit format**: Use the format `<type>: <description>` where type is one of:
  - `feat`: A new feature
  - `fix`: A bug fix
  - `docs`: Documentation changes
  - `style`: Code style changes (formatting, etc)
  - `refactor`: Code changes that neither fix bugs nor add features
  - `perf`: Performance improvements
  - `test`: Adding or fixing tests
  - `chore`: Changes to the build process, tools, etc.
- **Present tense, imperative mood**: Write commit messages as commands (e.g., "add feature" not "added feature")
- **Concise first line**: Keep the first line under 72 characters

## Guidelines for Splitting Commits

When analyzing the diff, consider splitting commits based on these criteria:

1. **Different concerns**: Changes to unrelated parts of the codebase
2. **Different types of changes**: Mixing features, fixes, refactoring, etc.
3. **File patterns**: Changes to different types of files (e.g., source code vs documentation)
4. **Logical grouping**: Changes that would be easier to understand or review separately
5. **Size**: Very large changes that would be clearer if broken down

## Examples

Good commit messages:

- `feat(auth): add the session refresh endpoint`
- `fix(api): resolve the memory leak in the streaming parser`
- `docs: update the deployment runbook with the rollback step`
- `refactor(domain): simplify the error handling in the extraction pipeline`
- `test(backend): cover the expiry boundary of the credential cipher`
- `perf(frontend): avoid re-rendering the kanban board on every keystroke`
- `chore(ci): pin the pnpm version read from package.json`
- `fix(frontend): address the minor styling inconsistency in the header`
- `feat(privacy): add input validation for the consent form`
- `ci: fail the deploy when production is not ready`
- `fix: remove the deprecated legacy adapter`
- `feat(i18n): add the missing Spanish translations for the settings page`

Example of splitting commits:

- First commit: `feat(db): add the migration for the credential table`
- Second commit: `test(backend): cover the migration against Postgres`
- Third commit: `docs: record the migration drift measurement`
- Fourth commit: `fix(ci): run the migration chain before the test suite`

## Command Options

- `--no-verify`: Skip running the pre-commit checks (lint, build, generate:docs)

## Versioning

This repository derives its version from the commit history. `make bump` runs
commitizen (`cz bump`), which reads the Conventional Commits since the last tag and
writes the next version into `package.json`, `frontend/package.json` and
`backend/pyproject.toml`, updates `CHANGELOG.md`, commits, and creates the tag.

So pick the type deliberately:

- `feat` releases a MINOR (`0.3.2` to `0.4.0`).
- `fix`, `refactor`, `perf` release a PATCH (`0.3.2` to `0.3.3`).
- `docs`, `test`, `chore`, `style`, `ci`, `build` release nothing; they ship with
  the next version.
- A `!` after the type, or a `BREAKING CHANGE:` footer, releases a MAJOR
  (`0.3.2` to `1.0.0`). Avoid it unless the change is genuinely incompatible.

Never hand-edit a `version` field and never create the tag yourself. The git tag is
the source of truth and `cz bump` is what reconciles the files to it.

`cz bump` commits every tracked change in the worktree along with the files it
writes, so run `make bump` on a clean tree, and never while you have unreviewed work
in progress.

## Important Notes

- By default, pre-commit checks (`pnpm lint`, `pnpm build`, `pnpm generate:docs`) will run to ensure code quality
- If these checks fail, you'll be asked if you want to proceed with the commit anyway or fix the issues first
- If specific files are already staged, the command will only commit those files
- If no files are staged, it will automatically stage all modified and new files
- The commit message will be constructed based on the changes detected
- Before committing, the command will review the diff to identify if multiple commits would be more appropriate
- If suggesting multiple commits, it will help you stage and commit the changes separately
- Always reviews the commit diff to ensure the message matches the changes