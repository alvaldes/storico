"""Contract tests: every ``STORICO_*`` name published to a reader must be a real setting.

``Settings`` declares ``env_prefix="STORICO_"`` together with ``extra="ignore"``, so an env
variable whose name matches no field is discarded **in silence**: no error, no warning, and
the field keeps its default. That is exactly how ``STORICO_OLLAMA_BASE_URL`` shipped in
``docker-compose.yml`` and in the README table while the real field (``ollama_host``) stayed
at ``http://localhost:11434`` — which, inside the API container, is the API container itself,
so the Quick Start ``make up`` path could not reach the ``storico-ollama`` service at all.

These tests pin the naming contract on the two surfaces a reader actually configures from.
They parse with ``re`` + ``pathlib`` only: ``pyyaml`` is not a declared dependency of this
project (nothing lists it under ``Required-by``), so a YAML import here would make the suite
depend on whatever happens to be installed.

A test that cannot find its subject fails: it never skips.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from storico.config.settings import Settings

# backend/tests/test_unit/test_env_contract.py → repository root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMPOSE_PATH = _REPO_ROOT / "docker-compose.yml"
_README_PATH = _REPO_ROOT / "README.md"

# The two environment templates a reader configures from: the repo-root file (the Quick
# Start source, ``cp .env.example .env``) and the backend reference, which documents the
# same names from the backend's point of view.
_ROOT_ENV_TEMPLATE = _REPO_ROOT / ".env.example"
_BACKEND_ENV_TEMPLATE = _REPO_ROOT / "backend" / ".env.example"
_ENV_TEMPLATES = (_ROOT_ENV_TEMPLATE, _BACKEND_ENV_TEMPLATE)

# `STORICO_FOO: value` in a compose mapping — key anchored at any indentation so it cannot
# be widened into a tautology by an unrelated edit.
_COMPOSE_KEY_RE = re.compile(r"^\s*(?P<key>STORICO_[A-Z0-9_]+):", re.MULTILINE)

# `  storico-api:` — a compose service header (exactly two spaces of indentation).
_SERVICE_HEADER_RE = re.compile(r"^  (?P<name>[A-Za-z0-9_-]+):\s*$", re.MULTILINE)

# `      STORICO_FOO: value` — an entry of a compose `environment:` mapping.
_ENV_ENTRY_RE = re.compile(r"^\s+(?P<key>STORICO_[A-Z0-9_]+):\s*(?P<value>\S+)\s*$", re.MULTILINE)

# `| `STORICO_FOO`` — a row of a markdown table, and only a table row.
_README_ROW_RE = re.compile(r"^\|\s*`(?P<key>STORICO_[A-Z0-9_]+)`", re.MULTILINE)

# `STORICO_FOO=...` or `# STORICO_FOO=...` — an assignment in either the active or the
# commented-out style these two templates mix. The trailing `=` is load-bearing: a prose
# line that merely names the prefix (``... use prefix STORICO_ (pydantic-settings ...)``)
# carries no assignment and must not be read as configuration.
_ENV_TEMPLATE_KEY_RE = re.compile(r"^\s*#?\s*(?P<key>STORICO_[A-Z0-9_]+)\s*=", re.MULTILINE)

# Names this repository retired. Each one was published to users and configured nothing,
# because no field carries it and `extra="ignore"` throws the value away.
_RETIRED_NAMES = (
    "STORICO_OLLAMA_BASE_URL",  # typo for STORICO_OLLAMA_HOST
    "STORICO_REDIS_URL",  # Redis left with Celery
    "STORICO_DEBUG",
    "STORICO_APP_NAME",
)

# The names the Qdrant + few-shot feature needs a reader to be able to set. The root
# template is the Quick Start source and must publish the whole block; the backend
# reference was the only place two of them were documented at all.
_FEATURE_KEYS_BY_TEMPLATE: dict[Path, tuple[str, ...]] = {
    _ROOT_ENV_TEMPLATE: (
        "STORICO_OLLAMA_HOST",
        "STORICO_QDRANT_URL",
        "STORICO_QDRANT_API_KEY",
        "STORICO_QDRANT_COLLECTION",
        "STORICO_EMBEDDING_PROVIDER",
        "STORICO_EMBEDDING_MODEL",
        "STORICO_EMBEDDING_DIMENSIONS",
        "STORICO_ENCRYPTION_KEY",
    ),
    _BACKEND_ENV_TEMPLATE: (
        "STORICO_OLLAMA_HOST",
        "STORICO_EMBEDDING_PROVIDER",
    ),
}


def _read(path: Path) -> str:
    """Read a contract subject, failing loudly when the repository layout moved."""
    assert path.is_file(), (
        f"Contract subject not found at {path}. The repository root resolved from "
        f"{__file__} to {_REPO_ROOT}; fix the root resolution in this test instead of "
        f"letting the contract pass unchecked."
    )
    return path.read_text(encoding="utf-8")


def _service_block(compose: str, service: str) -> str:
    """Return the text of one compose service, up to the next service header."""
    headers = list(_SERVICE_HEADER_RE.finditer(compose))
    for index, header in enumerate(headers):
        if header.group("name") != service:
            continue
        end = headers[index + 1].start() if index + 1 < len(headers) else len(compose)
        return compose[header.end() : end]
    raise AssertionError(
        f"Service {service!r} not found in {_COMPOSE_PATH}: found "
        f"{[header.group('name') for header in headers]}"
    )


def _unknown(keys: list[str]) -> list[str]:
    """The subset of ``STORICO_*`` names that maps to no ``Settings`` field."""
    return sorted(
        key for key in keys if key.removeprefix("STORICO_").lower() not in Settings.model_fields
    )


def test_every_compose_env_key_names_a_real_setting() -> None:
    """A compose key that names no field sets nothing, and says nothing about it."""
    compose = _read(_COMPOSE_PATH)

    keys = _COMPOSE_KEY_RE.findall(compose)

    assert keys, (
        f"No STORICO_* environment keys matched in {_COMPOSE_PATH}. The compose file does "
        f"set them, so an empty match means this regex stopped matching, not that the file "
        f"became clean — assert on the extraction before trusting the result."
    )

    unknown = _unknown(keys)

    assert not unknown, (
        f"{_COMPOSE_PATH} sets {unknown}, which name no Settings field. pydantic-settings "
        f"discards them silently (extra='ignore'), so the container starts on defaults. "
        f"A real field: {sorted(Settings.model_fields)}"
    )


def test_the_api_service_can_reach_ollama_from_inside_its_container() -> None:
    """The compose value that reaches Ollama must not name the API container itself."""
    compose = _read(_COMPOSE_PATH)

    environment = {
        match.group("key"): match.group("value").strip("\"'")
        for match in _ENV_ENTRY_RE.finditer(_service_block(compose, "storico-api"))
    }

    assert "STORICO_OLLAMA_HOST" in environment, (
        f"the storico-api service in {_COMPOSE_PATH} does not set STORICO_OLLAMA_HOST "
        f"(it sets {sorted(environment)}), so ollama_host falls back to "
        f"http://localhost:11434 — the API container itself."
    )

    host = environment["STORICO_OLLAMA_HOST"]

    assert not re.match(r"^(https?://)?(localhost|127\.0\.0\.1)(:\d+)?(/|$)", host), (
        f"the storico-api service in {_COMPOSE_PATH} points STORICO_OLLAMA_HOST at "
        f"{host!r}. Inside a container that address is the container itself, so the "
        f"storico-ollama service is unreachable; address it by its compose service name."
    )


def test_every_readme_table_variable_names_a_real_setting() -> None:
    """A documented variable that names no field configures nothing for the reader."""
    readme = _read(_README_PATH)

    keys = _README_ROW_RE.findall(readme)

    assert keys, (
        f"No `STORICO_*` table rows matched in {_README_PATH}. The environment table does "
        f"list them, so an empty match means this regex stopped matching, not that the "
        f"table became clean — assert on the extraction before trusting the result."
    )

    unknown = _unknown(keys)

    assert not unknown, (
        f"{_README_PATH} documents {unknown} in a table row, which name no Settings field. "
        f"A reader who sets them configures nothing. A real field: "
        f"{sorted(Settings.model_fields)}"
    )


@pytest.mark.parametrize("retired_name", _RETIRED_NAMES)
def test_a_retired_env_name_appears_in_neither_surface(retired_name: str) -> None:
    """The regression guard for the class of bug, name by name, surface by surface."""
    for path in (_COMPOSE_PATH, _README_PATH):
        content = _read(path)

        assert retired_name not in content, (
            f"{retired_name} is published in {path}, but no Settings field carries that "
            f"name, so setting it does nothing while looking like configuration."
        )


def _env_template_keys(path: Path) -> list[str]:
    """The ``STORICO_*`` names an env template assigns, commented out or not."""
    return _ENV_TEMPLATE_KEY_RE.findall(_read(path))


def _template_id(path: Path) -> str:
    """A stable, readable pytest id for a template path."""
    return str(path.relative_to(_REPO_ROOT))


@pytest.mark.parametrize("path", _ENV_TEMPLATES, ids=_template_id)
def test_every_env_template_key_names_a_real_setting(path: Path) -> None:
    """A key published in an env template that names no field sets nothing, silently."""
    keys = _env_template_keys(path)

    assert keys, (
        f"No STORICO_* keys matched in {path}. The template does set them, so an empty "
        f"match means this regex stopped matching, not that the template became clean — "
        f"assert on the extraction before trusting the result."
    )

    unknown = _unknown(keys)

    assert not unknown, (
        f"{path} publishes {unknown}, which name no Settings field. pydantic-settings "
        f"discards them silently (extra='ignore'), so a reader who sets them configures "
        f"nothing. A real field: {sorted(Settings.model_fields)}"
    )


def test_env_template_extraction_ignores_prose_that_names_the_prefix() -> None:
    """A prose mention of the prefix carries no assignment and is not configuration.

    The extraction regex above is only safe because of its trailing ``=``. Without it,
    the header prose of the root template (which names ``STORICO_`` while explaining the
    prefix) would extract a bogus, fieldless key and the contract would fail on its own
    documentation. This pins that property to the template's current wording.
    """
    prose = "# Backend vars use prefix STORICO_ (pydantic-settings requirement)."

    assert prose in _read(_ROOT_ENV_TEMPLATE), (
        f"{_ROOT_ENV_TEMPLATE} no longer carries the prose line this test guards, so the "
        f"check lost its subject; update the literal to the template's current wording."
    )

    assert _ENV_TEMPLATE_KEY_RE.findall(prose) == [], (
        f"the template key regex matched the prose line {prose!r}, so it would read the "
        f"prefix explanation as a setting name."
    )


@pytest.mark.parametrize("path", _ENV_TEMPLATES, ids=_template_id)
def test_env_template_publishes_the_qdrant_few_shot_keys(path: Path) -> None:
    """The template a reader copies must publish every name the feature needs to be on."""
    published = set(_env_template_keys(path))
    missing = sorted(set(_FEATURE_KEYS_BY_TEMPLATE[path]) - published)

    assert not missing, (
        f"{path} does not publish {missing}, so a reader who copies this template cannot "
        f"enable the Qdrant + few-shot feature. Published keys: {sorted(published)}"
    )
