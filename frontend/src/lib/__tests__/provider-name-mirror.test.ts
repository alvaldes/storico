// @vitest-environment node
//
// The guard reads a Python file, so it needs a real filesystem path: jsdom hands
// out `http://localhost/...` URLs for `import.meta.url`, and `readFileSync` refuses
// those. The node environment keeps this file out of the jsdom suite instead of
// making the path depend on the working directory.
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';

import { PROVIDER_NAME_MAX_LENGTH } from '@/lib/llm-providers';

/**
 * The one number two languages have to agree on.
 *
 * `NAME_MAX_LENGTH` (backend) and `PROVIDER_NAME_MAX_LENGTH` (frontend) are kept in
 * step by hand, because the backend is Python and the frontend cannot import it. The
 * frontend copy drives the input's `maxLength` and the visible counter, so a drift
 * would let the field accept a name the API refuses — the exact failure the counter
 * was added to prevent.
 */
describe('provider name length mirror', () => {
  const backendSource = readFileSync(
    new URL('../../../../backend/src/storico/api/schemas/custom_provider.py', import.meta.url),
    'utf8',
  );

  it('matches the backend maximum', () => {
    expect(backendSource.match(/^NAME_MAX_LENGTH = (\d+)$/m)?.[1]).toBe(
      String(PROVIDER_NAME_MAX_LENGTH),
    );
  });

  it('reads the rule from the module that declares it', () => {
    // Guards the guard: if the constant is renamed in the backend, the regex above
    // would stop matching and the assertion would fail on `undefined` rather than on
    // a number, which reads as a mystery. This says so directly.
    expect(backendSource).toContain('NAME_MAX_LENGTH');
  });
});
