import { describe, expect, it } from 'vitest';

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
