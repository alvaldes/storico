# ODD Feature: production state and the domain decision

## Problem

Two tracked documents stated things about production that the operator corrected on 2026-09-23, and one
recorded decision asked a question that can now be answered by measurement instead of prose.

## What the operator established

Production runs on the Oracle VM container, not on Vercel:

| Surface | URL | In use? |
| --- | --- | --- |
| Frontend | `https://storico.vercel.app` | yes |
| API | `https://storico-api.163.192.150.75.sslip.io` | **yes, this is the endpoint** |
| API (Vercel project) | `https://storico-api.vercel.app` | no — it builds and deploys, but it is not the endpoint in use |

And a decision: **no custom domain.** HTTPS is already served on both domains above, so there is nothing to
buy and nothing to renew by hand.

## The measurement that answers D5

D5 — recorded in `odd/tasks/prod-honesty-followups.md`, which lives on the unpushed
`fix/prod-honesty-followups` branch — says that four artifacts (`backend/api/index.py`,
`backend/vercel.json`, `backend/entrypoint.sh` and the `mangum` dependency) "describe a backend-on-Vercel
deployment that does not exist, but nobody has verified whether a Vercel project still points at
`backend/`".

Measured on 2026-09-23 with the authenticated Vercel CLI (`vercel projects ls`):

```
  Project Name       Latest Production URL             Updated   Node Version
  storico-api        https://storico-api.vercel.app    13m       24.x
  storico-frontend   https://storico.vercel.app        14m       24.x
```

So the Vercel project `storico-api` exists, has a production URL, and was updated minutes after this
repository's last merge — consistent with the Vercel check that runs on every pull request here. **The
artifacts D5 contemplated deleting are the build configuration of a live project**, and deleting them
would break it.

Whether that project serves real traffic is a different question, and the operator's answer is that it does
not: the endpoint in use is the VM. That distinction is the reason this record exists.

## What lands

- `docs/api.md` — the production base URL stops saying `storico-api.vercel.app (tentativo)` and names the
  endpoint that is actually in use, plus a line recording that the Vercel project deploys but is not it.
- `prod.todo.md` — the `Dominio propio + SSL` row goes 🔲 → ✅ with the decision and its reason.
- `docs/security.md` — the `Dominio personalizado + renovar SSL` checklist item closes with the same
  reason.

## Deliberately not done

- **No decision was taken about the host's visibility.** `docs/deployment.md` says, deliberately, "el host
  no se escribe acá: el workflow lo toma del secret `DEPLOY_HOST`", and this batch respects it as a norm
  for that document. `docs/api.md` needs a usable base URL, and the host is already public in this
  repository (`odd/tasks/prod-checklist-honesty.md`). If the project wants the host out of every document,
  `docs/api.md` is a second place to change, not the first — say so and it changes.
- **Nothing was deleted.** D5's artifacts stay until the Vercel project's role is decided.
- **D5's own record was not edited**: it is on a branch that is not on `main`, and editing a branch under
  review from here would mix two batches. This record is the answer that branch's record cannot yet carry.

## Verification

- The three edited claims now match the operator's answer, verified by reading each file after the edit.
- The Vercel project list came from the authenticated CLI, not from prose; the output is quoted above.
- Documentation only: no code, workflow, configuration or version manifest changed.
