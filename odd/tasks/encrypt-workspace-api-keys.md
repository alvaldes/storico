# ODD Feature: encrypt-workspace-api-keys

> **Status**: done and landed on `main` @ `6583e40` — eight commits from `c45bc66`: `65758d3`,
> `4a86859`, `a323172`, `8457fda`, `88fdfed` (the implementation and its record) then `2c9ba73`,
> `7f07238`, `6583e40` (the answers to the verification). Branch deleted, `main` re-gated, **not
> pushed**. Receipt-driven development is **off** in this clone, so no native review ran; an
> independent verification did, and it found three statements the record made that no test defended
> — each by mutation — plus a pre-existing credential leak it did not fix.
> **Created**: 2026-09-19
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `feat/encrypt-workspace-api-keys`.
>
> **Execution**: the exploration and the design were the parent's; the implementation was delegated
> to a writer. **The writer's first run changed nothing and reported three bugs in the brief** — all
> three confirmed, all three incorporated below. That is recorded because it is the delegation
> working as intended, not a footnote.

## Process correction: the review switch was on

**This record said receipt-driven development was "off in this clone", and for the second half of
this session that was false.** The switch read `off (decided by default)` when the session began, and
was turned on globally mid-session — `~/.gentle-ai/state.json` records `rdd_mode = 'on'` with
`rdd_mode_recorded_at = 2026-09-19T18:49:02Z`. This record's line was copied forward from the earlier
features without re-checking it, which is **the same defect this batch spent the day removing**: a
claim about state, written once and never re-read.

So native review was the expected path for this candidate and it did not run. Two independent
verifications did, and their findings are recorded below — every one of them found something material.
Whether that is an adequate substitute is the maintainer's call, not this record's.

It could not have run from the parent session regardless: the `gentle_review` facade answers
`native-status-package-binary-missing` here, while a subagent's context reached the lifecycle and
returned an unresolved provider consent envelope for the last candidate. The recovery is
`node scripts/install-gentle-ai.mjs` from the installed package directory, which is a maintenance
action rather than something this session takes on its own.

## Problem

Every workspace LLM API key was stored in **plaintext**:

```python
# infrastructure/database/models/workspace_llm_config.py:29
api_key: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
```

Added as a plain column by revision `0011`, with no encryption anywhere in the codebase. An earlier
slice found and removed a **false claim** in the UI ("Stored encrypted at rest") and made
`docs/security.md` honest about the situation at line 88, with the fix listed as pending at line 98.
This feature makes that statement true instead of merely honest.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | The mechanism | **User-approved**: Fernet (AES-CBC + HMAC) with a master key from `STORICO_ENCRYPTION_KEY`. Rejected: `pgcrypto` (couples to Postgres and breaks the SQLite suite) and an external KMS (infrastructure the single-VM deploy does not have). |
| D2 | Where it lives | Hexagonal: a `CipherPort` in `domain/ports`, a `FernetCipher` in `infrastructure/crypto`. The **repository** encrypts on write and decrypts on read, and those are the only two places that touch the stored value, so no caller ever holds ciphertext. |
| D3 | Ciphertext format | Version-prefixed (`v1:` + token). The prefix is what makes rotation possible later **and** what lets the read path tell an encrypted value from a legacy plaintext one. It is public (`FernetCipher.PREFIX`) because revision `0024` has to recognize an already-encrypted row, and re-spelling the marker there would let the two drift. |
| D4 | Legacy rows | Tolerant read: a value without the prefix is returned unchanged, so the code can be deployed before the data is migrated. The cipher owns that decision, because the cipher owns the format. |
| D5 | Migration | Revision `0024` encrypts the existing rows. **Deploy order is code first, then migration** — the new code reads both shapes, the old code would hand ciphertext to a provider. `NULL` and `''` are left alone (no secret to protect; both are spellings of "no credential"); an already-prefixed value is skipped so a re-run cannot double-encrypt. |
| D6 | Missing key | **Fail closed on write**: with no key configured, saving a credential raises `EncryptionKeyMissing`. The app still starts and legacy plaintext still reads. A default key would silently encrypt production data with a published value. |
| D7 | Undecryptable value | `CredentialUndecryptable` — never a silent `None`. A value marked as ours with no key to open it has no plaintext to fall back to, and returning `None` would be indistinguishable from "no credential configured". |
| D8 | The GET surface | **User-approved**: `GET /settings/llm` keeps returning the decrypted key to the workspace admin, as `docs/security.md` documents. This protects data at rest, not the endpoint; that limit is stated, not implied. |
| D9 | Whether to widen the column | See below. It turned out to be **required**, not optional. |
| D10 | Dependency | Declare `cryptography` at the installed floor, `>=50.0.1`. |

## The column could not hold its own ciphertext

The writer found this and it is the most valuable finding of the feature. `api_key` was
`String(500)`, and the request schema accepts up to 500 characters — but what gets stored after this
change is the **ciphertext**, and Fernet's base64 output is about 1.4 times longer. Measured:

| plaintext | stored (`v1:` + token) | fits `String(500)`? |
|-----------|------------------------|---------------------|
| 64 | 187 | yes |
| 200 | 359 | yes |
| 303 | 503 | **no — the exact maximum that would have fit** |
| 360 | 571 | **no** |
| 500 | 763 | **no** |

So a credential longer than **303 characters** would have overflowed. **SQLite does not enforce
a `VARCHAR` length**, so no test in this repository could have caught it; Postgres would have raised
`value too long for type character varying(500)` — during the migration for an existing long key,
and on a legitimate admin save for a new one. It is the same class of trap the repository already has
history with: a Postgres-only constraint that a SQLite suite hides.

Fixed three ways, because one was not enough:

1. The column is `String(1000)`, and the model comment carries the arithmetic.
2. Revision `0024` **widens the column before encrypting**, via `batch_alter_table` so it works on
   SQLite as well as Postgres, with the reason in its docstring.
3. A test asserts the two numbers **against each other** rather than trusting either: the accepted
   plaintext length is read from the request schema, the declared width from the model, and the
   ciphertext of a maximum-length credential must fit. Mutation-checked — narrowing the column back
   to 500 fails it with `a 500-character credential stores as 763 characters, which does not fit the
   declared 500`.

The downgrade deliberately does **not** narrow the column back, and says so: a column wider than the
model declares is harmless to every reader, a truncated secret is not.

## Three bugs in the brief, found by the writer before it wrote anything

| # | What the brief said | What is true |
|---|--------------------|--------------|
| B1 | Only `api/routes/workspace_settings.py` resolves the repository through `get_repository(...)`. | **Two** sites do. `api/routes/extraction.py:111` also does, and the moment the constructor requires a cipher, every extraction request raises `TypeError`. The parent's grep had searched only two files. Without this, test requirement 14 (the extraction path receives the plaintext) is unimplementable. |
| B2 | The branch `feat/encrypt-workspace-api-keys` exists. | It did not. HEAD was `main`, clean. The writer stopped rather than placing feature work on the default branch. |
| B3 | `cryptography` is 42.0.5. | The venv — the interpreter that runs the tests — has **50.0.1**. The parent had measured the system interpreter, which does not even have it installed. The declared floor follows the venv. |

All three were verified by the parent before the corrected brief went back out.

## Evidence

| Check | Command | Result |
|-------|---------|--------|
| Backend suite | `python -m pytest -q` | **692 passed, 1 skipped** (668 before; +24) |
| Backend lint (CI scope) | `ruff check src tests` | `All checks passed!` |
| Backend format | `ruff format --check src tests` | `224 files already formatted` |
| Cipher tests | `pytest tests/test_unit/test_fernet_cipher.py -v` | 8 passed |
| Repository tests | `pytest tests/test_repositories/test_workspace_llm_config_repo.py -q` | 5 passed |
| Migration tests | `pytest tests/test_unit/test_encrypt_workspace_api_keys_migration.py -v` | 8 passed |
| Frontend | `pnpm vitest run`, `tsc --noEmit` | 36 files / 420 passed, exit 0 — **untouched by this branch** |
| The security assertion | repository tests read the raw column, around the repository | the stored value starts with `v1:` and does not contain the plaintext |
| The width hazard | measured, then pinned | 500 plaintext → 763 stored; the guard fails if the column narrows |
| The refusal is real | `pytest tests/test_api -k master_key` | 500 with `ENCRYPTION_KEY_MISSING`, nothing written |

## Environment facts worth keeping

- **SQLite does not enforce `VARCHAR` length.** Any schema change that makes a stored value longer
  than its column is invisible to this suite and fatal on Postgres. The guard added here is the
  pattern to copy: compare the declared width against the worst case the schema admits.
- **`cryptography` arrives transitively** (via `google-auth`) and was undeclared; the venv has
  50.0.1 while the system interpreter has none. Measure dependency versions with the interpreter that
  runs the tests, not whichever `python` is on PATH.
- **`conftest.py` is a shared surface worth having in the allowed paths**: four test files each
  needed the same master-key fixture, and with conftest out of scope the worker had to duplicate a
  module-local autouse fixture four times.
- **The analyzer's index is stale, and it is not a gate.** The writer diagnosed it: pi-lens's graph
  was built at `ccb5f78f` while HEAD was `c45bc66a`, with *"no node for it (likely added/changed after
  the graph was last built)"* and *"Graph is stale: built 5447m ago"*. `pilens_rebuild` was not among
  its callable tools. Meanwhile `ruff`, `compileall` and a fresh-interpreter import of every new
  symbol all pass. This also explains the `Result.rowcount` cascades elsewhere in this session.

## Findings left unfixed on purpose

1. **`Result.rowcount` is untyped in seven repositories.** The analyzer flags whichever one sits in a
   changed file. Refuted at runtime on the extraction repository and, separately, on
   `task_repository.py` through its own delete path. A shared helper or a typed cast in all seven
   would settle it; doing one alone is worse than doing none.
2. **Twelve `add_exception_handler` registrations carry the same analyzer complaint.** Eleven predate
   this change and were not touched — verified: `git diff` shows the parent's `app.py` change is one
   added registration, with zero pre-existing lines modified. The repository's own answer to this one
   is a targeted `# type: ignore[arg-type]` on the last registration, applied once. The handler's
   behaviour is refuted at runtime by the refusal test.
3. **`docs/security.md` now describes what is implemented and what it does not protect** — including
   that the endpoint still returns the key to the workspace admin, that the master key lives in the
   process environment, and that ciphertext does not stop someone holding both the database and the
   key. Key rotation remains unimplemented; the `v1:` prefix is what makes it possible later.

## Independent verification

Ran over `c45bc66..88fdfed`, read-only, against a writer's implementation. It confirmed the
encryption end to end (a credential written through the real route lands in the column as `v1:`
ciphertext, with the plaintext absent from the whole row), confirmed the choke point is complete by
deriving it independently (no raw SQL, no second query path, no ORM bypass, and `upsert` routes
**both** its insert and update branches through `_to_orm_kwargs`), confirmed no secret escapes into
logs or responses, confirmed the authorization empirically rather than from the docstring
(admin 200 / member 403 / non-member 403 on the credential-bearing route), and confirmed fail-closed
down to the database having nothing in it after a refusal.

It also **strengthened** the deploy-order claim beyond what was written: the migration imports
`FernetCipher` and reads `Settings.encryption_key`, neither of which exists at `c45bc66`, so it
cannot run against the previous release at all — and the old read path demonstrably hands the
ciphertext to the provider as if it were a key.

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| V1 | medium | Making the repository swallow `CipherError` into `None` left the suite green (692 passed): D7's "never a silent `None`" was stated but not defended. Returning `None` also makes a misconfigured master key indistinguishable from an unconfigured workspace, so the readiness rule would tell the admin to configure a credential that already exists. | **Fixed** — a repository test now reads a `v1:` row with a keyless cipher and requires the raise. Mutation re-run: fails with `DID NOT RAISE CredentialUndecryptable`. |
| V2 | medium | The migration's `_API_KEY_LENGTH` was a third, uncross-checked copy of the width. Lowering it to 500 kept 692 passing while leaving the column narrower than what the repository writes. | **Fixed** — a test asserts the migration's width covers the model's and the ciphertext of the widest accepted credential. Mutation re-run: `assert 500 >= 1000`. |
| V3 | medium | "The widening is first and is not incidental" was not pinned: reversing the order kept 692 passing, and with the order reversed a 763-character ciphertext is written into a `VARCHAR(500)` — which SQLite verifiably accepts and Postgres rejects. | **Fixed** — the statements the revision executes are captured and the widening must precede the first rewrite. Mutation re-run: `widening was statement 12 and the first rewrite was 1`. |
| V4 | medium, pre-existing | **A credential escapes the response and the logs.** The Gemini model probe puts the key in the URL query string, and the route echoes the httpx error — including the full URL — into the 502 body; `httpx` also logs that URL at INFO, which is precisely what the route's own docstring claims to have avoided. The echoed credential can be the *stored, decrypted* one. Confirmed **not** caused by this branch, and returned only to a workspace admin, so it is not a cross-user escalation. | **Recorded** — see the follow-ups. It is the same class of defect this feature exists to remove, but a different mechanism (transport and logging, not storage), and moving the key to a header is an integration change that needs its own slice and its own verification. |
| V5 | low | "past roughly 310 characters" — the exact maximum that fits 500 is **303**. | **Fixed** in the migration docstring and here, with the measurement in the table. |
| V6 | low | `GET /llm/status` is member-readable, but 500s with `CREDENTIAL_UNDECRYPTABLE` when a ciphertext row exists and no key is configured — the state in which a member most needs the readiness answer. Fail-closed and leak-free; the cost is availability. | **Recorded**. |
| V7 | low | `cipher_error_handler` logs with `exc_info=exc`, so a full traceback is emitted. Verified free of the plaintext and the master key under the default formatter, but a formatter that renders locals would expose frame arguments. | **Recorded** — not a defect of this change, and the reason is worth knowing. |

One caveat the verifier recorded about its own method, kept because it bounds the claims above: the
tests construct the repository with a cipher directly, so the `get_cipher()` dependency's
env-absent branch is exercised through the routes rather than at the repository level.

## Follow-ups this surfaced, recorded rather than bundled

1. **The Gemini probe leaks the credential into its own error response and into the logs** (V4).
   `workspace_settings.py` builds the probe URL with `?key=<credential>` and returns the httpx
   error, URL included, in the 502 body; httpx logs the URL at INFO. The credential can be the
   stored one, because the probe falls back to the saved key. The fix is to move the credential to a
   request header and stop echoing the URL — an integration change with its own test surface, and
   the most security-relevant item left open.
2. **`GET /llm/status` fails closed but unhelpfully** when a ciphertext row exists and no master key
   is configured: a member asking whether the workspace is ready gets a 500 rather than an answer
   saying the server cannot read the stored credential. Worth one decision (V6).
3. **`exc_info=exc` in the cipher handler emits a traceback** (V7). Harmless under the default
   formatter; a locals-rendering formatter would change that.
4. **The analyzer's index is stale and is not a gate** — see the environment notes above. Nothing in
   this feature depends on it, and every claim it made about this range was refuted by execution.

## Tasks — all closed

- [x] Explore the full read/write path of `api_key` before changing anything.
- [x] `CipherPort` + `FernetCipher`; errors that never carry the secret.
- [x] Encrypt on write, decrypt on read, tolerate legacy plaintext.
- [x] Declare `cryptography>=50.0.1`; master key from `STORICO_ENCRYPTION_KEY` with no default.
- [x] Wire the cipher through both DI sites, with explicit injection and no singleton.
- [x] Revision `0024`: widen the column, then encrypt; refuse without a key; skip what is already encrypted.
- [x] Fail closed on write; explicit failure on an undecryptable value; HTTP 500 with a machine-readable code.
- [x] The tests, including the security assertion and the width guard.
- [x] `docs/security.md` and `backend/.env.example`.
- [x] Re-export the three cipher errors from `domain/entities` (the writer flagged the gap; the parent closed it).
- [x] Independent verification — the encryption, the choke point, the leak-free paths and fail-closed all confirmed; V1–V3 (three surviving mutants) fixed and re-mutated, V5 corrected, V4/V6/V7 recorded.
- [x] Fast-forward into `main`, delete the branch, re-gate — `main` @ `6583e40`; backend
      695 passed / 1 skipped with `ruff check src tests` clean and 224 files formatted, frontend
      36 files / 420 tests and `tsc --noEmit` exit 0 — all re-run **after** the merge.
