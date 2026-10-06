// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

import { StatusPanel } from '@/components/react/StatusPanel';
import { fetchServiceHealth } from '@/lib/status-health-api';

vi.mock('@/lib/status-health-api', () => ({
  fetchServiceHealth: vi.fn(),
}));

/**
 * Why this assertion lives in its own file, alone.
 *
 * React logs `Each child in a list should have a unique "key" prop` **once per message per
 * module instance**. Inside the main StatusPanel suite an earlier render has already emitted
 * it, so a spy placed there observes nothing and the assertion passes vacuously — a passing
 * test that proves nothing, which is worse than no test at all. Measured, not assumed: the
 * same assertion added to `StatusPanel.test.tsx` passed against the unfixed component.
 *
 * A fresh file gets a fresh module registry, so the render here is the first render
 * anywhere and the spy is a real witness. If the warning ever stops being deduped, this
 * test keeps working; if the suite is ever merged into one file, it stops being a witness.
 */
describe('StatusPanel row keys', () => {
  it('renders its rows with keys, so React logs no list-key warning', () => {
    vi.mocked(fetchServiceHealth).mockReturnValue(new Promise(() => {}));
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(<StatusPanel locale="en" />);

    const keyWarnings = errorSpy.mock.calls
      .map((call) => String(call[0]))
      .filter((message) => message.includes('unique "key" prop'));
    errorSpy.mockRestore();

    expect(keyWarnings).toEqual([]);
  });
});
