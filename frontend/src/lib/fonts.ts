/**
 * Single source of truth for the app's web fonts, loaded from Google Fonts.
 *
 * The literal <link> used to live only in PublicLayout.astro, so every surface that does
 * not render through that layout — the Starlight docs pages — silently loaded no web fonts
 * at all while `--sl-font: Inter` made it look like it should. Both PublicLayout and the
 * Starlight `Head` override render from these constants, so the two surfaces always load
 * the same faces.
 *
 * `FONT_FAMILIES` documents what the stylesheet URL must request; the weight lists are part
 * of the URL itself (Inter 400–800, Space Grotesk 700–800, Geist Mono 400–700), and
 * `src/styles/starlight.css` relies on Space Grotesk existing only at 700/800.
 */
export const FONT_FAMILIES = ['Inter', 'Space Grotesk', 'Geist Mono'] as const;

/**
 * Preconnect hosts in emit order, with their `crossorigin` flag: the stylesheet host is a
 * plain preconnect, the font-file host needs `crossorigin` to be useful.
 */
export const GOOGLE_FONTS_PRECONNECT_HOSTS = [
  { host: 'https://fonts.googleapis.com', crossorigin: false },
  { host: 'https://fonts.gstatic.com', crossorigin: true },
] as const;

/** The exact stylesheet href PublicLayout.astro emitted before this module existed. */
export const GOOGLE_FONTS_STYLESHEET_HREF =
  'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Space+Grotesk:wght@700;800&family=Geist+Mono:wght@400;500;600;700&display=swap';
