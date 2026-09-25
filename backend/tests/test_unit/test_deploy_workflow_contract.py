"""Contract tests: the deploy workflow's disk cleanup stays bounded and ordered.

Nothing else in the repository reads `.github/workflows/deploy-backend.yml`, so every invariant it
carries lives in a shell script that no test executes. These tests pin the three that are
load-bearing for the VM's disk:

- the image prune is **dangling-only**, so ``storico-api:previous`` — the only rollback the deploy
  leaves — survives by construction rather than by luck;
- the build-cache prune keeps a **bounded window**, because the cache is what stops the dependency
  layer from being rebuilt from scratch on every deploy;
- both run **after the readiness gate**, so ``set -e`` aborts before them when a deploy fails and a
  recovery re-run still has the cache it needs.

They parse with ``re`` + ``pathlib`` only: ``pyyaml`` is not a declared dependency of this project,
so a YAML import here would make the suite depend on whatever happens to be installed.

A test that cannot find its subject fails: it never skips.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

# backend/tests/test_unit/test_deploy_workflow_contract.py → repository root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "deploy-backend.yml"

_SCRIPT_MARKER_RE = re.compile(r"^\s*script: \|\s*$", re.MULTILINE)

# The commands this file makes claims about. Matched as prefixes of a `docker …` command line, and
# never as substrings of the whole script: the workflow documents the unbounded alternative in a
# comment, and reading that comment as a command is how a contract test ends up asserting the
# opposite of what runs. That mistake is not hypothetical — the first version of this file did
# exactly that.
_IMAGE_PRUNE = "docker image prune"
_BUILDER_PRUNE = "docker builder prune"
_SYSTEM_PRUNE = "docker system prune"

# The readiness gate's own message. Anchored on the string the script echoes, not on a line number:
# that is the same thing here, and this one travels with the script.
_READINESS_GATE_MARKER = "READINESS GATE FAILED"

# The rollback tag the deploy leaves behind. Removing it is the one mistake this cleanup must not
# make, and it is what turns "dangling only" from a preference into a contract.
_ROLLBACK_TAG = "storico-api:previous"


def _script_body() -> str:
    """Return the shell script the workflow hands to the ssh action.

    The body is the indented block under ``script: |``, and it is the only place these commands
    legitimately live: a prune written anywhere else in the file would be configuration that never
    runs.
    """
    text = _WORKFLOW_PATH.read_text(encoding="utf-8")
    marker = _SCRIPT_MARKER_RE.search(text)
    assert marker is not None, f"no `script: |` block in {_WORKFLOW_PATH.name}"

    lines = text[marker.end() :].split("\n")
    first = next((line for line in lines if line.strip()), "")
    indentation = len(first) - len(first.lstrip())
    assert indentation > 0, "the script body is not indented, so the block cannot be delimited"

    body: list[str] = []
    for line in lines:
        if line.strip() and not line.startswith(" " * indentation):
            break
        body.append(line)
    assert body, "the script body is empty"
    return "\n".join(body)


def _command_lines(body: str) -> list[tuple[int, str]]:
    """Return ``(line number, command)`` for every command line, comments excluded."""
    return [
        (number, line.strip())
        for number, line in enumerate(body.split("\n"))
        if line.strip().startswith("docker ")
    ]


def _the_command(body: str, prefix: str) -> str:
    """Return the single command line starting with ``prefix``, or fail loudly."""
    matches = [command for _, command in _command_lines(body) if command.startswith(prefix)]
    assert len(matches) == 1, (
        f"expected exactly one `{prefix}` command in the deploy script, found {len(matches)}: "
        f"{matches}"
    )
    return matches[0]


def _flag_tokens(command: str) -> set[str]:
    """Return the flag tokens of a command line, ignoring its arguments."""
    return {token for token in command.split() if token.startswith("-")}


def _is_unbounded(tokens: set[str]) -> bool:
    """Report whether a flush-everything flag is present, in either spelling.

    ``--all`` is one token, but the short form combines: ``-af`` means "all, without asking", and a
    test that only looked for the literal ``-a`` would wave it through.
    """
    for token in tokens:
        if token == "--all":
            return True
        if token.startswith("-") and not token.startswith("--") and "a" in token[1:]:
            return True
    return False


def test_the_script_body_is_found() -> None:
    body = _script_body()
    assert "docker stop storico-api" in body
    assert "alembic upgrade head" in body


def test_the_workflow_still_aborts_on_the_first_error() -> None:
    """`set -e` is what makes the cleanup order below meaningful, so its loss is a failure here."""
    assert re.search(r"^\s*set -e\s*$", _script_body(), re.MULTILINE)


def test_the_deploy_still_leaves_a_rollback_image() -> None:
    commands = [command for _, command in _command_lines(_script_body())]
    assert any(
        command.startswith("docker tag") and _ROLLBACK_TAG in command for command in commands
    ), (
        "the deploy no longer tags the running image as the rollback, so the prune contract below "
        "protects a tag nothing creates"
    )


def test_the_image_prune_never_removes_tagged_images() -> None:
    tokens = _flag_tokens(_the_command(_script_body(), _IMAGE_PRUNE))
    assert not _is_unbounded(tokens), (
        "`docker image prune` must stay dangling-only: `-a`/`--all` deletes the tagged rollback "
        f"image and every other tagged image on the host. Flags found: {sorted(tokens)}"
    )


def test_the_build_cache_prune_keeps_a_bounded_window() -> None:
    tokens = _flag_tokens(_the_command(_script_body(), _BUILDER_PRUNE))
    assert "--filter" in tokens, (
        "the build-cache prune must be bounded by a window, or every deploy rebuilds the "
        f"dependency layer from scratch. Flags found: {sorted(tokens)}"
    )
    assert not _is_unbounded(tokens), (
        f"`--filter` and a flush-everything flag contradict each other. Flags found: {sorted(tokens)}"
    )


def test_nothing_prunes_the_whole_system() -> None:
    for _, command in _command_lines(_script_body()):
        assert not command.startswith(_SYSTEM_PRUNE), (
            "`docker system prune` reaches beyond this project: it also removes the images and "
            "volumes of everything else on the host, and with `-a` the rollback tag with them"
        )


def test_no_prune_is_swallowed() -> None:
    """A swallowed failure is how the 2026-09-20 outage survived a day.

    The readiness gate that replaced it is a plain command whose status reaches `set -e`, and the
    prune is held to the same standard: a disk filling up again has to be a red job, not a line that
    prints something while the deploy reports success.
    """
    prunes = [
        (number, command)
        for number, command in _command_lines(_script_body())
        if command.startswith((_IMAGE_PRUNE, _BUILDER_PRUNE))
    ]
    assert prunes, "the workflow no longer prunes anything"
    for number, command in prunes:
        assert "||" not in command, f"a prune swallowed with `||` on line {number + 1}: {command!r}"


def test_the_cleanup_runs_only_after_the_deploy_is_ready() -> None:
    """Order is the safety property: on a failed deploy, `set -e` aborts before the cleanup."""
    body = _script_body()
    lines = body.split("\n")

    gate = next(
        (number for number, line in enumerate(lines) if _READINESS_GATE_MARKER in line), None
    )
    assert gate is not None, (
        f"the readiness gate's `{_READINESS_GATE_MARKER}` message is gone, so this ordering "
        "contract no longer has a subject"
    )

    cleanup = min(
        number
        for number, command in _command_lines(body)
        if command.startswith((_IMAGE_PRUNE, _BUILDER_PRUNE))
    )
    assert cleanup > gate, (
        "the disk cleanup runs before the readiness gate: a failed deploy would then prune the "
        "cache its own recovery re-run needs"
    )
