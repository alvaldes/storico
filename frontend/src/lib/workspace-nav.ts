import { localizedPath, type Locale } from '@/i18n/utils';

/**
 * Workspace-aware path helpers.
 *
 * The URL (`/workspaces/{id}/...`) and `useWorkspaceStore().currentWorkspace` are
 * two views of the same fact. These helpers translate a pathname from one
 * workspace id to another without ever interpolating an unvalidated id.
 */

/** Workspace ids are opaque identifiers, but they always travel inside a path segment. */
const SAFE_WORKSPACE_ID = /^[A-Za-z0-9-]{1,64}$/;

/** Locale prefixes owned by the Astro i18n routing. */
const LOCALE_PREFIXES: Locale[] = ['en', 'es'];

/** Matches `/workspaces/{id}` plus any deeper subpath. The captured id is never reused. */
const WORKSPACE_PATH = /^\/workspaces\/[^/]+(\/.*)?$/;

/**
 * Returns true when `id` is safe to interpolate into a URL path segment.
 * Rejects anything outside `[A-Za-z0-9-]{1,64}` so a stored value can never
 * escape its segment (`../evil`, `a/b`, query/fragment injection, etc.).
 */
export function isSafeWorkspaceId(id: string): boolean {
  return SAFE_WORKSPACE_ID.test(id);
}

/**
 * Returns the workspace-scoped equivalent of `pathname` for `workspaceId`, or
 * `null` when `pathname` is not a workspace-scoped page or `workspaceId` is unsafe.
 *
 * The original locale prefix (`/en`, `/es`) and any deeper subpath are preserved;
 * a pathname without a locale prefix stays without one.
 */
export function workspaceScopedPath(pathname: string, workspaceId: string): string | null {
  if (!isSafeWorkspaceId(workspaceId)) return null;

  const prefix = LOCALE_PREFIXES.map((locale) => `/${locale}`).find((candidate) =>
    pathname.startsWith(`${candidate}/`),
  );
  const rest = prefix ? pathname.slice(prefix.length) : pathname;
  const match = rest.match(WORKSPACE_PATH);
  if (!match) return null;

  return `${prefix ?? ''}/workspaces/${workspaceId}${match[1] ?? ''}`;
}

/**
 * Builds the localized settings path of `workspaceId`, or `null` for an unsafe id.
 * Route construction stays inside `localizedPath` so the locale prefix can only
 * ever be an internal `/en...` or `/es...` path.
 */
export function workspaceSettingsPath(locale: Locale, workspaceId: string): string | null {
  if (!isSafeWorkspaceId(workspaceId)) return null;
  return localizedPath(`/workspaces/${workspaceId}/settings`, locale);
}
