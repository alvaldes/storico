import { describe, expect, it } from 'vitest';
import { BLOCKING_EXCLUSIONS, shouldBlockRequest } from '@/lib/blocking-requests';

describe('shouldBlockRequest — method filtering', () => {
  it('blocks every mutating method on a normal path', () => {
    expect(shouldBlockRequest('POST', '/api/v1/stories/')).toBe(true);
    expect(shouldBlockRequest('PATCH', '/api/v1/stories/s-1')).toBe(true);
    expect(shouldBlockRequest('PUT', '/api/v1/stories/s-1')).toBe(true);
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

  it('does not block the task status update PUT (D11: the card move is optimistic and both callers own their pending UI)', () => {
    expect(shouldBlockRequest('PUT', '/api/v1/tasks/t-1')).toBe(false);
  });

  it('still blocks task paths that merely start like the excluded one', () => {
    // The exclusion is anchored on both ends and covers exactly one task
    // resource — not everything that begins with the same prefix. A sibling
    // write like a task's comments, or a hypothetical bulk route whose name
    // only shares the `tasks` prefix, must keep blocking: this is the failure
    // mode a future regex edit is most likely to introduce.
    expect(shouldBlockRequest('POST', '/api/v1/tasks/t-1/comments')).toBe(true);
    expect(shouldBlockRequest('PUT', '/api/v1/tasks-bulk/x')).toBe(true);
  });

  it('still blocks the near-miss settings path that is NOT the model probe', () => {
    // The models regex is anchored, so a sibling settings write keeps blocking.
    expect(shouldBlockRequest('PUT', '/api/v1/workspaces/ws-1/settings/llm')).toBe(true);
  });

  it('strips the query string and hash before matching, so parameters cannot flip a decision either way', () => {
    // A blocking path cannot dodge the veil by appending parameters...
    expect(shouldBlockRequest('POST', '/api/v1/tasks/t-1/invalidations?foo=1')).toBe(true);
    expect(shouldBlockRequest('POST', '/api/v1/tasks/t-1/invalidations#anchor')).toBe(true);
    // ...and the excluded task path cannot be pulled back into blocking by
    // them either: the stripping runs BEFORE the match, so the exclusion is
    // decided on the path alone. Aiming this pin AT the excluded entry (not
    // away from it) is what keeps the property alive now that the task path
    // is itself an exclusion — a case aimed at a still-blocking path would
    // pass even if the stripping silently stopped running.
    expect(shouldBlockRequest('PUT', '/api/v1/tasks/t-1?status=todo')).toBe(false);
    expect(shouldBlockRequest('POST', '/api/v1/tasks/t-1#anchor')).toBe(false);
    expect(shouldBlockRequest('POST', '/api/v1/workspaces/ws-1/extract/?dry_run=true')).toBe(
      false,
    );
  });
});

describe('BLOCKING_EXCLUSIONS', () => {
  it('has exactly four entries, each carrying a written-down reason', () => {
    expect(BLOCKING_EXCLUSIONS).toHaveLength(4);
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

    // Exactly the task resource: the bare id matches, a sub-resource and a
    // prefix-sharing sibling do not.
    expect(BLOCKING_EXCLUSIONS[3].match.test('/api/v1/tasks/t-1')).toBe(true);
    expect(BLOCKING_EXCLUSIONS[3].match.test('/api/v1/tasks/t-1/comments')).toBe(false);
    expect(BLOCKING_EXCLUSIONS[3].match.test('/api/v1/tasks-bulk/x')).toBe(false);
  });
});
