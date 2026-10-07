# llm-test-workspace-scoped

> **Status**: authorized by the owner on 2026-10-07 and in progress on branch
> `fix/llm-test-workspace-scoped` off `main`. Nothing pushed.
> **Receipt-driven development**: off in this clone.
> **Source**: `odd/tasks/docs-pass-open-findings.md`, item A — the only item of that agenda that was
> a new finding rather than a re-open of an already-recorded decision.
> **Created**: 2026-10-07

## Goal

Close the authenticated-user-triggerable outbound-request primitive that `POST /api/v1/llm/test`
is today, and close the second open row that lives in the same five branches — the transport error
echo — in the same two work units.

## Problem, measured

| Claim | Evidence |
| --- | --- |
| The route depends only on an authenticated user | `backend/src/storico/api/routes/settings.py:147-150` (`_current_user: CurrentUserDep`), with `CurrentUserDep = Annotated[User, Depends(get_current_user)]` at `:39` |
| It has no workspace in its path, so no membership or role can be checked | `backend/src/storico/api/routes/settings.py:140-143` (`prefix="/api/v1/llm"`), route `"/test"` at `:146` |
| The caller chooses the destination host and the credential | `LLMTestRequest` carries `provider`, `base_url`, `api_key`, `model` (`backend/src/storico/api/schemas/settings.py:89-113`); the adapter is built from the body |
| The request path is host-arbitrary, not path-arbitrary | the suffix is the adapter's: `{base_url}/api/chat` (`infrastructure/llm/ollama_adapter.py:72`), `/chat/completions` and `/v1/messages` appended by the OpenAI and Anthropic SDKs (`openai_adapter.py:51`, `anthropic_adapter.py:41`) |
| The sibling probe **is** gated | `POST /workspaces/{id}/settings/llm/models` requires the workspace and the admin role (`backend/src/storico/api/routes/workspace_settings.py:674-681`) |
| Five branches echo the transport error into the response | `settings.py:146-337`, one `except Exception as e` per branch, each building `message=f"... connection failed: {e}"` |
| The application does not call it | no caller in `frontend/src`; `odd/tasks/drop-per-user-llm-config.md` (D5) deleted the client `testLLMConnection`, `LLMTestParams`, `LLMTestResult` and the store slice **on purpose**, and kept the backend route as a documented endpoint |
| No test pins the laxness | `backend/tests/test_api/test_llm_test_route.py` — 10 tests across five classes covering blank credentials, blank endpoints, real values, custom providers and the provider name. Zero authorization tests |

**Why it matters.** On a single-tenant self-hosted instance with closed registration this is close to
theoretical. On the deployed instance — `storico.vercel.app`, with open Google and GitHub
registration — any person who can create a Google account holds a token that makes the production
API container emit an outbound request to a host of their choosing. The container runs
`--network host`, so "arbitrary host" reaches Caddy, the container's own port 8000 and the VM's
loopback. The blast radius is not workspace data (the route reads and writes none); it is the API
process as a network client, plus the absence of any workspace row that would attribute the call.
It also has no consumer inside the product, so there is no UI behaviour to preserve.

**One premise not measured, and therefore not claimed.** Whether the `{e}` echo turns this into a
read primitive against an internal service depends on what each SDK puts in its exception message.
That was not measured. It is the reason WU2 exists rather than being deferred: the echo is a second,
independent way the route hands dependency-controlled text to an unauthenticated-in-practice caller.

## The owner's decision

**Option (a): gate it.** The route becomes workspace-scoped and admin-gated, mirroring the sibling
model probe, and keeps its documented operator capability — a `cURL`-able connection test that D5
deliberately preserved.

The other three options and why they lost:

| Option | Why not |
| --- | --- |
| (b) Leave it open and document it as an accepted risk | The only option that leaves the primitive standing on a deployment with open registration. Its whole cost was one line in `docs/api.md:218`, which makes it cheap but not safe |
| (c) Delete the route | Defensible and it shrinks the system, but it discards a capability D5 kept on purpose. The sibling proves the *config*, not that a `Hello` round-trips through the adapter extraction uses |
| (d) Scope the probe to the workspace's saved configuration | Turns out to be nearly a duplicate: the sibling with no body already probes the saved config, under an admin gate, without the echo. It would have added a second route to say almost the same thing |

**Exact path: `POST /api/v1/workspaces/{workspace_id}/settings/llm/test`.** This is a deliberate
narrowing of the shape proposed when the owner chose (a): the proposal read
`POST /api/v1/workspaces/{id}/llm/test`, and every other workspace LLM route in this repository
lives under `/workspaces/{id}/settings/llm*` (`docs/api.md:203-208`), so the route joins that
family instead of inventing a sibling prefix. The `settings` segment is not an accident of the
probe: the sibling at `/settings/llm/models` also tests a *pending* selection, not the saved one.

## Scope

- `frontend/src/content/docs/es/docs/roles-permissions.md:37` and its `en` twin — the bullet that
  documents the gap stops being true and is folded into the permission table.
- `frontend/src/content/docs/{en,es}/docs/llm-providers.md:72` — the new path, and the claim that the
  response carries "the connection error message" is withdrawn.
- `frontend/src/content/docs/{en,es}/docs/api-reference.md:296` — regenerated from the app, never
  hand-edited.
- `docs/api.md:208` (path) and `:218` ("Requiere admin", which is the one false sentence left after
  `2e52147` corrected the other).
- `prod.todo.md:74-75` — both rows, closed with their evidence.
- `odd/tasks/docs-pass-open-findings.md`, item A — the decision and its outcome recorded in place.

## Non-goals

- **Not** removing the credential from the request body. The route's documented purpose is testing
  credentials *before* they are saved; a body is the transport for that, and the sibling does the
  same (D3 in `odd/tasks/llm-model-probe-selection.md`). The change is about *who* may call it and
  *what* comes back, not about where the credential travels.
- **Not** changing `LLMTestResponse`, the normalization rules, or the provider branches.
- **Not** touching the member-readable `GET /settings/llm/status`, or the admin-only plaintext read
  at `GET /settings/llm` (item B of the agenda, already decided).
- **Not** the frontend. There is no consumer to update.

## Tasks

- [x] **WU1 — Relocate the route and gate it.** Move `test_llm_connection` and its body out of
  `api/routes/settings.py` into `api/routes/workspace_settings.py`, mounted on the existing
  `/api/v1/workspaces/{workspace_id}/settings` router, and swap `_current_user: CurrentUserDep` for
  `ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin)`. Delete `test_router` and its
  `app.include_router` line (`api/app.py:202`). The five provider branches keep their behaviour
  exactly. Tests: the existing 10 move to the new URL with an admin workspace from `seed_workspace`;
  new tests for 401 without a session, 403 `ADMIN_ACCESS_REQUIRED` for a member, and 403
  `NOT_A_WORKSPACE_MEMBER` for a non-member. Schemas stay in `api/schemas/settings.py` — moving them
  is churn this fix does not need — with their docstrings corrected to the new path. The generated
  reference (`frontend/src/content/docs/{en,es}/docs/api-reference.md`) is regenerated **in this same
  commit**, not in WU3: the drift guard compares committed bytes against a fresh render, so leaving
  it for the docs work unit would have left the tree red in between.
- [ ] **WU2 — Stop echoing the transport error.** One shared helper that classifies a transport
  failure into something this application owns (`HTTP {status}`, or "the provider could not be
  reached"), with the exception text going to the log at `logger.warning(..., exc_info=e)`. Used by
  the five branches of the moved route **and** by the models probe, whose inline version of the same
  logic at `workspace_settings.py:698-720` becomes the first caller. Tests: an adapter that raises
  with a marker in its message must not put that marker in the response, and must put it in the log.
- [ ] **WU3 — Docs, checklist and agenda.** The prose documentation locations in Scope, the two
  `prod.todo.md` rows, and item A of the review agenda. The generated reference already landed in
  WU1.

## Constraints

- The path change is a **breaking change to a public contract** that has no consumer. It is committed
  as `fix(api): ...` and the break is named here rather than marked with `!`, because a `!` would
  make the next `make bump` cut `1.0.0` — the number the roadmap reserved for observability
  (`prod.todo.md` § Observabilidad). **This is the owner's call to override before the next bump.**
- `backend/tests/test_api_reference.py` compares the committed pages against a fresh render, so the
  reference is regenerated with
  `conda run -n storico python -m storico.scripts.render_api_reference`, never edited by hand.
- `frontend/src/i18n/__tests__/docs-content.test.ts` guards locale parity and internal links, so both
  locales change together or the frontend suite fails.
- ADR-008: the Spanish UI/docs are neutral international Spanish. The `es` pages are not voseo.

## Evidence log

| Work unit | Commit | Evidence |
| --- | --- | --- |
| WU1 — relocate and gate | `d50dda0` | RED observed first, test file edited before any implementation edit: `pytest tests/test_api/test_llm_test_route.py -q` → **19 failed**, every failure a 404 on the new path (the route had no home there yet). GREEN after the move: same command → **19 passed**; `pytest -q -m unit` → **302 passed, 1038 deselected**; `ruff check src tests` and `ruff format --check src tests` clean (ruff caught two imports the deletion orphaned). Parent's independent spot check, run after the writer returned: the 180-line body diffed mechanically against `HEAD:backend/src/storico/api/routes/settings.py` is **byte-identical**; the 10 pre-existing tests changed only their client/URL plumbing, with assertions untouched; and after regenerating both locales, `pytest tests/test_api/test_llm_test_route.py tests/test_api_reference.py -q` → **24 passed**. |

## Limitations carried forward

- The echo fix removes our application's *own* contribution to the leak. It does not audit the
  adapters' exception messages for the same class of text, and it does not verify whether an SDK's
  error text ever contained a credential. That stays unmeasured, and this document does not claim
  otherwise.
- The route remains reachable by any **admin of any workspace they belong to**, which is the trust
  boundary the sibling already uses. Whether that is the right boundary for a credential the caller
  types is the same question item B of the agenda leaves open for the stored key.
