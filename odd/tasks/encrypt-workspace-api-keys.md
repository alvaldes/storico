# ODD Feature: encrypt-workspace-api-keys

> **Status**: planning — no commit, no evidence yet.
> **Created**: 2026-09-19
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `feat/encrypt-workspace-api-keys` (to be created off `main` @ `6174f5a`).
> **Receipt-driven development**: off in this clone.

## Problem

Every workspace LLM API key is stored in **plaintext**:

```python
# backend/src/storico/infrastructure/database/models/workspace_llm_config.py:29
api_key: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
```

Added as a plain column by migration `0011` (`0011_add_api_key_to_workspace_llm_config.py:21-24`),
with no encryption anywhere in the codebase. `grep` for `cryptography`, `Fernet`, `nacl` in
`backend/src` returns nothing.

An earlier slice found and removed a **false claim** in the UI ("Stored encrypted at rest") and
in `docs/security.md`, which now states the situation truthfully at `:88` and lists the fix as
pending at `:98`:

> - [ ] Cifrado en reposo de las API keys de LLM (hoy se guardan en claro en `workspace_llm_configs`)

This feature makes that statement true instead of merely honest.

`cryptography` **42.0.5 is installed but not declared** in `backend/pyproject.toml` — it arrives
transitively. Using it directly requires declaring it (and checking `backend/requirements.txt`,
which is a second manifest in the same project).

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | The mechanism | **User-approved**: application-level symmetric encryption with Fernet (AES-CBC + HMAC), master key from `STORICO_ENCRYPTION_KEY`. Rejected: `pgcrypto` (couples to Postgres and breaks the SQLite suite) and an external KMS (infrastructure the single-VM deploy does not have). |
| D2 | Where it lives | Hexagonal, matching the architecture: a `CipherPort` in the domain and a `FernetCipher` adapter in infrastructure. The repository/adapter encrypts before persisting and decrypts on read, so no caller handles raw ciphertext by accident. |
| D3 | Ciphertext format | Version-prefixed (`v1:` + token). The prefix is what makes rotation possible later **and** is what lets the read path distinguish an encrypted value from a legacy plaintext one. |
| D4 | Legacy rows | Tolerant read: a value without the `v1:` prefix is treated as legacy plaintext and returned as-is, so the code can be deployed before the data is migrated. |
| D5 | Migration | Revision `0023` encrypts the existing plaintext rows. **Deploy order is code first, then migration**, and the reason is recorded in the migration docstring — the same hazard class recorded for `0022`: run the migration while the *previous* release is still serving and that release reads ciphertext as if it were a key. |
| D6 | Missing key | **Fail closed on write.** With no `STORICO_ENCRYPTION_KEY` configured, the app still starts and reads work, but persisting a credential is refused with a clear error rather than silently falling back to plaintext. Silently storing plaintext is exactly the state this feature exists to end. |
| D7 | Undecryptable value | An explicit, named failure — never a silent `None`. Returning `None` for a key that is present but undecryptable would be indistinguishable from "no key configured" and would surface as a misleading readiness error. Needs a defined error type and a test for the wrong-key case. |
| D8 | The GET surface | **User-approved**: `GET /settings/llm` keeps returning the decrypted key to the workspace admin, as `docs/security.md:88` documents. This feature protects data at rest, not the endpoint; the exposure surface over HTTP is unchanged and that is stated, not implied. |
| D9 | Dependency | Declare `cryptography` with the version range actually installed, in `pyproject.toml` (and reconcile `requirements.txt`). |
| D10 | Docs | `docs/security.md:98`'s pending item becomes a description of what is implemented, including where the key lives and what it does not protect against. |

## Open question to settle during implementation

Whether a startup check should warn when stored values look encrypted while no key is
configured. Cheap and useful, but it is added only if it can be done without a scan on every
boot — recorded here rather than assumed.

## Non-goals

- No key rotation tooling. The `v1:` prefix makes it possible later; implementing rotation is
  its own feature.
- No change to what the admin sees in the editor, and no masking (D8).
- No encryption of other secrets: `qdrant_api_key`, `auth_jwt_secret` and the embedding keys in
  `config/settings.py` come from the environment, not the database, and are out of scope.
- No change to the per-user settings contract, which no longer carries an LLM block at all
  (revision `0022`).

## Tasks

- [ ] Explore the full read/write path of `api_key` before changing anything: repository,
      routes, adapters, `extraction_task.py`, `cli/seed_few_shot.py`, the probe in
      `workspace_settings.py`, and every test that constructs a config with a key.
- [ ] Define `CipherPort` and the `FernetCipher` adapter; wire it through dependency injection.
- [ ] Encrypt on write, decrypt on read, tolerate legacy plaintext.
- [ ] Declare `cryptography`; confirm the pinned version matches what is installed.
- [ ] Migration `0023` encrypting existing rows, with a working `downgrade` and the deploy-order
      note in the docstring.
- [ ] Fail-closed behaviour with no key; explicit error on an undecryptable value.
- [ ] Tests: round-trip, legacy plaintext, wrong key, missing key, blank value, the probe path,
      the extraction path, and migration up/down against real Postgres.
- [ ] Correct `docs/security.md`; add the env var to `backend/.env.example`.
- [ ] Run backend `ruff check`, `ruff format --check`, `pytest -q` (including the Postgres
      integration test); frontend `tsc --noEmit` and `vitest run`.
- [ ] Work-unit commits on the feature branch.
- [ ] Independent verification.
- [ ] Fast-forward into `main`, delete the branch, re-gate.

## Evidence

_None yet._
