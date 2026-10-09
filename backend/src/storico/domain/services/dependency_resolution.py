"""The one dependency-reference rule, shared by every export surface.

Extracted from ``api/routes/export.py``'s ``_build_markdown`` (where it lived
inlined): a dependency reference is resolved to the referenced task's title —
by id first, then by casefolded title — and an unresolvable reference renders
as the reference itself, never disappears. The Markdown export and the Trello
board plan both mean the same thing by "dependency", so they must resolve it
with the same code, not two implementations of one rule.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DependencyTitleIndex:
    """The title lookup a batch of dependencies resolves against.

    Built once per export from the exported tasks: a dependency may reference a
    task in any status column, so the index covers the whole export, not one
    group of it.
    """

    title_by_id: Mapping[str, str]
    title_by_name: Mapping[str, str]


def build_dependency_title_index(entries: Iterable[tuple[str, str]]) -> DependencyTitleIndex:
    """Index ``(id, title)`` pairs for dependency resolution.

    The name index is keyed by the stripped, casefolded title, so ``Set Up
    Database`` and ``set up database`` resolve to the same task. Exact titles
    are what the Markdown export has always matched; nothing new is normalized
    here beyond the fold the original rule applied.
    """
    title_by_id: dict[str, str] = {}
    title_by_name: dict[str, str] = {}
    for task_id, title in entries:
        title_by_id[task_id] = title
        title_by_name[title.strip().casefold()] = title
    return DependencyTitleIndex(title_by_id=title_by_id, title_by_name=title_by_name)


def resolve_dependency(reference: str, index: DependencyTitleIndex) -> str:
    """Resolve one reference, or render it back unchanged.

    An id match wins; then a casefolded title match; then the raw reference is
    returned. The fallback is the *original* argument (not the stripped form),
    preserving the Markdown export's exact behavior — the returned string is
    what the member reads on the card or in the file, so a reference that names
    nothing must still name itself.
    """
    resolved = reference.strip()
    return index.title_by_id.get(resolved) or index.title_by_name.get(
        resolved.casefold(), reference
    )
