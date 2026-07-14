"""Slug generation helpers for workspace names."""

from __future__ import annotations

import re


def generate_slug(name: str, existing_slugs: list[str]) -> str:
    """Generate a unique URL-friendly slug from a workspace name.

    Examples::

        "Acme Project"     → "acme-project"
        "Acme Project"     → "acme-project-1"  (if taken)
        "My  Team!!"       → "my-team"
        ""                 → "workspace"
        "  Spaces  "       → "spaces"

    Args:
        name: The workspace name to slugify.
        existing_slugs: Set of slugs already in use (for uniqueness).

    Returns:
        A unique slug string.
    """
    base = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-"))
    base = re.sub(r"-+", "-", base).strip("-")
    if not base:
        base = "workspace"

    slug = base
    counter = 1
    while slug in existing_slugs:
        slug = f"{base}-{counter}"
        counter += 1

    return slug
