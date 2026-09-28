import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { StatusPanel } from '@/components/react/StatusPanel';
import { fetchServiceHealth, type HealthOutcome } from '@/lib/status-health-api';
import type { ServicesHealth, ServiceStatus } from '@/lib/health';

vi.mock('@/lib/status-health-api', () => ({
  fetchServiceHealth: vi.fn(),
}));

/** All five backend probes reporting ok, as a settled healthy deployment would answer. */
const ALL_OK_HEALTH: ServicesHealth = {
  status: 'ok',
  version: '1.0.0',
  timestamp: '2026-09-25T12:00:00Z',
  services: {
    database: { status: 'ok', latency_ms: 2 },
    schema: { status: 'ok', latency_ms: 1 },
    ollama: { status: 'ok', latency_ms: 5, model_count: 3 },
    qdrant: { status: 'ok', latency_ms: 4 },
    embeddings: { status: 'ok', latency_ms: 8, provider: 'ollama', model: 'nomic-embed-text' },
  },
};

const OK_OUTCOME: HealthOutcome = { kind: 'ok', health: ALL_OK_HEALTH };

function healthWithOverrides(
  overrides: Record<string, { status: ServiceStatus['status'] }>,
): ServicesHealth {
  return {
    ...ALL_OK_HEALTH,
    status: 'degraded',
    services: Object.fromEntries(
      Object.entries(ALL_OK_HEALTH.services).map(([name, probe]) => [
        name,
        { ...probe, ...overrides[name] },
      ]),
    ),
  } as ServicesHealth;
}

describe('StatusPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  /**
   * THE regression this island exists for: the document must be complete on the very
   * first synchronous render, before any network result. The old page awaited the
   * backend in its frontmatter and blocked the whole HTML document on it (measured
   * TTFB 2.19–2.54 s, up to 10 s of blank page with the backend down). Here the rows
   * and their pending loaders exist immediately; only the badges fill in later.
   */
  it('renders all six rows with pending badges synchronously, before any fetch resolves', () => {
    vi.mocked(fetchServiceHealth).mockReturnValue(new Promise(() => {}));

    render(<StatusPanel locale="en" />);

    // No `await` before these assertions: the panel is complete on first paint.
    expect(screen.getByText('API Server')).toBeDefined();
    expect(screen.getByText('Database')).toBeDefined();
    expect(screen.getByText('Database schema')).toBeDefined();
    expect(screen.getByText('Ollama default host')).toBeDefined();
    expect(screen.getByText('Vector Store')).toBeDefined();
    expect(screen.getByText('Embeddings')).toBeDefined();

    // One pending badge per row (the "Last updated" line also says Checking… while
    // pending, so six or more occurrences), and the region announces it is busy.
    expect(screen.getAllByText('Checking…').length).toBeGreaterThanOrEqual(6);
    expect(screen.getByRole('region')).toHaveAttribute('aria-busy', 'true');
  });

  it('fills every row as Operational and the banner as green when an all-ok payload lands', async () => {
    vi.mocked(fetchServiceHealth).mockResolvedValue(OK_OUTCOME);

    render(<StatusPanel locale="en" />);

    await waitFor(() => expect(screen.getAllByText('Operational')).toHaveLength(6));
    expect(screen.getByText('All systems operational')).toBeDefined();
    expect(screen.getByText('Storico services are running normally.')).toBeDefined();

    // "Last updated" shows the settled timestamp, not a perpetual Checking….
    expect(screen.getByText(/Last updated/)).toBeDefined();
    expect(screen.getByText(/2026/)).toBeDefined();
    expect(screen.getByRole('region')).toHaveAttribute('aria-busy', 'false');
  });

  it('paints the degraded banner when a core probe fails', async () => {
    vi.mocked(fetchServiceHealth).mockResolvedValue({
      kind: 'ok',
      health: healthWithOverrides({ database: { status: 'error' } }),
    });

    render(<StatusPanel locale="en" />);

    await waitFor(() => expect(screen.getByText('Some systems degraded')).toBeDefined());
    expect(screen.getByText('Some Storico services are experiencing issues.')).toBeDefined();
    // Decision: the failing optional probes must NOT appear in a green-banner note here —
    // the core failure owns the banner.
    expect(screen.queryByText(/Some optional integrations are currently unavailable/)).toBeNull();
  });

  it('keeps the banner green and shows the amber note when only an optional probe fails (D2)', async () => {
    vi.mocked(fetchServiceHealth).mockResolvedValue({
      kind: 'ok',
      health: healthWithOverrides({ ollama: { status: 'error' } }),
    });

    render(<StatusPanel locale="en" />);

    await waitFor(() => expect(screen.getByText('All systems operational')).toBeDefined());
    expect(
      screen.getByText(
        /Some optional integrations are currently unavailable: Ollama default host/,
      ),
    ).toBeDefined();
  });

  it('renders the down copy with the api row Unavailable (not Error) and retries on demand', async () => {
    vi.mocked(fetchServiceHealth).mockResolvedValue({
      kind: 'unavailable',
      reason: 'transport',
    });

    render(<StatusPanel locale="en" />);

    await waitFor(() => expect(screen.getByText('Services unavailable')).toBeDefined());

    // Every row without a document is Unavailable — the api row included. None of them
    // may claim Error: that would be a diagnosis nobody measured.
    expect(screen.getAllByText('Unavailable')).toHaveLength(6);
    expect(screen.queryByText('Error')).toBeNull();

    // Settled without a document: "Last updated" must not claim Checking… forever.
    expect(screen.queryAllByText('Checking…')).toHaveLength(0);

    const retry = screen.getByRole('button', { name: 'Retry' });
    expect(retry).toBeDefined();
    expect(fetchServiceHealth).toHaveBeenCalledTimes(1);

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Retry' }));

    expect(fetchServiceHealth).toHaveBeenCalledTimes(2);

    // Once the second fetch settles, the panel is back to the failure state.
    await waitFor(() =>
      expect(screen.queryAllByText('Checking…')).toHaveLength(0),
    );

    // Back to the pending state synchronously with the click: asserted with a synchronous
    // fireEvent instead of userEvent, whose awaiting would let the mocked promise resolve
    // before the assertion and hide the pending state this case must pin.
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(fetchServiceHealth).toHaveBeenCalledTimes(3);
    expect(screen.getAllByText('Checking…').length).toBeGreaterThanOrEqual(6);
  });

  it('reads the api row as Unknown on http-error while document-less rows stay Unavailable', async () => {
    vi.mocked(fetchServiceHealth).mockResolvedValue({ kind: 'http-error', status: 500 });

    render(<StatusPanel locale="en" />);

    await waitFor(() => expect(screen.getByText('Unknown')).toBeDefined());

    // Something answered (HTTP 500): the api row says Unknown, never Unavailable.
    expect(screen.getByText('Unknown')).toBeDefined();
    expect(screen.getAllByText('Unavailable')).toHaveLength(5);
  });
});
