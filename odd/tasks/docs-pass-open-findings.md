# Open findings for review: docs-starlight-expansion

> **Status**: **open** for items B, C and D; **item A is closed** — authorized by the owner on
> 2026-10-07 and implemented on branch `fix/llm-test-workspace-scoped` (`d50dda0`, `b9ce87d`).
> Nothing else here is in flight and nothing else is authorized work. This is a
> review agenda, not an implementation.
> **Created**: 2026-10-07
> **Workflow**: Organic Driven Development (ODD)
> **Receipt-driven development**: off in this clone.
> **Source**: the documentation pass recorded in `odd/tasks/docs-starlight-expansion.md`, merged as
> `09999c4` and verified in production. These four items are what that pass surfaced or re-confirmed
> and deliberately did **not** fix.
> **Review order suggested**: A first (it is the only one that is both new and security-shaped),
> then C, then B and D, which are re-open candidates on decisions already made.

## Problem

The pass read the product from the code to write the pages. Reading it that carefully produced four
items that are not documentation defects — they are behaviour and product decisions that the
documentation now describes truthfully. Fixing any of them is a change to the product, not to the
prose, so none was made.

## The rule that governs every item

**Each item is a decision, and the decision is the owner's.** The pass measured each one against the
code; nothing here is inferred from a document, and where a document in this repository contradicts
the code that contradiction is named rather than smoothed over. Nothing is agreed until the operator
says so, and nothing was changed in advance of that.

---

## A. `POST /api/v1/llm/test` is not workspace-scoped and does not require admin

**Status**: **CLOSED 2026-10-07** — measured as new during the docs pass, then authorized by the
owner the same day and implemented as option (a) plus the neighbouring echo fix. The measurement
below is kept as written, because it is what the decision was made against.

**The outcome, appended rather than rewritten.** The owner chose **(a) gate it**, and the route is
now `POST /api/v1/workspaces/{workspace_id}/settings/llm/test` inside the workspace settings
router, behind `require_admin`. The exact path differs from the one this item proposed
(`/workspaces/{id}/llm/test`): every other workspace LLM route lives under `/settings/llm*`, so the
probe joined that family instead of inventing a sibling prefix. The five failure branches, which
this item did not cover, stopped echoing the transport error in the same batch. Full record:
`odd/tasks/llm-test-workspace-scoped.md`. Note which document was actually false: `docs/api.md:218`
was, and so was the `prod.todo.md` row until `2e52147` corrected it; the public Starlight page
`roles-permissions.md:37` had documented the gap truthfully in both locales, and the generated
reference never claimed admin at all.

**What was measured**

| Claim | Evidence |
| --- | --- |
| The route depends only on an authenticated user | `backend/src/storico/api/routes/settings.py:147-150` (`_current_user: CurrentUserDep`), with `CurrentUserDep = Annotated[User, Depends(get_current_user)]` at `:39` |
| It has no workspace in its path, so no membership or role can be checked | `backend/src/storico/api/routes/settings.py:140-143` (`prefix="/api/v1/llm"`, route `"/test"`) |
| The caller chooses the destination host and the credential | `LLMTestRequest` carries `provider`, `base_url`, `api_key`, `model` (`backend/src/storico/api/schemas/settings.py:89-113`); the adapter is built from the body |
| The sibling probe *is* gated | `POST /api/v1/workspaces/{id}/settings/llm/models` requires the workspace and the admin role (`backend/src/storico/api/routes/workspace_settings.py:673-701`) |
| **Two documents in this repository claim the opposite** | `prod.todo.md` § Seguridad called it "admin-only"; `docs/api.md:218` says "Requiere admin". Both are wrong |
| **The application does not call it** | No caller in `frontend/src`; `odd/tasks/drop-per-user-llm-config.md` (D5) deleted the client `testLLMConnection`, `LLMTestParams`, `LLMTestResult` and the store slice **on purpose**, and kept the backend route as a documented endpoint |

**Why it matters.** The route is reachable by any authenticated user of a deployment, takes an
arbitrary host and an arbitrary credential from the request body, and makes the API process perform
an outbound request to that host. On a single-tenant self-hosted instance with closed registration
that is close to theoretical. On the deployed instance — `storico.vercel.app` with open Google and
GitHub registration — it is an authenticated-user-triggerable server-side request primitive whose
target and payload the user picks. The blast radius is not the workspace data (the route reads and
writes none); it is the API process as a network client, plus the fact that the credential it carries
is not tied to any workspace, so no audit trail in this application attributes the call to an
organization.

It also has no consumer inside the product, which changes the cost of every option: there is no UI
behaviour to preserve.

**The decision to make.** Which of these is true:

| Option | What it costs | What it buys |
| --- | --- | --- |
| (a) Gate it: require a workspace and `require_admin`, mirroring the model probe | A real behaviour change; needs tests; the route already takes credentials from the body, so the gate is about blob and audit, not about the key | Removes the primitive. Makes `docs/api.md:218` and the `prod.todo.md` row true as written |
| (b) Leave it open on purpose and document it as such | No code change; `docs/api.md:218` still has to be corrected, and the security table row rewritten as an accepted risk | Keeps a documented, cURL-able connection test — which is the stated reason the route outlived its client (`drop-per-user-llm-config.md`, D5) |
| (c) Delete the route | The endpoint disappears from `docs/api.md` and the generated `api-reference.md`; the contract it documents goes with it | Shrinks the surface, and the probe at `.../settings/llm/models` already covers the real use |

There is a fourth shape worth naming, because it is the one the sibling route already uses: keep it
reachable but **scope the probe to the workspace's own saved configuration**, so the body can no
longer choose the host. That converts the primitive into a "test my own settings" button, which is
the operation the UI actually has.

**What would close it.** The operator's choice recorded here, and — for (a) or the scoped variant —
the code change with its tests as its own feature document. For (b), two one-line corrections to
`docs/api.md:218` and the `prod.todo.md` row.

**What would not close it.** Correcting the two documents alone. They would then be true and the
primitive would remain.

---

## B. The admin's `GET /settings/llm` returns the stored API key decrypted

**Status**: ALREADY DECIDED — listed only so a future review knows it is not an oversight.

The read is admin-only, the key is encrypted at rest with Fernet, and the response returns it in
plaintext so the settings form can round-trip it. That is deliberate and already written down, with
the trade-off named, in `docs/security.md:88` ("La key sí se devuelve al **admin** del workspace: …
**Qué NO protege**: el endpoint sigue entregando la key descifrada al admin"). The behaviour is
pinned by a test whose docstring states the intent — `test_the_admin_reads_back_the_key_it_saved`,
"Encryption must be invisible to the admin who owns the credential"
(`backend/tests/test_api/test_workspace_settings_llm_config.py:375-394`). The member-readable
`GET /settings/llm/status` is deliberately narrow and never includes a value
(`backend/src/storico/api/routes/workspace_settings.py:185-206`).

**The decision to make, if the operator wants to re-open it.** Whether "admin of the workspace" is
the right trust boundary for a plaintext credential, or whether the response becomes
`api_key_set: bool` with a blind replace on write. The cost is a UI change: the field stops being
pre-filled, and "test the saved configuration" has to work without the value.

**Nothing was changed.** The docs pass documented this as the real behaviour rather than as a
finding, and the description in `docs/security.md` needed no correction.

---

## C. CSV story import: follow-ups 6, 10 and 11 are still open

**Status**: ALREADY RECORDED — the detail lives in `odd/tasks/csv-story-import.md`.

The docs pass added the missing `story-import` page in both locales. What it did **not** do is close
the three open follow-ups, and one of them bounds what that page is allowed to claim:

- **11 — the composition that serves production has never carried a real upload.** Every request goes
  through the Astro proxy (`frontend/src/lib/api.ts:7`, `frontend/src/pages/api/v1/[...path].ts`), and
  in production that file is a Vercel serverless function whose own request-body ceiling is separate
  from the backend's 2 MB `MAX_FILE_BYTES` — and unverified in this repository. The dev pass never
  exercised that hop. **This is why the new page documents the code's contract and makes no
  production claim.** The page was deferred for exactly this reason by `odd/tasks/docs-content-v2.md`,
  and this pass overrode the deferral on the owner's explicit request, not on new evidence.
- **6 — no client-side size pre-check.** A 3 MB file is uploaded and the `413` is read back.
- **10 — the duplicate accessible-name pattern is still live in five components**
  (`StoryForm.tsx`, `TaskEditor.tsx`, `StoryDetail.tsx`, `ExportPanel.tsx`, and the fixed
  `ImportStoriesDialog.tsx`).

**The decision to make.** Whether to verify the production upload path (a real multipart upload
against the deployed composition, which is the only thing that closes 11), or to accept the gap and
keep the page's scope as it is. Follow-up 11's absence is not a documentation problem; it is an
unverified seam in the product that a user could hit by uploading a large file.

**What would close it.** A measured end-to-end multipart upload against the deployed composition,
recorded with its evidence in `odd/tasks/csv-story-import.md`.

---

## D. `AGENTS.md` and `docs/deployment.md` still describe the Docker Compose dev database

**Status**: ALREADY RECORDED and **already decided not to correct** — declared at `AGENTS.md:8`.

The drift, as measured on 2026-09-30 and recorded at `AGENTS.md:8`: the section 4 stack table
(`AGENTS.md:247`), ADR-005 (`:318-319`) and feature row 40 (`:577`) all state that development runs
on Docker Compose and its PostgreSQL container. On this machine `docker` is not installed and the
development `.env` points at the Supabase pooler (`docs/deployment.md:66-111` documents Supabase as
the development database, and the comparison table at `:101` puts dev on Supabase against prod on
Neon). `docker-compose.yml` exists and does define `postgres:16-alpine`, but it is not the database
this environment connects to. What could not be established is whether that path is used on another
machine, which is why it stays a finding rather than a correction.

Two things the docs pass added to the picture without touching the files:

1. **`docs/deployment.md` contradicts itself.** Its heading and prerequisites still frame the page as
   "Desarrollo (Docker Compose)" (`:6-10`) while `:68` documents the Supabase reality. A reader who
   stops at the first screen gets the wrong setup.
2. **This is the same drift the docs pass proved is avoidable.** The pass found and fixed one false
   claim in a generated page (the duplicate-story docstring) precisely because the source of truth
   was the code. The Docker Compose claims are the same class of error and are unfixed by explicit
   decision.

**The decision to make.** Correct the four locations to describe the two supported development paths
and which one the environment actually uses, or leave them as recorded drift. If corrected, the
honest shape is: the Compose path exists in the repository and is one way to run dev; the environment
this team measures was on Supabase; say which is canonical.

---

## What this document is not

- It is **not** a plan. No scope, no branches, no tasks are authorized here.
- It is **not** a bug list. Three of the four items are decisions already taken or deliberately
  deferred; only A is a finding that was not written down anywhere before.
- It is **not** a claim that the documentation pass was incomplete. The pass closed what it was asked
  to close; these four are what it deliberately left outside its own scope, each with the reason
  above.
