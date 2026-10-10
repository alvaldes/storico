"""Pins the Trello export failure codes to the registry the frontend translates.

Every member of the ``TrelloExportError`` family carries its failure code as a
class attribute (``domain/entities/exceptions.py``), and ``api/error_codes.py``
declares the same literal — the file the frontend guard parses by regex, so
reformatting it is out of bounds and a code nobody registered cannot be
translated. This suite is the pin between the two: a new exception whose code
the registry does not declare goes red here instead of shipping a string the
frontend cannot translate. It discovers the family by walking subclasses, so a
future member is covered by construction, not by remembering to add it to a
list.
"""

import re
from pathlib import Path

from storico.api import error_codes
from storico.domain.entities.exceptions import (
    TRELLO_EXPORT_INTERRUPTED,
    TrelloExportError,
)

_REGISTRY_PATH = Path(error_codes.__file__)

# Literal ``NAME = "value"`` assignments, extracted the way the frontend guard
# reads the file — so a code that exists only as an import or a computed value
# does not count as declared.
_LITERAL_ASSIGNMENT = re.compile(r'^([A-Z][A-Z0-9_]*) = "([A-Z0-9_]+)"$', re.MULTILINE)


def _declared_codes() -> set[str]:
    """The code values the registry declares as literal assignments."""
    return {
        value for _, value in _LITERAL_ASSIGNMENT.findall(_REGISTRY_PATH.read_text(encoding="utf8"))
    }


def _family() -> list[type[TrelloExportError]]:
    """The base exception itself and every subclass, discovered, not listed."""
    found: list[type[TrelloExportError]] = [TrelloExportError]
    stack: list[type[TrelloExportError]] = [TrelloExportError]
    while stack:
        for subclass in stack.pop().__subclasses__():
            if subclass not in found:
                found.append(subclass)
                stack.append(subclass)
    return found


def test_every_trello_exception_code_is_declared_by_the_registry():
    declared = _declared_codes()
    for exc_class in _family():
        code = getattr(exc_class, "code", None)
        assert isinstance(code, str), (
            f"{exc_class.__name__} declares no code — the runner and the HTTP "
            "envelope would fall back to INTERNAL_ERROR for it"
        )
        assert code in declared, (
            f"{exc_class.__name__}.code = {code!r} is not declared in "
            "api/error_codes.py — the frontend cannot translate it"
        )


def test_the_known_family_members_are_covered():
    # The discovery above is only as good as the family it finds: pin the
    # members this feature shipped so a rename cannot shrink the sweep to
    # nothing without this test noticing.
    names = {exc_class.__name__ for exc_class in _family()}
    assert {
        "TrelloExportError",
        "TrelloCredentialRejectedError",
        "TrelloServiceUnavailableError",
        "TrelloRateLimitExhaustedError",
        "TrelloBoardRefusedError",
        "TrelloCardRefusedError",
    } <= names


def test_the_interrupted_code_is_declared_by_the_registry():
    # The interrupted code is not a typed failure of any family member — the
    # cancellation handler and the startup sweep write it — but the runner
    # stores it from the domain mirror, so the mirror's literal is pinned the
    # same way.
    assert TRELLO_EXPORT_INTERRUPTED in _declared_codes()
