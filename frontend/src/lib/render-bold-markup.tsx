import { createElement, type ReactNode } from 'react';

/** The emphasis tags the i18n copy is authored with. */
export type BoldMarkupTag = 'b' | 'strong';

// Literal patterns rather than a pattern built from `tag`: the split source stays
// auditable at the definition site, and there is no string-to-regex path at all.
const TAG_PATTERNS: Record<BoldMarkupTag, RegExp> = {
  b: /<\/?b>/,
  strong: /<\/?strong>/,
};

/**
 * Renders an i18n string that authors emphasis with one tag pair, WITHOUT going
 * through `dangerouslySetInnerHTML`.
 *
 * The text is split on the tag's opening and closing forms; the segments between
 * them become real elements and everything else stays a plain text node. That is
 * the whole safety property: a payload such as `<img src=x onerror=alert(1)>` is not
 * a tag this helper splits on, so it never becomes an element and renders as visible
 * literal text.
 *
 * Two callers use two different tags because their translation strings were authored
 * that way: the delete-account dialog copy uses `<b>`, while `story_format_hint` uses
 * `<strong>`. Same idea, different tag — hence the parameter.
 */
export function renderBoldMarkup(text: string, tag: BoldMarkupTag): ReactNode {
  return text
    .split(TAG_PATTERNS[tag])
    .map((part, index) => (index % 2 === 1 ? createElement(tag, { key: index }, part) : part));
}
