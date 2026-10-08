// @vitest-environment node
//
// This guard reads a Python file, so it needs a real filesystem path: jsdom hands
// out `http://localhost/...` URLs for `import.meta.url`, and `readFileSync` refuses
// those. The node environment keeps this file out of the jsdom suite instead of
// making the path depend on the working directory. (Same choice as
// provider-name-mirror.test.ts.)
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';

import { IMPORT_MAX_FILE_BYTES } from '@/lib/stories-api';

/**
 * The import file-size cap is declared twice, in two languages.
 *
 * The backend (`backend/src/storico/infrastructure/parsers/story_csv.py`) is
 * authoritative — it is the check that actually answers `413` — and the frontend
 * cannot import it, so the frontend constant is kept in step by this test instead
 * of by hope. A drift in either number means the dialog refuses a file the API
 * would accept, or waves through one the API rejects after a full upload.
 *
 * The read is deliberately unwrapped: if the backend file moves or the constant
 * is renamed, this test must FAIL, not skip, because a silently passing mirror
 * is worse than no mirror at all.
 */
describe('the frontend import size cap mirrors the backend parser', () => {
  const backendSource = readFileSync(
    new URL('../../../../backend/src/storico/infrastructure/parsers/story_csv.py', import.meta.url),
    'utf8',
  );

  it('matches the backend MAX_FILE_BYTES exactly', () => {
    // Python keeps the LAST assignment when a module rebinds a name, so the first
    // match would be the wrong one to compare against. Rather than guess which
    // assignment is the intent, an ambiguous declaration is refused: this
    // collects every assignment and requires exactly one. Reading the first
    // match silently passed while the backend used a different number.
    const declarations = backendSource.match(/^MAX_FILE_BYTES = (.+)$/gm) ?? [];

    expect(declarations, 'story_csv.py declares MAX_FILE_BYTES exactly once').toHaveLength(1);

    const declared = (declarations[0] ?? '').replace('MAX_FILE_BYTES = ', '');

    expect(declared, 'the declaration carries a value').not.toBe('');

    // The backend writes the cap as an arithmetic expression (`2 * 1024 * 1024`),
    // not a literal, so evaluate the multiplication rather than comparing the
    // string form. Only digits, spaces and `*` are accepted: anything else on
    // the line is a declaration this guard does not understand and must refuse,
    // not misread.
    const expression = declared!.trim();
    expect(expression, 'MAX_FILE_BYTES is a plain multiplication of integers').toMatch(
      /^[\d\s*]+$/,
    );
    const backendBytes = expression
      .split('*')
      .map((part) => Number.parseInt(part.trim(), 10))
      .reduce((acc, n) => acc * n, 1);

    expect(backendBytes).toBe(IMPORT_MAX_FILE_BYTES);
  });
});
