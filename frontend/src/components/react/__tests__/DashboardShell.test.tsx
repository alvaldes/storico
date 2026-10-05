import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DashboardShell } from '@/components/react/DashboardShell';
import { useLoadingStore } from '@/stores/loadingStore';

// NavUser / MobileNav import `signOut` from the auth-astro virtual client;
// mock it so the module resolves under vitest and no real sign-out path is
// reachable (same pattern as app-sidebar.test.tsx).
vi.mock('auth-astro/client', () => ({ signOut: vi.fn() }));

/**
 * DashboardShell is the single mount point for the blocking loader, because
 * every ApiClient mutation in the app happens under it. This test pins that
 * the mount exists: the loader is absent until the store raises it, and the
 * overlay renders inside the shell when it does.
 */
describe('DashboardShell — FullPageLoader mount point', () => {
  beforeEach(() => {
    useLoadingStore.setState({ pending: 0, visible: false });
    // fetchFullUserProfile fires from the shell's bootstrap effect; the
    // network itself must stay inert in jsdom.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ user: null }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );
  });

  it('does not render the blocking overlay until the store raises it', () => {
    render(
      <DashboardShell locale="en" currentPath="/dashboard" userJson="">
        <div>page content</div>
      </DashboardShell>,
    );

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByText('page content')).toBeInTheDocument();
  });

  it('renders the overlay inside the shell once the loading store flips visible', () => {
    useLoadingStore.setState({ visible: true });
    render(
      <DashboardShell locale="en" currentPath="/dashboard" userJson="">
        <div>page content</div>
      </DashboardShell>,
    );

    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('Processing...');
  });
});
