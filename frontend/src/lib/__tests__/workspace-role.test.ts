import { describe, it, expect } from 'vitest';
import { canManageVersions } from '@/lib/workspace-role';
import type { Workspace } from '@/types/workspace';

function makeWorkspace(overrides: Partial<Workspace> = {}): Workspace {
  return {
    id: 'ws-1',
    name: 'WS One',
    slug: 'ws-one',
    ownerId: 'owner-1',
    role: 'member',
    memberCount: 2,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

/**
 * The truth table over the client mirror of the backend's `_is_owner_or_admin`
 * (design decision: "the client mirrors the gate in one helper"). Every row
 * the backend gate accepts or refuses, the helper must accept or refuse too.
 */
describe('canManageVersions — the client mirror of the owner-or-admin gate', () => {
  it('accepts the workspace owner even when their role is member', () => {
    expect(canManageVersions(makeWorkspace(), 'owner-1')).toBe(true);
  });

  it('accepts a member with the admin role who is not the owner', () => {
    expect(canManageVersions(makeWorkspace({ role: 'admin' }), 'admin-1')).toBe(true);
  });

  it('accepts an owner who also carries the admin role', () => {
    expect(canManageVersions(makeWorkspace({ role: 'admin' }), 'owner-1')).toBe(true);
  });

  it('refuses a plain member who is neither the owner nor an admin', () => {
    expect(canManageVersions(makeWorkspace(), 'member-1')).toBe(false);
  });

  it('refuses when no workspace is selected', () => {
    expect(canManageVersions(null, 'owner-1')).toBe(false);
    expect(canManageVersions(undefined, 'owner-1')).toBe(false);
  });

  it('refuses when the user id is missing', () => {
    expect(canManageVersions(makeWorkspace(), undefined)).toBe(false);
    expect(canManageVersions(makeWorkspace(), '')).toBe(false);
  });
});
