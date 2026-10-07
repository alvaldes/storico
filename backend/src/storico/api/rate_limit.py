"""The in-application rate limiter — limiter, key, tiers, exemptions, 429 handler.

Everything the limiter decides lives in this module: the key function, the
per-endpoint tier table, the health exemptions and the canonical 429 envelope.
Route files carry no rate-limit code.

## Why the limiter is built inside ``create_app()``, never at import

A module-level ``Limiter`` keeps its in-memory counters across every app
instance a test builds: two apps in one pytest process would share buckets and
flakily trip each other's limits. Building it in the factory gives every app
its own ``memory://`` storage — correct for the one-container deployment this
is (a second container would double every effective limit; that trade is
recorded in ``odd/tasks/rate-limiting.md``, not hidden).

## Shape: factory-built limiter + one global dispatch dependency

slowapi's canonical FastAPI usage decorates route functions with
``limiter.limit(...)`` at import time, which forces a module-level limiter —
exactly what the factory requirement forbids. The shape chosen instead:

1. ``create_app()`` builds the limiter and registers the tier limits and the
   health exemptions on it, using slowapi's own public ``limiter.limit`` /
   ``limiter.exempt`` APIs applied as plain calls (the wrappers they return are
   discarded — only the registration matters, see ``build_rate_limiter``).
2. A single global dependency (``check_rate_limit``, registered on the app
   itself) dispatches every request through slowapi's own checking routine,
   ``Limiter._check_request_limit(request, handler, in_middleware=False)``.
   That single call performs the whole decision with slowapi's own logic:
   registered tier limits for the endpoints in the table, the default read
   limit for everything else, and an early return for the exempted health
   routes. No bucket arithmetic lives here.

The dependency runs before every auth dependency (app-level dependencies
resolve first in FastAPI), so unauthenticated requests count against the
limiter too — an anonymous hammer is still a hammer. slowapi's own
``SlowAPIMiddleware`` was not usable: its route lookup walks a flat
``app.routes`` list, and this FastAPI version wraps routes in
``_IncludedRouter`` containers the helper cannot resolve — it silently returns
``None`` and the limiter never trips. The global dependency sidesteps route
walking entirely: by the time dependencies run, routing has set
``scope["endpoint"]``. The one slowapi internal still relied on
(``_check_request_limit``) is why ``slowapi`` is pinned ``>=0.1.10,<0.2`` in
``pyproject.toml``: a major bump would be free to reshape it, and the tests in
``tests/test_api/test_rate_limiting.py`` would catch a silent change.

## The key: verified subject, else client address

The bucket key is the JWT ``sub`` **when the token verifies** with this
project's own verification parameters (the PyJWT decode with
``settings.auth_jwt_secret`` and ``HS256`` that ``api/dependencies.py:105-115``
runs in ``get_current_user``); an invalid, expired or absent token falls back
to the client address. The fallback is deliberate: a naive implementation that
reads ``sub`` without verifying lets any caller mint unlimited fresh buckets
just by rotating garbage tokens. The address the backend sees for proxied
traffic is the Vercel serverless function's (the proxy builds headers from
scratch and does not forward the client's address), so the fallback bucket is
coarse — that is the accepted trade recorded in ``odd/tasks/rate-limiting.md``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import jwt as pyjwt
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from storico.api.error_codes import RATE_LIMIT_EXCEEDED
from storico.api.routes import extraction as extraction_routes
from storico.api.routes import health as health_routes
from storico.api.routes import stories as stories_routes
from storico.api.routes import tasks as tasks_routes
from storico.api.routes import workspace_settings as workspace_settings_routes
from storico.config.settings import Settings, get_settings

__all__ = [
    "build_rate_limiter",
    "check_rate_limit",
    "rate_limit_exceeded_handler",
    "rate_limit_key",
]


def rate_limit_key(request: Request) -> str:
    """Return the limiter bucket key: the verified JWT subject, else the address.

    Mirrors the verification ``get_current_user`` performs
    (``api/dependencies.py:105-115``): the same secret, the same ``HS256``
    allow-list, and PyJWT's own expiry check. Anything that does not verify —
    malformed, wrong secret, expired, missing ``sub`` — lands in the caller's
    address bucket instead of minting a per-identity one. The ``user:`` /
    ``ip:`` prefixes keep a subject string from ever colliding with an address.

    This runs before authentication on every request, so it must never raise.
    """
    auth_header = request.headers.get("Authorization") or ""
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        try:
            payload = pyjwt.decode(token, get_settings().auth_jwt_secret, algorithms=["HS256"])
        except Exception:  # noqa: BLE001 — any verification failure is the same fallback
            payload = {}
        sub = payload.get("sub")
        if sub:
            return f"user:{sub}"
    host = request.client.host if request.client is not None else "unknown"
    return f"ip:{host}"


def _tiered_limits(settings: Settings) -> list[tuple[Callable[..., Any], str]]:
    """The per-endpoint tier table — the limits that are stricter than reads.

    Declarative and centralized here on purpose: each row names the endpoint
    function and the ``Settings``-backed limit it rides. Reads (the default
    limit passed to the ``Limiter``) apply to everything not in this table and
    not exempt. The writes tier rides ``update_task`` because that is the one
    endpoint the status/labels/dependencies writes go through (the D5/D21 field
    matrix); the probe tier covers both LLM probe routes.
    """
    return [
        (
            extraction_routes.extract_tasks,
            f"{settings.rate_limit_extraction_per_minute}/minute",
        ),
        (
            stories_routes.import_stories,
            f"{settings.rate_limit_import_per_minute}/minute",
        ),
        (
            workspace_settings_routes.list_available_models,
            f"{settings.rate_limit_probes_per_minute}/minute",
        ),
        (
            workspace_settings_routes.test_llm_connection,
            f"{settings.rate_limit_probes_per_minute}/minute",
        ),
        (
            tasks_routes.update_task,
            f"{settings.rate_limit_writes_per_minute}/minute",
        ),
    ]


# The health routes are exempt unconditionally — there is no setting that could
# turn this off, because the deployment's own readiness gate polls
# /health/ready in a bounded ``curl -sf`` loop (.github/workflows/
# deploy-backend.yml): a limit there would fail the deploy, not just the caller.
_EXEMPT_ENDPOINTS: tuple[Callable[..., Any], ...] = (
    health_routes.health,
    health_routes.health_services,
    health_routes.health_ready,
)


def build_rate_limiter(settings: Settings) -> Limiter:
    """Build the app-owned limiter: default read tier, endpoint tiers, exemptions.

    ``key_style="endpoint"`` scopes each bucket to the endpoint function rather
    than the concrete URL, so one user extracting against ten stories spends
    one 10/min extraction bucket, not ten of them — the per-key numbers in
    ``odd/tasks/rate-limiting.md`` are per route, not per URL.

    ``limiter.limit`` / ``limiter.exempt`` are applied as plain calls so the
    registrations land on this app's limiter; the returned wrappers are
    discarded because the check is performed by ``RateLimitMiddleware`` through
    slowapi's own routine, not by slowapi's per-route decorators.
    """
    limiter = Limiter(
        key_func=rate_limit_key,
        default_limits=[f"{settings.rate_limit_reads_per_minute}/minute"],
        key_style="endpoint",
    )
    for endpoint, limit in _tiered_limits(settings):
        limiter.limit(limit)(endpoint)
    for endpoint in _EXEMPT_ENDPOINTS:
        limiter.exempt(endpoint)
    return limiter


async def rate_limit_exceeded_handler(
    request: Request,
    exc: RateLimitExceeded,
) -> JSONResponse:
    """Map a tripped limit to the canonical error envelope with a 429.

    slowapi's default body (``{"error": "Rate limit exceeded: ..."}``) is not
    the shape any other error in this API uses, so the handler emits the same
    ``detail`` + ``error_code`` envelope every other handler in
    ``api/errors.py`` emits. ``detail`` is a fixed, calm instruction — the
    machine contract is the code, and slowapi's own limit description carries
    no information a client can act on beyond what the code already says.
    """
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Too many requests. Slow down and retry shortly.",
            "error_code": RATE_LIMIT_EXCEEDED,
        },
    )


async def check_rate_limit(request: Request) -> None:
    """Dispatch one request through slowapi's own limit-checking routine.

    Registered as a global app dependency (see ``create_app``), so it runs
    before every auth dependency and counts requests that later fail with
    401 as well. One line of policy, zero bucket arithmetic: the exemption
    check, the tier lookup and the hit itself all happen inside
    ``Limiter._check_request_limit`` (see the module docstring for why the
    global dependency instead of slowapi's middleware, and the meaning of
    ``in_middleware=False``). A tripped limit raises here, and the app's
    registered handler turns it into the canonical 429 envelope.
    """
    limiter: Limiter = request.app.state.limiter
    if not limiter.enabled:
        return
    # Routing has resolved the endpoint by the time dependencies run; passing
    # it lets slowapi find this endpoint's tier limits and exemptions.
    limiter._check_request_limit(request, request.scope.get("endpoint"), in_middleware=False)
