# Archive Report: few-shot-examples

> **Change**: `few-shot-examples`
> **Archived**: 2026-09-14
> **Disposition**: superseded (not completed, no canonical spec produced)

## Summary

The manual few-shot examples feature — workspace admins entering
`{user_story, tasks}` examples that the task-generation prompt injects as a
"Few-Shot Examples (Style Reference)" section — was implemented and shipped in
commits `1424ae0` (feature + hydration), `f9597b2` (AGENTS.md sync), and
`e60f8b8` (camelCase round-trip test).

This SDD change, however, was never completed past `design.md`: no
`proposal.md`, `spec.md`, or `tasks.md` were produced, and no canonical spec
exists under `openspec/specs/`.

## Why superseded

Superseded by the `few-shot-qdrant` change, which replaces admin-entered
examples with automatic retrieval from Qdrant: per-workspace retrieval config
(`limit`, `threshold`), a single unified "Few-Shot Examples" prompt section,
workspace-scoped vector search, and cloud Qdrant + cloud embeddings for
production.

## Artifacts at close

- `design.md` (the only artifact that ever existed for this change)

## Notes

- Nothing to sync into `openspec/specs/` — no delta spec was ever written.
- The manual-editor implementation is being removed/replaced by
  `few-shot-qdrant`.
