import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { FullPageLoader } from '@/components/react/FullPageLoader';
import { useLoadingStore } from '@/stores/loadingStore';

/**
 * Visibility is driven straight through the store: the component's only
 * reactive input is the boolean `visible` selector, so setting it is the
 * contract being rendered — no timers involved.
 */
describe('FullPageLoader', () => {
  beforeEach(() => {
    useLoadingStore.setState({ pending: 0, visible: false });
  });

  it('renders nothing while the loader is hidden', () => {
    const { container } = render(<FullPageLoader locale="en" />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the status region with the English label when visible', () => {
    useLoadingStore.setState({ visible: true });
    render(<FullPageLoader locale="en" />);

    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-live', 'polite');
    expect(status).toHaveTextContent('Processing...');
  });

  it('renders the neutral Spanish label when locale is es', () => {
    useLoadingStore.setState({ visible: true });
    render(<FullPageLoader locale="es" />);

    expect(screen.getByRole('status')).toHaveTextContent('Procesando...');
  });

  it('hides again when the store flips back to false', () => {
    useLoadingStore.setState({ visible: true });
    render(<FullPageLoader locale="en" />);
    expect(screen.getByRole('status')).toBeInTheDocument();

    // Wrapped in act so the zustand subscription flushes before the query.
    act(() => {
      useLoadingStore.setState({ visible: false });
    });
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
