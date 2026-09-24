# Contributing to Storico

Thanks for your interest in Storico. This guide covers how to build, test, and
submit changes. For the full project definition — architecture, pipeline details,
ADR decisions, and non-obvious design constraints — read [AGENTS.md](AGENTS.md)
first; this file does not repeat it.

## Code of conduct

Be respectful and constructive. Storico is a thesis project and a research tool,
so keep discussion focused on the work and assume good faith. Harassment or
abuse is not tolerated.

## Before you start

For anything beyond a minor documentation fix, **please open an issue first** (or
comment on an existing one) and say you intend to work on it. This lets us give
early feedback and avoids two people building the same thing or a PR that does
not fit the project's direction.

A few notes to keep the project maintainable:

- **Link an issue.** PRs without a linked issue or prior discussion may be
  closed, except for small doc fixes.
- **Human oversight required.** AI-assisted contributions are fine, but
  low-quality or unreviewed agent output will be closed. Understand and test
  what you submit.
- New to the codebase? Look for issues labeled `good first issue`.
- Storico is a **thesis research project**. Its architecture (hexagonal backend,
  Astro + React islands frontend) reflects specific design decisions documented
  in AGENTS.md. Read the relevant ADRs before making architectural changes.

## Building

### Full stack (Docker Compose — recommended)

```bash
cp .env.example .env
make build     # Build all Docker images
make up        # Start all services (detached)
```

The API will be at **<http://localhost:8000>** and the frontend at
**<http://localhost:4321>**.

### Backend only (outside Docker)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Frontend only (outside Docker)

```bash
cd frontend
pnpm install
pnpm run dev    # http://localhost:4321
```

`pnpm` is the only package manager this repository uses: `frontend/package.json`
declares `packageManager: pnpm@10.15.0` and CI installs with
`pnpm install --frozen-lockfile`.

## Testing

### Backend

Run tests with **pytest**:

```bash
make test-backend                        # via Makefile
cd backend && .venv/bin/pytest -v        # or directly
cd backend && .venv/bin/pytest -v -m unit   # unit tests only (fast, no services)
```

- Tests use `asyncio_mode = auto` — async test functions are detected automatically.
- Markers: `unit` (fast, no external deps) and `integration` (require services).
- No `cargo test` equivalent gotcha here, but `pytest` runs each test file in its
  own process only if you use `-n` (pytest-xdist). For most cases the default
  runner is fine.

### Frontend

```bash
make test-frontend                        # build as smoke test (Makefile)
cd frontend && pnpm exec vitest run       # vitest, the frontend test runner
cd frontend && pnpm run build             # build as smoke test
```

**Vitest is the frontend test runner.** `frontend/package.json` wires `pnpm test`
to `vitest run` and `pnpm test:watch` to `vitest`, and CI runs `pnpm exec tsc
--noEmit`, `pnpm vitest run` and `pnpm build` on every push. The build step stays
the structural smoke test: if it compiles, the structural integrity is verified.

## Before you open a PR

For any code change:

1. **Backend**: `cd backend && .venv/bin/pytest -v` passes for the tests that
   cover your change. Run with `-m unit` for a fast feedback loop.
2. **Frontend**: `cd frontend && pnpm run build` compiles clean.
3. **Full stack**: `make build && make up` starts without errors and the health
   endpoints respond.
4. **Style**: ruff lints without surprises. We follow:
   - Line length: 100 (backend), TypeScript defaults (frontend).
   - Python: double quotes, numpy-style docstrings for public APIs.
   - Ruff config is in `backend/ruff.toml` — run `ruff check` before committing.
   - TypeScript: strict mode, `@/*` path alias for `src/*`.
5. **Do not bulk-run `ruff format` or blanket auto-formatters.** The tree is not
   uniformly formatted, so a blanket pass produces a large unrelated diff. Match
   the surrounding style in the files you edit. Comments should explain
   non-obvious "why", not restate the code.
6. **Architecture boundaries.** The backend follows hexagonal architecture
   (ports & adapters). Keep domain logic free of infrastructure imports. The
   frontend separates Astro (layout, routing, pages) from React (islands with
   state). Do not leak infrastructure concerns across boundaries.

## Commit messages

Keep them short and factual: what changed and why. We use a lightweight
`type(scope): summary` style, matching the existing history:

```
feat(privacy): expand privacy policy from 5 to 13 sections

Added GDPR, CCPA, cookies, sub-processors, data retention, and
international transfers sections. Matches Obscura's privacy model.

Fixes #42.
```

- `type` is one of `feat`, `fix`, `refactor`, `style`, `docs`, `test`, `perf`,
  `chore`. The `scope` is optional and lowercase (for example `api`, `frontend`,
  `privacy`, `nav`, `status`).
- The summary line is a complete sentence in imperative mood ("add", "fix",
  "remove"), not a description ("added", "fixes", "removing").
- No em dashes. Use commas, periods, or restructure the sentence.
- No AI-generated filler ("This commit improves...", "As an AI...").
- Do not add `Co-Authored-By` lines or list yourself as a co-author.

### The commit type decides the version

The version comes from the commit history; nobody edits the version fields by hand.
`make bump` runs [commitizen](https://commitizen-tools.github.io/commitizen/)
(`cz bump`), which reads the Conventional Commits since the last tag, computes the
next version, writes it into `package.json`, `frontend/package.json` and
`backend/pyproject.toml`, updates `CHANGELOG.md`, commits, and creates the tag.

The type you pick is therefore what decides the release:

| Commit | Bump | Example |
| --- | --- | --- |
| `feat` | MINOR (`0.3.2` → `0.4.0`) | a new capability, backwards compatible |
| `fix`, `refactor`, `perf` | PATCH (`0.3.2` → `0.3.3`) | a bug fix, a cleanup, or a speedup |
| `docs`, `test`, `chore`, `style`, `ci`, `build` | no bump | they ship with the next version, they do not create one |
| a type followed by `!`, or a `BREAKING CHANGE:` footer | MAJOR (`0.3.2` → `1.0.0`) | an incompatible change |

The scope never affects the bump: `feat(api): ...` and `feat: ...` release the same
thing.

Careful with `!` while the project is on `0.x`: by default commitizen takes it all
the way to `1.0.0`. Setting `major_version_zero = true` in `.cz.toml` keeps 0.x
semantics, where a breaking change releases `0.4.0` instead.

The three version fields are mirrors of the git tag, and the tag is the source of
truth. Never edit them by hand and never create the tag yourself. Across `v0.3.0`,
`v0.3.1` and `v0.3.2`, `backend/pyproject.toml` said `0.3.0` while
`frontend/package.json` said `0.2.0`, and there was no manifest at the repository
root: the two files contradicted each other and neither matched the tag. `cz bump`
is what reconciles the files to the tag.

Run `make bump` from the repository root with a clean working tree. `cz bump`
commits the files it writes together with every tracked change in the worktree, so
`make bump` refuses to run while the tree is dirty.

The three fields must already carry the version of the last tag before you bump.
With `version_provider = "scm"` commitizen reads the current version from the tag,
searches each file for that exact string, and skips any file that does not contain
it, without an error and while still creating the tag. A lagging field therefore
never catches up, which is how `v0.3.1` and `v0.3.2` shipped with stale manifests.
`make bump` refuses to run when a version file does not carry the current tag
version.

## Pull requests

- All submissions are reviewed; a maintainer merges after approval.
- Keep the diff small and readable. One logical change per PR. Split large
  contributions into several PRs.
- Reference the issue the PR closes, and say how you verified it (the test or
  repro that now passes).
- PRs should include both frontend and backend changes when the feature spans
  both layers, but keep the scope narrow to a single feature.

## Reporting bugs

Open an issue with enough detail to reproduce:

- The Storico version or commit, plus OS and architecture.
- How you are running Storico (Docker Compose, backend-only, frontend-only).
- A repro: the user story input, the expected result, and what actually happened.
- If it is an LLM-related issue, include the model name and version (for example
  `llama3.2`, `mistral`).
- API-related bugs: include the request payload and response status.
- Frontend bugs: include browser and console errors if available.

**Security issues:** do not open a public issue. Contact
alvaldes.dev@gmail.com directly.

## Scope and direction

Storico is a **thesis research project** for the Master's in Software Engineering
at the Universidad Tecnológica de la Mixteca (UTM), Oaxaca, México. Its primary
goal is to evaluate whether LLM-based automatic task decomposition from user
stories improves planning efficiency and task clarity in agile teams.

The project's priorities are:

1. **Research integrity.** The tool must support the experimental evaluation
   (expert judgment, TCR/TAS/IFI metrics) planned in the thesis.
2. **Extraction quality.** Accuracy and consistency of LLM-generated tasks is
   the core contribution.
3. **Architecture discipline.** The hexagonal backend and Astro islands frontend
   are intentional — they enable the multi-model LLM strategy and the
   thesis evaluation.
4. **Local-first LLM.** Ollama is the primary integration target, because it needs no
   credential and keeps the offline path first-class. Cloud models (OpenAI, Anthropic,
   Gemini) are supported, but a contribution should not make the offline path depend
   on one.

Contributions that add features outside the thesis scope (for example unrelated
project management tools, CI/CD integrations, or non-agile workflows) may be
deferred until after the thesis evaluation is complete.

## License

By contributing, you agree that your contributions are licensed under the MIT
License, the same license as the project.
