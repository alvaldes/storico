import { describe, it, expect, beforeEach } from 'vitest';
import {
  getScopedWorkspaceId,
  isScopeUnchanged,
  isScopedWorkspace,
  resetScopedWorkspace,
  setScopedWorkspaceId,
} from '@/lib/workspace-scope';

describe('workspace-scope', () => {
  beforeEach(() => {
    resetScopedWorkspace();
  });

  it('is fail-open and unobserved before any switch is observed', () => {
    expect(getScopedWorkspaceId()).toBeUndefined();
    expect(isScopedWorkspace('ws-a')).toBe(true);
    expect(isScopedWorkspace('ws-b')).toBe(true);
    expect(isScopedWorkspace(null)).toBe(true);
    expect(isScopedWorkspace(undefined)).toBe(true);
  });

  it('accepts only the matching id once a scope is set', () => {
    setScopedWorkspaceId('ws-a');

    expect(getScopedWorkspaceId()).toBe('ws-a');
    expect(isScopedWorkspace('ws-a')).toBe(true);
    expect(isScopedWorkspace('ws-b')).toBe(false);
    expect(isScopedWorkspace('')).toBe(false);
  });

  it('reflects the last value that was set, including an observed null', () => {
    setScopedWorkspaceId('ws-a');
    expect(getScopedWorkspaceId()).toBe('ws-a');

    setScopedWorkspaceId('ws-b');
    expect(getScopedWorkspaceId()).toBe('ws-b');

    setScopedWorkspaceId(null);
    expect(getScopedWorkspaceId()).toBeNull();
  });

  it('denies every id once an explicit "no workspace" scope is observed', () => {
    setScopedWorkspaceId(null);

    expect(getScopedWorkspaceId()).toBeNull();
    expect(isScopedWorkspace('ws-a')).toBe(false);
    expect(isScopedWorkspace('ws-b')).toBe(false);
    expect(isScopedWorkspace('')).toBe(false);
    expect(isScopedWorkspace(null)).toBe(false);
    expect(isScopedWorkspace(undefined)).toBe(false);
  });

  it('restores the unobserved fail-open state only through resetScopedWorkspace', () => {
    setScopedWorkspaceId('ws-a');
    expect(isScopedWorkspace('ws-b')).toBe(false);

    resetScopedWorkspace();

    expect(getScopedWorkspaceId()).toBeUndefined();
    expect(isScopedWorkspace('ws-b')).toBe(true);
    expect(isScopedWorkspace('ws-a')).toBe(true);
  });

  describe('isScopeUnchanged', () => {
    it('is fail-open before any switch is observed', () => {
      expect(isScopeUnchanged(undefined)).toBe(true);
    });

    it('accepts the scope a call started in and rejects a different one', () => {
      setScopedWorkspaceId('ws-a');

      expect(isScopeUnchanged('ws-a')).toBe(true);
      expect(isScopeUnchanged('ws-b')).toBe(false);
    });

    it('rejects the scope a call started in once a switch moved it', () => {
      setScopedWorkspaceId('ws-a');
      setScopedWorkspaceId('ws-b');

      expect(isScopeUnchanged('ws-a')).toBe(false);
      expect(isScopeUnchanged('ws-b')).toBe(true);
    });

    it('rejects every id but the observed "no workspace" once that is the scope', () => {
      setScopedWorkspaceId(null);

      expect(isScopeUnchanged('ws-a')).toBe(false);
      expect(isScopeUnchanged(null)).toBe(true);
    });

    it('restores the fail-open comparison through resetScopedWorkspace', () => {
      setScopedWorkspaceId('ws-a');
      expect(isScopeUnchanged('ws-a')).toBe(true);
      expect(isScopeUnchanged('ws-b')).toBe(false);

      resetScopedWorkspace();

      // Fail-open is back: an unobserved scope matches a call that also started unobserved.
      // This does not make a call that sampled a real id pass again, which is the whole point
      // of the guard once `resetScopedWorkspace` has put the module back to its initial state.
      expect(isScopeUnchanged(undefined)).toBe(true);
      expect(isScopeUnchanged('ws-a')).toBe(false);
    });
  });
});
