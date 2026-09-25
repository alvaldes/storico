/**
 * First code point of each of the first `max` words, uppercased; `?` when there is nothing to
 * abbreviate.
 *
 * Walks code points (via `Array.from`) instead of indexing UTF-16 units: `charAt(0)` splits an
 * astral character's surrogate pair and yields a lone surrogate, which renders as the
 * replacement glyph (e.g. `'😀'.charAt(0)` → `'\ud83d'`).
 */
export function getInitials(name: string, max = 2): string {
  const words = name.split(/\s+/).filter(Boolean);
  if (words.length === 0) return '?';
  return words
    .slice(0, max)
    .map((word) => Array.from(word)[0].toUpperCase())
    .join('');
}
