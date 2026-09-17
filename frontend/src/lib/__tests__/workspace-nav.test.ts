import { describe, it, expect } from 'vitest';
import { isSafeWorkspaceId, workspaceScopedPath, workspaceSettingsPath } from '@/lib/workspace-nav';

describe('isSafeWorkspaceId', () => {
  it('accepts alphanumeric and hyphenated ids up to 64 chars', () => {
    expect(isSafeWorkspaceId('a')).toBe(true);
    expect(isSafeWorkspaceId('ws-1-ABC')).toBe(true);
    expect(isSafeWorkspaceId('a'.repeat(64))).toBe(true);
  });

  it('rejects ids that could break out of a path segment', () => {
    expect(isSafeWorkspaceId('')).toBe(false);
    expect(isSafeWorkspaceId('a'.repeat(65))).toBe(false);
    expect(isSafeWorkspaceId('../evil')).toBe(false);
    expect(isSafeWorkspaceId('ws/1')).toBe(false);
    expect(isSafeWorkspaceId('ws 1')).toBe(false);
    expect(isSafeWorkspaceId('ws?x=1')).toBe(false);
    expect(isSafeWorkspaceId('ws_1')).toBe(false);
    expect(isSafeWorkspaceId('ws.1')).toBe(false);
  });
});

describe('workspaceScopedPath', () => {
  it('keeps the locale prefix and swaps the id on a settings URL', () => {
    expect(workspaceScopedPath('/es/workspaces/old-id/settings', 'new-id')).toBe(
      '/es/workspaces/new-id/settings',
    );
  });

  it('keeps the locale prefix on the workspace root URL', () => {
    expect(workspaceScopedPath('/en/workspaces/old-id', 'new-id')).toBe('/en/workspaces/new-id');
  });

  it('preserves deeper subpaths', () => {
    expect(workspaceScopedPath('/es/workspaces/old-id/members/x', 'new-id')).toBe(
      '/es/workspaces/new-id/members/x',
    );
  });

  it('stays without a locale prefix when the pathname has none', () => {
    expect(workspaceScopedPath('/workspaces/old-id/settings', 'new-id')).toBe(
      '/workspaces/new-id/settings',
    );
  });

  it('returns null for pages that are not workspace-scoped', () => {
    expect(workspaceScopedPath('/es/dashboard', 'new-id')).toBeNull();
    expect(workspaceScopedPath('/es/stories', 'new-id')).toBeNull();
    expect(workspaceScopedPath('/', 'new-id')).toBeNull();
  });

  it('returns null for the workspace list page (no id segment)', () => {
    expect(workspaceScopedPath('/es/workspaces', 'new-id')).toBeNull();
    expect(workspaceScopedPath('/workspaces', 'new-id')).toBeNull();
  });

  it('returns null for an unsafe target id', () => {
    expect(workspaceScopedPath('/es/workspaces/old-id/settings', '../evil')).toBeNull();
    expect(workspaceScopedPath('/es/workspaces/old-id/settings', '')).toBeNull();
  });
});

describe('workspaceSettingsPath', () => {
  it('builds the localized settings path of the new workspace', () => {
    expect(workspaceSettingsPath('es', 'new-id')).toBe('/es/workspaces/new-id/settings');
    expect(workspaceSettingsPath('en', 'new-id')).toBe('/en/workspaces/new-id/settings');
  });

  it('returns null for an unsafe id', () => {
    expect(workspaceSettingsPath('es', '../evil')).toBeNull();
    expect(workspaceSettingsPath('en', 'a/b')).toBeNull();
  });
});
