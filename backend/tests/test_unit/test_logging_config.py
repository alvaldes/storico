"""Behavioural contract for the API factory's logging configuration.

The defect these tests guard: under plain ``uvicorn storico.api.app:create_app
--factory``, the process configured no logging at all — uvicorn's own
``dictConfig`` leaves the root logger at WARNING with no handler, so every
``storico.*`` INFO record propagated to nothing and ``logging.lastResort``
dropped it in silence.

Every assertion here is on OBSERVED logging behaviour (records that actually
reach a handler), never on a logger's ``.level`` attribute: a level can look
right while the record still goes nowhere.
"""

from __future__ import annotations

import importlib
import logging

import pytest
from pydantic import ValidationError

import storico.api.app
from storico.api.app import create_app
from storico.config.settings import _reset_settings_cache

# The state plain uvicorn leaves the process in: root at WARNING with no
# handler, so application records die at ``logging.lastResort``. The fixtures
# below reproduce it so the tests exercise the same conditions as production.
PRODUCTION_ROOT_LEVEL = logging.WARNING


class RecordingHandler(logging.Handler):
    """Handler that records every emitted record, for behavioural assertions."""

    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def fresh_root_logger():
    """Snapshot the root logger, reset it to the plain-uvicorn state, restore.

    ``create_app()`` owns the root logger for the rest of the process once it
    has run (``dictConfig`` replaces handlers), so without the restore one
    test's configuration would leak into every other test in the suite.
    """
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    saved_disabled = root.disabled

    root.handlers.clear()
    root.setLevel(PRODUCTION_ROOT_LEVEL)
    root.disabled = False
    try:
        yield root
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
        root.disabled = saved_disabled


@pytest.fixture
def clean_settings_cache():
    """Isolate the settings lru_cache around tests that patch the env."""
    _reset_settings_cache()
    try:
        yield
    finally:
        _reset_settings_cache()


def _probe(level: int, message: str) -> None:
    logging.getLogger("storico.test_probe").log(level, message)


def _messages(handler: RecordingHandler) -> list[str]:
    return [record.getMessage() for record in handler.records]


def test_application_info_records_are_emitted_after_create_app(fresh_root_logger):
    """The defect itself: a storico.* INFO record must survive create_app()."""
    create_app()

    capture = RecordingHandler()
    fresh_root_logger.addHandler(capture)

    _probe(logging.INFO, "extraction marker")

    assert "extraction marker" in _messages(capture), (
        "a storico.* INFO record was discarded after create_app(): the process "
        "configured no logging, exactly the production defect this module guards"
    )


def test_a_record_is_emitted_exactly_once(fresh_root_logger):
    """One record produces exactly ONE emission: neither zero nor two."""
    create_app()

    root = logging.getLogger()
    emissions = 0
    wrapped: list[tuple[logging.Handler, object]] = []
    for handler in list(root.handlers):
        original = handler.emit

        def counting_emit(record: logging.LogRecord, _original=original) -> None:
            nonlocal emissions
            emissions += 1
            _original(record)

        handler.emit = counting_emit  # type: ignore[method-assign]
        wrapped.append((handler, original))

    try:
        _probe(logging.INFO, "exactly once")
    finally:
        for handler, original in wrapped:
            handler.emit = original  # type: ignore[method-assign]

    assert emissions == 1, (
        f"a single record produced {emissions} handler emissions; the record must "
        f"reach exactly one configured handler"
    )

    # And the application logger chain itself must not own a handler that would
    # duplicate every record beside the root's.
    assert logging.getLogger("storico").handlers == []
    assert logging.getLogger("storico").propagate is True


def test_importing_the_module_does_not_configure_logging(fresh_root_logger):
    """Importing storico.api.app must leave logging untouched.

    ``importlib.reload`` is used instead of a subprocess because this module
    (and the test session's conftest) already has ``storico.api.app`` in
    ``sys.modules`` — a plain import would be a no-op and prove nothing.
    Reload re-executes the module body, which is exactly the code path that
    must not configure logging, without bootstrapping a subprocess.
    """
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    level_before = root.level

    importlib.reload(storico.api.app)

    assert root.handlers == handlers_before, (
        "importing storico.api.app installed a handler on the root logger: "
        "logging must only be configured inside create_app()"
    )
    assert root.level == level_before, (
        "importing storico.api.app changed the root logger's level: logging "
        "must only be configured inside create_app()"
    )


def test_create_app_twice_does_not_stack_handlers(fresh_root_logger):
    """Idempotency: a second create_app() must not stack handlers."""
    create_app()
    handlers_after_first = list(logging.getLogger().handlers)

    create_app()

    root = logging.getLogger()
    assert len(root.handlers) == len(handlers_after_first), (
        f"calling create_app() twice stacked handlers: {len(handlers_after_first)} "
        f"after the first call, {len(root.handlers)} after the second"
    )

    capture = RecordingHandler()
    root.addHandler(capture)
    _probe(logging.INFO, "second call marker")
    assert _messages(capture) == ["second call marker"], (
        "after a second create_app() the record was not emitted exactly once"
    )


def test_storico_log_level_warning_suppresses_info(
    fresh_root_logger, monkeypatch, clean_settings_cache
):
    """With STORICO_LOG_LEVEL=WARNING an INFO record is suppressed."""
    monkeypatch.setenv("STORICO_LOG_LEVEL", "WARNING")
    create_app()

    capture = RecordingHandler()
    logging.getLogger().addHandler(capture)

    _probe(logging.INFO, "suppressed marker")
    _probe(logging.WARNING, "emitted marker")

    assert "suppressed marker" not in _messages(capture)
    assert "emitted marker" in _messages(capture)


def test_storico_log_level_info_emits_both(fresh_root_logger, monkeypatch, clean_settings_cache):
    """With STORICO_LOG_LEVEL=INFO both INFO and WARNING records are emitted."""
    monkeypatch.setenv("STORICO_LOG_LEVEL", "INFO")
    create_app()

    capture = RecordingHandler()
    logging.getLogger().addHandler(capture)

    _probe(logging.INFO, "info marker")
    _probe(logging.WARNING, "warning marker")

    assert "info marker" in _messages(capture)
    assert "warning marker" in _messages(capture)


def test_invalid_storico_log_level_fails_loudly(monkeypatch, clean_settings_cache):
    """A typo'd level name must fail loudly, naming the offending value."""
    monkeypatch.setenv("STORICO_LOG_LEVEL", "LOUD")

    with pytest.raises(ValidationError) as excinfo:
        create_app()

    assert "LOUD" in str(excinfo.value)


def test_the_lazy_module_app_is_a_singleton(fresh_root_logger):
    """Repeated access to ``storico.api.app.app`` hands out ONE instance.

    The module used to bind ``app = create_app()`` at import time. Moving that
    binding behind a PEP 562 ``__getattr__`` — which is what stops importing the
    module from configuring logging — creates an obligation of its own:
    ``__getattr__`` is consulted on every miss, so a version that merely returns
    ``create_app()`` builds a fresh FastAPI application per access, and each of
    those also re-runs the logging configuration. The first access must write the
    instance back into the module namespace so later ones read the global.
    """
    # ``reload`` re-executes the module body in the SAME namespace, so a
    # ``app`` materialized by an earlier test would survive it and this test
    # would pass without exercising the first access at all.
    module = importlib.reload(storico.api.app)
    module.__dict__.pop("app", None)

    first = module.app
    second = module.app

    assert first is second, (
        "each access to storico.api.app.app built a separate FastAPI application; "
        "the previous module-level binding handed out a single instance"
    )
    assert vars(module)["app"] is first, (
        "the lazy attribute was not materialized into the module namespace, so "
        "every later access would run create_app() again"
    )
