import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { LoadingVeil } from '@/components/react/LoadingVeil';

/**
 * The veil is presentational: it always renders when mounted, and visibility is
 * the caller's decision. These cases pin the accessibility contract (one polite
 * status region carrying the caller's label) that both consumers — the
 * mutation-driven `FullPageLoader` and the Kanban board's reads — inherit.
 */
describe('LoadingVeil', () => {
  it('renders a polite status region carrying the given label', () => {
    render(<LoadingVeil label="Loading..." />);

    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-live', 'polite');
    expect(status).toHaveTextContent('Loading...');
  });

  it('renders whatever label it is given — the copy belongs to the caller', () => {
    render(<LoadingVeil label="Procesando..." />);

    expect(screen.getByRole('status')).toHaveTextContent('Procesando...');
  });
});
