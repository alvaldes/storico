// Deliberately narrow. This config exists for one class of bug: a hook that
// runs conditionally or reads stale closure state. The ExportPanel incident
// (early return above three useMemo calls; the page rendered nothing in
// production while every gate was green — see "Post-merge incident" in
// odd/tasks/export-page-rework.md) is exactly that class, and no gate caught
// it because no lint ran anywhere. Do not grow this into a general style
// config: a first run that spews hundreds of style errors is how a lint gate
// gets disabled the next week.
import reactHooks from 'eslint-plugin-react-hooks';
import tseslint from 'typescript-eslint';

export default [
  {
    // Build output. `.vercel/` and `dist/` are gitignored, but ESLint's flat
    // config does not read `.gitignore`, so the built bundles must be ignored
    // here or every run lints minified artifacts. node_modules is ignored by
    // default; listed so the contract does not depend on that default.
    ignores: ['dist/**', '.vercel/**', '.astro/**', 'node_modules/**'],
  },
  {
    files: ['src/**/*.{js,mjs,jsx,ts,mts,tsx}'],
    // The TypeScript parser is needed to read the files at all; typescript-
    // eslint is used ONLY as a parser here, plus its plugin *registration*:
    // several files carry pre-existing inline `eslint-disable` directives for
    // @typescript-eslint rules (shadcn-generated code), and an unregistered
    // rule name makes ESLint error with "Definition for rule ... was not
    // found". Registering the plugin makes those directives resolve — with
    // every rule left off, so they report as unused-directive warnings, not
    // as enabled checks. This config's rule contract stays the two
    // react-hooks rules.
    languageOptions: {
      parser: tseslint.parser,
    },
    plugins: {
      '@typescript-eslint': tseslint.plugin,
      'react-hooks': reactHooks,
    },
    rules: {
      // The rule that exists for the incident class above. Error: a
      // conditional hook is a runtime crash on a render path, not a taste
      // question.
      'react-hooks/rules-of-hooks': 'error',
      // exhaustive-deps is warn, not error, and that is a decision: it flags
      // stale closures, which is real bug territory, but it also flags
      // intentional omissions (memo objects re-derived per render, refs read
      // during render guards). Making it an error before we know this
      // codebase's noise rate would hand the first contributor a wall of
      // failures that trains people to ignore the gate. It stays visible as a
      // warning; if the warnings prove to be mostly true positives, promote
      // it — if mostly noise, that is a finding to record here, not a
      // blanket disable to add.
      'react-hooks/exhaustive-deps': 'warn',
    },
  },
];
