"""Render the FastAPI OpenAPI spec into the docs site's API reference pages.

Run from the repository root, with the backend environment available:

    conda run -n storico python -m storico.scripts.render_api_reference

The output is deterministic: the same application produces the same bytes. That is what
lets ``tests/test_api_reference_is_current.py`` compare the committed pages against a
fresh render and fail when the docs describe an API that changed underneath them.

The page body stays in English in both locales, on purpose. The spec's paths, field names
and types are English because the API is; only the page chrome is localized. Translating
the API into one locale and not the other — or inventing Spanish field names — would be a
lie about the wire format, and this repository has paid for that class of lie before.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
DOCS_ROOT = REPO_ROOT / "frontend" / "src" / "content" / "docs"
LOCALES = ("en", "es")

METHODS = ("get", "post", "put", "patch", "delete")

CHROME: dict[str, dict[str, str]] = {
    "en": {
        "title": "API Reference",
        "description": "Every endpoint the Storico API exposes, with its parameters and responses.",
        "intro": (
            "Every path below is rendered from the FastAPI application itself, so it describes what the "
            "code answers rather than what a document remembered. The API's own names — paths, fields, "
            "types — stay in English, because the API is."
        ),
        "parameters": "Parameters",
        "request_body": "Request body",
        "responses": "Responses",
        "name": "Name",
        "in": "In",
        "required": "Required",
        "type": "Type",
        "field": "Field",
        "status": "Status",
        "description_h": "Description",
        "schema": "Schema",
        "yes": "yes",
        "no": "no",
        "no_parameters": "_No parameters._",
    },
    "es": {
        "title": "Referencia de la API",
        "description": "Todos los endpoints que expone la API de Storico, con sus parámetros y respuestas.",
        "intro": (
            "Cada ruta de abajo se genera desde la propia aplicación FastAPI, así que describe lo que el "
            "código responde y no lo que un documento recordaba. Los nombres propios de la API —rutas, "
            "campos, tipos— quedan en inglés, porque la API está en inglés."
        ),
        "parameters": "Parámetros",
        "request_body": "Cuerpo de la petición",
        "responses": "Respuestas",
        "name": "Nombre",
        "in": "Ubicación",
        "required": "Obligatorio",
        "type": "Tipo",
        "field": "Campo",
        "status": "Estado",
        "description_h": "Descripción",
        "schema": "Esquema",
        "yes": "sí",
        "no": "no",
        "no_parameters": "_Sin parámetros._",
    },
}


def _ref_name(schema: Any) -> str | None:
    """The component name a ``$ref`` points at, or ``None``."""
    if isinstance(schema, dict) and isinstance(schema.get("$ref"), str):
        return schema["$ref"].rsplit("/", 1)[-1]
    return None


def type_of(schema: Any) -> str:
    """A short, deterministic rendering of a JSON-schema fragment."""
    if not isinstance(schema, dict):
        return "any"
    name = _ref_name(schema)
    if name:
        return name
    for combinator, joiner in (("anyOf", " | "), ("oneOf", " | "), ("allOf", " & ")):
        if combinator in schema:
            # Sorted for determinism, with `null` last so unions read `string | null`.
            parts = sorted(
                {type_of(part) for part in schema[combinator]}, key=lambda p: (p == "null", p)
            )
            return joiner.join(parts)
    kind = schema.get("type")
    if kind == "array":
        return f"{type_of(schema.get('items', {}))}[]"
    if kind == "object" and "additionalProperties" in schema:
        extra = schema["additionalProperties"]
        return f"map<string, {type_of(extra)}>" if extra else "map<string, any>"
    if "enum" in schema:
        return "enum(" + ", ".join(str(value) for value in schema["enum"]) + ")"
    if kind is None and "properties" in schema:
        kind = "object"
    return kind or "any"


def fields_of(
    schema: Any,
    spec: dict[str, Any],
    seen: frozenset[str] = frozenset(),
    depth: int = 0,
) -> list[tuple[str, str, bool]]:
    """Top-level ``(name, type, required)`` of a schema, following ``$ref`` one level.

    ``seen`` is the whole bound, and it is the reason this terminates: a component is expanded
    at most once per call, so a schema that refers to itself stops instead of recursing. An
    earlier version also carried a depth limit that could never fire — the depth never
    incremented on the ``$ref`` descent — so it was removed rather than left as a guard that
    guards nothing behind a comment that claims otherwise.

    Measured when this was written: the application's 60 components contain **no** ref cycle at
    all — walking every schema's refs found zero self-references and zero cycles. The guard is
    therefore exercised by a unit test with a synthetic recursive schema, not by the output.
    """
    if not isinstance(schema, dict):
        return []
    name = _ref_name(schema)
    if name:
        if name in seen:
            return []
        target = (spec.get("components", {}).get("schemas") or {}).get(name)
        return fields_of(target, spec, seen | {name})
    properties: dict[str, Any] = dict(schema.get("properties") or {})
    required: set[str] = set(schema.get("required") or [])
    for part in schema.get("allOf") or []:
        part_name = _ref_name(part)
        if part_name:
            if part_name in seen:
                continue
            part = (spec.get("components", {}).get("schemas") or {}).get(part_name, {})
            seen = seen | {part_name}
        properties.update(part.get("properties") or {})
        required.update(part.get("required") or [])
    return [(key, type_of(value), key in required) for key, value in properties.items()]


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    lines.append("")
    return lines


def _render_operation(
    path: str, method: str, operation: dict[str, Any], spec: dict[str, Any], chrome: dict[str, str]
) -> list[str]:
    lines = [f"### `{method.upper()}` `{path}`", ""]
    summary = (operation.get("summary") or "").strip()
    description = (operation.get("description") or "").strip()
    if summary:
        lines += [summary, ""]
    if description and description != summary:
        lines += [description, ""]

    lines += [f"**{chrome['parameters']}**", ""]
    parameters = operation.get("parameters") or []
    if parameters:
        rows = []
        for parameter in sorted(parameters, key=lambda p: (p.get("in", ""), p.get("name", ""))):
            rows.append(
                [
                    f"`{parameter.get('name', '')}`",
                    f"`{parameter.get('in', '')}`",
                    chrome["yes"] if parameter.get("required") else chrome["no"],
                    f"`{type_of(parameter.get('schema', {}))}`",
                ]
            )
        lines += _table([chrome["name"], chrome["in"], chrome["required"], chrome["type"]], rows)
    else:
        lines += [chrome["no_parameters"], ""]

    body = operation.get("requestBody") or {}
    content = body.get("content") or {}
    if content:
        media = "application/json" if "application/json" in content else sorted(content)[0]
        schema = content[media].get("schema", {})
        lines += [f"**{chrome['request_body']}** (`{media}`)", ""]
        rows = fields_of(schema, spec)
        if rows:
            lines += _table(
                [chrome["field"], chrome["type"], chrome["required"]],
                [
                    [f"`{name}`", f"`{type}`", chrome["yes"] if required else chrome["no"]]
                    for name, type, required in rows
                ],
            )
        else:
            lines += [f"`{type_of(schema)}`", ""]

    lines += [f"**{chrome['responses']}**", ""]
    responses = operation.get("responses") or {}
    rows = []
    for status in sorted(responses, key=lambda code: (len(code), code)):
        response = responses[status]
        text = (response.get("description") or "").replace("\n", " ").replace("|", "\\|").strip()
        schema = ((response.get("content") or {}).get("application/json") or {}).get("schema")
        rows.append([f"`{status}`", text or "—", f"`{type_of(schema)}`" if schema else "—"])
    lines += _table([chrome["status"], chrome["description_h"], chrome["schema"]], rows)
    return lines


def render_page(spec: dict[str, Any], locale: str) -> str:
    """The full markdown page for one locale. Deterministic by construction."""
    chrome = CHROME[locale]
    lines = [
        "---",
        f"title: {chrome['title']}",
        f"description: {chrome['description']}",
        "---",
        "",
        chrome["intro"],
        "",
    ]

    grouped: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for path, item in (spec.get("paths") or {}).items():
        for method, operation in item.items():
            if method not in METHODS or not isinstance(operation, dict):
                continue
            for tag in operation.get("tags") or ["untagged"]:
                grouped.setdefault(tag, []).append((path, method, operation))

    for tag in sorted(grouped):
        lines += [f"## {tag}", ""]
        for path, method, operation in sorted(
            grouped[tag], key=lambda entry: (entry[0], METHODS.index(entry[1]))
        ):
            lines += _render_operation(path, method, operation, spec, chrome)

    return "\n".join(lines).rstrip() + "\n"


def render_pages() -> dict[Path, str]:
    """Render every locale's page, keyed by its absolute path. Imports the app lazily so a
    test can compare against the committed files without rendering twice."""
    from storico.api.app import create_app

    spec = create_app().openapi()
    return {
        DOCS_ROOT / locale / "docs" / "api-reference.md": render_page(spec, locale)
        for locale in LOCALES
    }


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    pages = render_pages()
    stale: list[Path] = []
    written = 0
    for path, content in pages.items():
        if path.exists() and path.read_text(encoding="utf-8") == content:
            continue
        if path.exists():
            stale.append(path)
        if check_only:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written += 1
        print(f"wrote {path.relative_to(REPO_ROOT)} ({len(content.splitlines())} lines)")
    if check_only and stale:
        print("stale: " + ", ".join(str(p.relative_to(REPO_ROOT)) for p in stale), file=sys.stderr)
        return 1
    if not check_only and written == 0:
        print("already current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
