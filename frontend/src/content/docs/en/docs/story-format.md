---
title: User story format
description: The shape Storico expects, the two ways the form takes a story, the limits, and where the format is actually enforced.
---

## The shape

A story is one sentence in the canonical agile form:

```text
As a(n) [role], I want [feature], so that [benefit]
```

> "As a user, I want to reset my password, so that I can regain access to my account."

The three parts are separate fields in the database, and the whole sentence is stored as the story's **raw text**. The raw text is the string the model actually reads — it is the prompt's user story, and it is also what the historical context stores — so it is the part worth getting right.

## The two ways the form takes a story

**Parts mode** is three inputs: the role, the feature and the benefit. You never type the connective words. The form composes the raw text itself with a fixed English template:

```text
As a(n) {actor}, I want {feature}, so that {benefit}
```

Those words are hardcoded, not translated. Switching the interface to Spanish changes the labels around the inputs, never the text that reaches the model — which is the point.

**Full-text mode** takes the whole sentence in one box. The form checks that it carries the three keywords — an `As a`/`As an`/`As a(n)` opening, `I want`, and `so that` — and then splits it into the role, the feature and the benefit. A text that has the keywords but cannot be split is refused, and a text missing any of them is refused with a message telling you the expected format.

## Limits

| Field | Limit |
| --- | --- |
| Role (`actor`) | 100 characters, required |
| Feature | 300 characters, required |
| Benefit | 300 characters, required |
| Raw text | 2000 characters |

In full-text mode the parts are **truncated** to their limits rather than rejected, while the raw text keeps up to its 2000 characters. A very long story therefore still extracts, with the parts clipped for display and the full sentence preserved for the prompt.

## Stories are expected in English

The interface is bilingual; the stories are not. The models this tool targets were trained predominantly in English, and their output for task decomposition is measured in English. Parts mode enforces the English connectors by construction, because it always composes them that way.

## Where the format is enforced, and where it is not

- **The form** enforces it: the keyword check and the split run before anything is sent.
- **[CSV import](/en/docs/story-import)** enforces it in the one-column shape: a row that does not match the format is refused with the reason `unparsable_story`.
- **The API does not.** It stores four fields — role, feature, benefit, raw text — and applies their length limits. It does not re-check that the raw text reads like a canonical story, so a story created directly against the API with odd text is accepted and then extracted as-is.
