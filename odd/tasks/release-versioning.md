# ODD Feature: release-versioning

> **Status**: implemented and committed on `main`; **nothing pushed**. Native review ran on
> 2026-09-21 under this worktree's review flow and **closed approved** —
> `review-85d12db7ba7103e8`, tier `high`, four lenses, nine advisories and no correction. See
> "Native review".
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

## Native review

Native review `review-85d12db7ba7103e8`, target
`sha256:ddfaa2fec2a973e30b9a80c64a9e37a6afc872db96498e74cf7c87efa2c44d2a`: `state: approved`,
`risk_tier: **high**`, **four lenses** (`review-risk`, `review-resilience`, `review-readability`,
`review-reliability`), 10 files, `original_changed_lines: 742`, `correction_budget: 200`,
`risk_reasons: [{"code": "process_boundary", "signal": "shell_process", "path": "Makefile"}]` — the
provider reads the `Makefile` as code that starts other processes, which is precisely what the guarded
`bump` target is. Four reviewers were prepared and submitted over `pi_host_relay`, and the
acknowledgement burned the authority (`gentle-ai.review-acknowledged/v1`).

It ran on the committed range `4931f10..55c1c08`, once the tree was clean and stable, under this
worktree's review flow. This section was written afterwards, so it was **not** part of the reviewed
candidate.

**Nine advisories, none opening a correction.** Three are `WARNING` and six `SUGGESTION`:

| Finding | Lens | Location | Severity |
|---|---|---|---|
| `R2-001` | readability | `AGENTS.md:46` | WARNING |
| `R2-002` | readability | `CONTRIBUTING.md:137-178` | SUGGESTION |
| `R2-003` | readability | `Makefile:55-58` | SUGGESTION |
| `R3-cz-not-installed` | reliability | `Makefile:51-58` | WARNING |
| `R3-grep-substring` | reliability | `Makefile:54-57` | SUGGESTION |
| `R3-tag-baseline-remote` | reliability | `Makefile:52-53` | SUGGESTION |
| `R4-bump-not-idempotent-retry` | resilience | `Makefile:52` | SUGGESTION |
| `R4-partial-bump-no-recovery` | resilience | `Makefile:51-57` | WARNING |
| `R4-tag-grep-substring` | resilience | `Makefile:54-56` | SUGGESTION |

**Eight of the nine land in the `Makefile`** — the same file that forced the tier to `high` and required
all four lenses. The risk lens returned 820 bytes and **no findings at all**; the populated ones were
reliability and resilience. The coincidence is worth recording: the tier driver and the finding cluster
are the same artifact, which is the classification doing its job rather than handing out lenses at
random.

Two advisories — `R3-grep-substring` and `R4-tag-grep-substring`, arriving independently from two lenses
— point at the same thing: the guard's version check is a **substring** grep, so a tag string that
appears inside a longer one could satisfy it. That is the same class as this record's own fact #1, where
commitizen matches the tag string literally and skips a file that lacks it, so the guard's precision
deserves the scrutiny the tooling got. The closure envelope carries ids, lenses, locations and
severities only, so this record does not paraphrase the finding text.

Deliberately **not** fixed here: the review's own closure says advisories are separate later work and
never a reason to re-run review on this candidate, and editing the reviewed tree would mean delivering
something other than what was reviewed.

## Post-review fix

`R3-grep-substring` and `R4-tag-grep-substring` — the same finding arriving from two lenses — were
confirmed and fixed in the commit that carries this section, **after** the approval and therefore
outside the reviewed range `4931f10..55c1c08`. The review of that range stands; this is new,
unreviewed work.

Confirmed as a false pass before touching the guard. With the tag at `v0.4.0` and all three version
fields at `0.3.0`, the guard passed anyway, because the check was `grep -q "$tag" "$file"` and one
file contained a dependency string reading `"^0.4.0"`:

```
package.json             "version": "0.3.0"   and   "lib": "^0.4.0"
frontend/package.json    "version": "0.3.0"
backend/pyproject.toml   version = "0.3.0"
tag                      v0.4.0
guard                    PASSED   <- fail-open, the exact drift the guard exists to stop
```

The check now extracts the value of the version field with an anchored pattern and compares it for
equality against the tag, so containment can no longer satisfy it. Re-verified in six sandbox
repositories, asserting the extracted recipe before trusting any result:

| Condition | Result |
| --- | --- |
| all three fields equal the tag | passes to `cz bump` |
| a field lagging the tag | blocks, naming the file and both values |
| a field lagging the tag **plus** a `^<tag>` dependency string | blocks |
| a field reading `10.4.0` while the tag is `0.4.0` | blocks |
| no tag at all | blocks |
| dirty tree | blocks |

The remaining seven advisories are untouched and stay the owner's to disposition.

## Native review of the guard fix

Native review `review-5809e0d918afbd67`, target
`sha256:b4afc99eb6e0b9429508a4ce7b28cffd4358e1489bbcf91dc8e5e57e767895e0`: `state: approved`,
`risk_tier: high`, **four lenses** (`review-risk`, `review-resilience`, `review-readability`,
`review-reliability`), 2 files, 46 lines, `correction_budget: 23`, and the same tier driver as the
first round — `process_boundary` on the `Makefile`. Four reviewers were prepared and submitted, and
the acknowledgement burned the authority (`gentle-ai.review-acknowledged/v1`).

It ran on the committed range `fa56bd6..a1d549b`, whose tree is `a1d549b` — not the tip of `main`,
which kept moving afterwards. What the harness freezes is the **workspace view**, not the commit, so a
later tip does not invalidate the review. This section was written afterwards and was **not** part of
the reviewed candidate.

**Six advisories, none opening a correction.** One is `WARNING` and five `SUGGESTION`, and all six
land in the `Makefile`, inside the six lines the fix touched:

| Finding | Lens | Location | Severity |
|---|---|---|---|
| `R2-inline-recipe-complexity` | readability | `Makefile:55-61` | SUGGESTION |
| `R2-sed-json-anchor` | readability | `Makefile:56-58` | SUGGESTION |
| `R3-json-field-drift` | reliability | `Makefile:56-59` | WARNING |
| `R3-no-tests` | reliability | `Makefile:55-60` | SUGGESTION |
| `R3-pyproject-first-match` | reliability | `Makefile:58` | SUGGESTION |
| `R4-empty-extraction-message` | resilience | `Makefile:56-60` | SUGGESTION |

**`R3-pyproject-first-match` is the residual limitation this record already declared**, found
independently by a reviewer. Announcing your own blind spot turns a future surprise into an
independent confirmation, which is cheaper than being told.

**The cost asymmetry, now measured twice.** The first round was 742 lines and came out tier `high`
with four lenses and nine advisories. This one was **46 lines and still tier `high`, four lenses, six
advisories**, because `process_boundary` keys on the file extension rather than on the diff. Any edit
to that `Makefile`, however small, therefore costs a full review round — which is why the disposition
below is all-or-nothing rather than proportional.

**Disposition: the six stay open, deliberately.** The owner chose not to open a fix round, so these
are follow-ups and not oversights. The reasoning is the asymmetry above: a round costs the same
whether it touches one line or forty-six, so the real choice was between fixing everything and fixing
nothing, and the review had closed approved with no correction opened.

## Follow-ups (not part of this change)

1. ~~**Native review for these commits has not run.**~~ **Done.** It ran on 2026-09-21 under this
   worktree's review flow, once the tree was clean and stable, and closed approved —
   `review-85d12db7ba7103e8`, tier `high`, four lenses. Its nine advisories were not a correction;
   they are listed under "Native review" and eight of the nine are in the `Makefile`. Two of them,
   the substring check, are fixed in "Post-review fix"; seven remain.
2. **Nothing is pushed, and the tag least of all.** `main` is on `origin/main` as of `5c295d4`, but
   `git ls-remote --tags origin` finds no `v0.4.0`: the tag exists only on this machine. Because
   `version_provider = "scm"` makes the tag the version source of truth, a clean clone has `v0.3.2` as
   its highest tag and would compute its next bump from that baseline. The guard blocks it
   fail-closed, which is the first time that design met a case it did not invent. Pushing a tag is a
   release decision and belongs to the owner.
3. `CONTRIBUTING.md` lists `feat`, `fix`, `refactor`, `style`, `docs`, `test`, `perf`, `chore`
   as the commit types while the history also uses `ci` and `build`, both of which the mapping
   in this change already names. The list is cosmetic drift, not a behaviour gap.
4. **The six advisories of the guard-fix review stay open, by decision** — bringing the open advisory
   count to thirteen. They are listed under "Native review of the guard fix" with their locations and
   severities. Two would matter first if this is revisited: `R3-pyproject-first-match`, the only false
   pass left in the guard (a nested `version` key whose value equals the tag while the root differs),
   and `R4-empty-extraction-message`, where an empty extraction reads as `carries version ''`. Both
   can be closed without a parser: block on **ambiguity** when more than one line matches the anchored
   pattern, and say so when there is nothing to read. That keeps the design rationale that the guard
   models the mechanism rather than the file's meaning.
