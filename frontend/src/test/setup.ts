import '@testing-library/jest-dom/vitest';

// jsdom does not implement matchMedia — mock it for uiStore usage.
//
// Guarded because a test file may opt into the `node` environment with the
// `@vitest-environment node` pragma (one does, to read a backend file off the real
// filesystem); the setup file runs for those too, and `window` does not exist there.
if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}
