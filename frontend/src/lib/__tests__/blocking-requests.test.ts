import { describe, expect, it } from 'vitest';
import { BLOCKING_EXCLUSIONS, shouldBlockRequest } from '@/lib/blocking-requests';

describe('shouldBlockRequest — method filtering', () => {
  it('blocks every mutating method on a normal path', () => {
    expect(shouldBlockRequest('POST', '/api/v1/stories/')).toBe(true);
    expect(shouldBlockRequest('PUT', '/api/v1/tasks/t-1')).toBe(true);
    expect(shouldBlockRequest('PATCH', '/api/v1/tasks/t-1')).toBe(true);
    expect(shouldBlockRequest('DELETE', '/api/v1/stories/s-1')).toBe(true);
  });

  it('never blocks reads', () => {
    expect(shouldBlockRequest('GET', '/api/v1/tasks/')).toBe(false);
    expect(shouldBlockRequest('HEAD', '/api/v1/tasks/')).toBe(false);
    expect(shouldBlockRequest('OPTIONS', '/api/v1/tasks/')).toBe(false);
  });

  it('blocks a lowercase method name', () => {
    expect(shouldBlockRequest('post', '/api/v1/stories/')).toBe(true);
  });
});

describe('shouldBlockRequest — exclusions', () => {
  it('does not block the automatic first-login onboarding write', () => {
    expect(shouldBlockRequest('POST', '/api/v1/users/me/onboarding')).toBe(false);
  });

  it('does not block the automatic LLM model probe', () => {
    expect(shouldBlockRequest('POST', '/api/v1/workspaces/ws-1/settings/llm/models')).toBe(
      false,
    );
  });

  it('does not block the extraction start (202 + story page owns its own pending UI)', () => {
    expect(shouldBlockRequest('POST', '/api/v1/workspaces/ws-1/extract/')).toBe(false);
  });

  it('still blocks the near-miss settings path that is NOT the model probe', () => {
    // The models regex is anchored, so a sibling settings write keeps blocking.
    expect(shouldBlockRequest('PUT', '/api/v1/workspaces/ws-1/settings/llm')).toBe(true);
  });

  it('strips the query string before matching, so an exclusion cannot be dodged or triggered by parameters', () => {
    expect(shouldBlockRequest('POST', '/api/v1/tasks/t-1/invalidations?foo=1')).toBe(true);
    expect(shouldBlockRequest('POST', '/api/v1/workspaces/ws-1/extract/?dry_run=true')).toBe(
      false,
    );
  });

  it('strips a hash before matching', () => {
    expect(shouldBlockRequest('POST', '/api/v1/tasks/t-1#anchor')).toBe(true);
  });
});

describe('BLOCKING_EXCLUSIONS', () => {
  it('has exactly three entries, each carrying a written-down reason', () => {
    expect(BLOCKING_EXCLUSIONS).toHaveLength(3);
    for (const exclusion of BLOCKING_EXCLUSIONS) {
      expect(exclusion.why.length).toBeGreaterThan(0);
      expect(exclusion.why.trim()).toBe(exclusion.why);
    }
  });

  it('matches the real call site of each exclusion and nothing broader', () => {
    expect(BLOCKING_EXCLUSIONS[0].match.test('/api/v1/users/me/onboarding')).toBe(true);
    expect(BLOCKING_EXCLUSIONS[0].match.test('/api/v1/users/me/onboarding/extra')).toBe(false);

    expect(
      BLOCKING_EXCLUSIONS[1].match.test('/api/v1/workspaces/ws-1/settings/llm/models'),
    ).toBe(true);
    expect(
      BLOCKING_EXCLUSIONS[1].match.test('/api/v1/workspaces/ws-1/settings/llm/models/reload'),
    ).toBe(false);

    expect(BLOCKING_EXCLUSIONS[2].match.test('/api/v1/workspaces/ws-1/extract/')).toBe(true);
    expect(BLOCKING_EXCLUSIONS[2].match.test('/api/v1/workspaces/ws-1/extract')).toBe(false);
  });
});
