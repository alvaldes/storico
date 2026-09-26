// @vitest-environment node
//
// These guards read source files, so they need a real filesystem path: jsdom hands out
// `http://localhost/...` URLs for `import.meta.url`, and `readFileSync` refuses those.
// The node environment keeps this file out of the jsdom suite instead of making the
// paths depend on the working directory.
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';

/**
 * The sentence that becomes the prompt sent to the LLM is built in two languages.
 *
 * `CANONICAL_RAW_TEXT_TEMPLATE` (backend, used when the CSV import derives the text from
 * `actor`/`feature`/`benefit`) and `StoryForm`'s `generatedRaw` (frontend, used when someone
 * creates a story one at a time) are two independent copies of the same string, and the
 * extraction reads exactly this text as its user story. A divergence does not fail anything at
 * runtime — it quietly changes the prompt — so the two are pinned here against each other.
 *
 * The comparison is on the literal spans around the placeholders and on the placeholder names,
 * not on the raw expression: the frontend writes `${actor.trim()}` inside a template literal
 * while the backend writes `{actor}` inside a plain string, and the test must fail when the
 * sentence changes, not when either side is rewritten to produce the same sentence.
 */

const PYTHON_SOURCE = readFileSync(
  new URL(
    '../../../../backend/src/storico/domain/services/story_import.py',
    import.meta.url,
  ),
  'utf8',
);

const STORY_FORM_SOURCE = readFileSync(
  new URL('../../components/react/StoryForm.tsx', import.meta.url),
  'utf8',
);

/** The literal text between placeholders, in order. */
function literalSpans(template: string): string[] {
  return template.split(/\$\{[^}]*\}|\{[^{}]*\}/);
}

/** The placeholder names, in order. A `.trim()` on the frontend side is not part of the name. */
function placeholderNames(template: string): string[] {
  const names: string[] = [];
  for (const match of template.matchAll(/\$\{\s*([A-Za-z_$][\w$]*)(?:\.trim\(\))?\s*\}|\{\s*(\w+)\s*\}/g)) {
    names.push((match[1] ?? match[2]) as string);
  }
  return names;
}

describe('the canonical user story text is the same in both languages', () => {
  it('extracts the backend template', () => {
    const declared = PYTHON_SOURCE.match(/^CANONICAL_RAW_TEXT_TEMPLATE = "(.+)"$/m)?.[1];

    expect(declared, 'the backend declares CANONICAL_RAW_TEXT_TEMPLATE').not.toBeUndefined();
    // A rename that made the extraction return undefined would otherwise pass the
    // comparison below by comparing two empty things.
    expect(placeholderNames(declared!)).toEqual(['actor', 'feature', 'benefit']);
  });

  it('extracts the frontend template literal', () => {
    const declared = STORY_FORM_SOURCE.match(/const generatedRaw = `([^`]+)`;/)?.[1];

    expect(declared, 'StoryForm builds generatedRaw from a template literal').not.toBeUndefined();
    expect(placeholderNames(declared!)).toEqual(['actor', 'feature', 'benefit']);
  });

  it('renders the same sentence, placeholder for placeholder', () => {
    // Read through the same extractors the two tests above pin, so a change in either
    // source expression fails loudly here instead of silently comparing nothing.
    const backend = PYTHON_SOURCE.match(/^CANONICAL_RAW_TEXT_TEMPLATE = "(.+)"$/m)![1];
    const frontend = STORY_FORM_SOURCE.match(/const generatedRaw = `([^`]+)`;/ )![1];

    expect(literalSpans(frontend)).toEqual(literalSpans(backend));
    expect(placeholderNames(frontend)).toEqual(placeholderNames(backend));
    expect(literalSpans(backend)).toHaveLength(4);
  });
});
