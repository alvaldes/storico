import { describe, it, expect, beforeEach } from 'vitest';
import {
  getScopedWorkspaceId,
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
});
