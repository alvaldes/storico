import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { TrelloCredentialsForm } from '@/components/react/TrelloCredentialsForm';
import { getTrelloConfig, getTrelloConfigStatus, upsertTrelloConfig } from '@/lib/trello-api';
import { toast } from 'sonner';

vi.mock('@/lib/trello-api', () => ({
  getTrelloConfig: vi.fn(),
  getTrelloConfigStatus: vi.fn(),
  upsertTrelloConfig: vi.fn(),
}));

// The toast is part of the save contract — the form has to *tell* the admin the
// save landed — so it is mocked to be assertable rather than rendered.
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const WS_ID = 'ws-1';
const SECRET_KEY = 'trello-key-abc123';
const SECRET_TOKEN = 'trello-token-xyz789-enough-length-to-be-real';

/**
 * Render the form as the workspace settings page does.
 *
 * The page knows the role from the workspace read, so the form receives it —
 * the admin split is a prop, not a 403 the form discovers.
 */
function renderForm(isAdmin: boolean) {
  return render(<TrelloCredentialsForm locale="en" workspaceId={WS_ID} isAdmin={isAdmin} />);
}

describe('TrelloCredentialsForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a member the status line only — no credential input, and no secret read', async () => {
    // The admin GET answers the decrypted pair; the member form must never call
    // it, so whatever it returns cannot reach a member's DOM.
    vi.mocked(getTrelloConfigStatus).mockResolvedValue({
      configured: false,
      missing: ['api_key', 'token'],
    });
    vi.mocked(getTrelloConfig).mockResolvedValue({ apiKey: SECRET_KEY, token: SECRET_TOKEN });

    renderForm(false);

    await waitFor(() => expect(getTrelloConfigStatus).toHaveBeenCalledWith(WS_ID));
    expect(getTrelloConfig).not.toHaveBeenCalled();
    expect(screen.queryByDisplayValue(SECRET_KEY)).toBeNull();
    expect(screen.queryByDisplayValue(SECRET_TOKEN)).toBeNull();
    expect(screen.queryByLabelText('API key')).toBeNull();
    expect(screen.queryByLabelText('Token')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Save Trello credentials' })).toBeNull();
  });

  it('tells a member the workspace is not configured before an export can run', async () => {
    vi.mocked(getTrelloConfigStatus).mockResolvedValue({
      configured: false,
      missing: ['api_key', 'token'],
    });

    renderForm(false);

    expect(
      await screen.findByText('This workspace has no Trello credentials yet.'),
    ).toBeInTheDocument();
    expect(screen.getByText(/Missing: API key, Token/)).toBeInTheDocument();
  });

  it('tells a member the workspace is configured when it is', async () => {
    vi.mocked(getTrelloConfigStatus).mockResolvedValue({ configured: true, missing: [] });

    renderForm(false);

    expect(
      await screen.findByText('Trello credentials are configured for this workspace.'),
    ).toBeInTheDocument();
  });

  it('prefills the admin fields with exactly what the API returned — and nothing when it returns nothing', async () => {
    // The API returns the decrypted pair, so the fields may carry it. When it
    // answers null (nothing stored yet) the fields stay empty: the form never
    // fabricates a value the API did not hand over.
    vi.mocked(getTrelloConfigStatus).mockResolvedValue({ configured: true, missing: [] });
    vi.mocked(getTrelloConfig).mockResolvedValue({ apiKey: SECRET_KEY, token: SECRET_TOKEN });

    const { rerender } = renderForm(true);
    expect(await screen.findByDisplayValue(SECRET_KEY)).toBeInTheDocument();
    expect(screen.getByDisplayValue(SECRET_TOKEN)).toBeInTheDocument();

    vi.mocked(getTrelloConfig).mockResolvedValue({ apiKey: null, token: null });
    rerender(<TrelloCredentialsForm locale="en" workspaceId={WS_ID} isAdmin={true} key="fresh" />);
    await waitFor(() => expect(getTrelloConfig).toHaveBeenCalledTimes(2));
    expect(screen.queryByDisplayValue(SECRET_KEY)).toBeNull();
    expect(screen.queryByDisplayValue(SECRET_TOKEN)).toBeNull();
  });

  it('saves the typed pair and then rereads the status, so the line flips with the save', async () => {
    const user = userEvent.setup();
    // First status read: unconfigured. The second (after the save) is what the
    // test waits for — the save must refresh the line, not leave it stale.
    vi.mocked(getTrelloConfigStatus)
      .mockResolvedValueOnce({ configured: false, missing: ['api_key', 'token'] })
      .mockResolvedValueOnce({ configured: true, missing: [] });
    vi.mocked(getTrelloConfig).mockResolvedValue({ apiKey: null, token: null });
    vi.mocked(upsertTrelloConfig).mockResolvedValue({ apiKey: SECRET_KEY, token: SECRET_TOKEN });

    renderForm(true);

    await user.type(await screen.findByLabelText('API key'), SECRET_KEY);
    await user.type(await screen.findByLabelText('Token'), SECRET_TOKEN);
    await user.click(screen.getByRole('button', { name: 'Save Trello credentials' }));

    await waitFor(() =>
      expect(upsertTrelloConfig).toHaveBeenCalledWith(WS_ID, {
        apiKey: SECRET_KEY,
        token: SECRET_TOKEN,
      }),
    );
    expect(toast.success).toHaveBeenCalledWith('Trello credentials saved');
    await waitFor(() => expect(getTrelloConfigStatus).toHaveBeenCalledTimes(2));
    expect(
      await screen.findByText('Trello credentials are configured for this workspace.'),
    ).toBeInTheDocument();
  });

  it('reports a failed save through the toast instead of losing it', async () => {
    const user = userEvent.setup();
    vi.mocked(getTrelloConfigStatus).mockResolvedValue({ configured: true, missing: [] });
    vi.mocked(getTrelloConfig).mockResolvedValue({ apiKey: SECRET_KEY, token: SECRET_TOKEN });
    vi.mocked(upsertTrelloConfig).mockRejectedValue(new Error('the put was refused'));

    renderForm(true);

    await user.click(await screen.findByRole('button', { name: 'Save Trello credentials' }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'Could not save the Trello credentials',
        expect.objectContaining({ description: 'the put was refused' }),
      ),
    );
  });
});
