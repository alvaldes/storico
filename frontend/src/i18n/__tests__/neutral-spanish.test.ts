// @vitest-environment node
//
// Besides importing the JSON catalogs, this guard reads the Spanish Starlight markdown off the
// real filesystem, so it needs a real path: jsdom hands out `http://localhost/...` URLs for
// `import.meta.url`, and `readFileSync` refuses those. The node environment keeps this file out
// of the jsdom suite instead of making the paths depend on the working directory.
import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';

import en from '@/i18n/en.json';
import es from '@/i18n/es.json';

/**
 * The Spanish UI copy is neutral international Spanish (tú register, standard
 * imperatives), never Rioplatense voseo. The tell is the voseo imperative, which
 * carries an accent the neutral form does not (`Seleccioná` vs `Selecciona`), plus a
 * handful of pronouns that only exist in that variant.
 *
 * Prose in a contributing guide does not fail a build, and voseo arrives exactly when
 * someone pastes a string from a local conversation, so the rule lives here too.
 */
const VOSEO_FORMS = new Set([
  // Imperatives: voseo accents the final vowel, neutral Spanish does not.
  'seleccioná',
  'revisá',
  'volvé',
  'guardá',
  'corregí',
  'escribí',
  'creá',
  'usá',
  'hacé',
  'ingresá',
  'continuá',
  'elegí',
  'agregá',
  'probá',
  'mirá',
  'completá',
  'verificá',
  'enviá',
  'aceptá',
  'cancelá',
  'confirmá',
  'descargá',
  'introducí',
  'abrí',
  'cerrá',
  'andá',
  'vení',
  'tené',
  'poné',
  'salí',
  'cargá',
  'copiá',
  'pegá',
  'borrá',
  'sumá',
  'dejá',
  // Imperative + clitic, also accented in voseo.
  'dejalo',
  'dejala',
  'dejalos',
  'dejalas',
  'hacelo',
  'hacela',
  'decime',
  'fijate',
  'intentalo',
  'intentala',
  'probalo',
  'usalo',
  // Pronouns and present-tense forms that only exist in voseo.
  'vos',
  'sos',
  'tenés',
  'podés',
  'querés',
  'sabés',
  'acá',
]);

function splitWords(text: string): string[] {
  return text.toLowerCase().split(/[^a-záéíóúüñ]+/);
}

function voseoFormsIn(text: string): string[] {
  return splitWords(text).filter((word) => VOSEO_FORMS.has(word));
}

function collectStrings(value: unknown, path: string[] = []): [string, string][] {
  if (typeof value === 'string') {
    return [[path.join('.'), value]];
  }
  if (value && typeof value === 'object') {
    return Object.entries(value).flatMap(([key, child]) => collectStrings(child, [...path, key]));
  }
  return [];
}

/** Every `.md` file under `dir`, recursively, as name + text. */
function markdownFiles(dir: URL): { name: string; text: string }[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const entryUrl = new URL(`${entry.name}${entry.isDirectory() ? '/' : ''}`, dir);
    if (entry.isDirectory()) return markdownFiles(entryUrl);
    if (!entry.name.endsWith('.md')) return [];
    return [{ name: entry.name, text: readFileSync(entryUrl, 'utf8') }];
  });
}

/** The Spanish documentation pages, where the same variant rule applies to prose. */
const ES_MARKDOWN = markdownFiles(new URL('../../content/docs/es/', import.meta.url));

/**
 * The Spanish sidebar labels living in `astro.config.mjs`, extracted from the
 * `translations: { es: '...' }` entries only. That file is code, English prose,
 * and URLs besides these strings, so scanning the whole file would guard
 * nothing meaningful; the extraction keeps the check on exactly the Spanish
 * copy that ships to `/es/docs`. Only the labels are real Spanish there: the
 * same word list would otherwise trip on lookalikes inside code identifiers
 * (`docs/roles-permissions` contains the letters of `sos`), which whole-word
 * tokenization in `voseoFormsIn` already avoids for the values themselves.
 */
const ES_SIDEBAR_LABELS = (() => {
  const config = readFileSync(new URL('../../../astro.config.mjs', import.meta.url), 'utf8');
  return [...config.matchAll(/translations:\s*\{\s*es:\s*(['"])(.*?)\1/g)].map((match, i) => ({
    name: `sidebar entry ${i + 1}`,
    text: match[2],
  }));
})();

describe('es.json Spanish variant', () => {
  it('detects voseo and leaves neutral Spanish alone', () => {
    // Guarding the guard: a detector that matches nothing would pass the copy check
    // below for the wrong reason.
    expect(voseoFormsIn('Seleccioná un modelo')).toEqual(['seleccioná']);
    expect(voseoFormsIn('No se pudo eliminar la cuenta. Intentalo de nuevo.')).toEqual([
      'intentalo',
    ]);
    expect(voseoFormsIn('Selecciona un modelo')).toEqual([]);
    expect(voseoFormsIn('Esto eliminará el proyecto y no se puede deshacer.')).toEqual([]);
  });

  it('uses neutral Spanish everywhere in the Spanish copy', () => {
    const offenders = collectStrings(es)
      .flatMap(([key, text]) => voseoFormsIn(text).map((form) => `${key}: "${form}"`))
      .sort();

    expect(offenders).toEqual([]);
  });

  it('keeps the same keys in en.json and es.json', () => {
    const keys = (value: unknown, path: string[] = []): string[] => {
      if (value && typeof value === 'object') {
        return Object.entries(value).flatMap(([key, child]) => keys(child, [...path, key]));
      }
      return [path.join('.')];
    };

    expect(keys(es).sort()).toEqual(keys(en).sort());
  });
});

describe('Spanish docs markdown variant', () => {
  it('finds the Spanish docs pages, or the voseo case below is vacuous', () => {
    // A broken glob or a moved content directory must fail loudly here instead of
    // letting the per-file check pass on an empty list.
    expect(ES_MARKDOWN.length).toBeGreaterThanOrEqual(5);
  });

  it.each(ES_MARKDOWN)('uses neutral Spanish in $name', ({ name, text }) => {
    const offenders = voseoFormsIn(text);
    expect(offenders, `${name} carries voseo forms: ${offenders.join(', ')}`).toEqual([]);
  });
});

describe('Spanish sidebar labels in astro.config.mjs', () => {
  it('finds a translations entry per sidebar item, or the voseo case below is vacuous', () => {
    // If the config moves or the extraction regex breaks, this must fail loudly
    // instead of letting the per-label check pass on an empty list.
    expect(ES_SIDEBAR_LABELS.length).toBeGreaterThanOrEqual(9);
  });

  it.each(ES_SIDEBAR_LABELS)('uses neutral Spanish in $name', ({ name, text }) => {
    const offenders = voseoFormsIn(text);
    expect(offenders, `${name} carries voseo forms: ${offenders.join(', ')}`).toEqual([]);
  });
});
