import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { toast } from 'sonner';

import { AccountPage } from '@/components/react/AccountPage';
import { useSettingsStore } from '@/stores/settingsStore';
import { DEFAULT_SETTINGS } from '@/types/settings';
import { fetchSettings, saveSettings } from '@/lib/settings-api';

vi.mock('@/lib/settings-api', () => ({
  fetchSettings: vi.fn(),
  saveSettings: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { loading: vi.fn(() => 'toast-id'), success: vi.fn(), error: vi.fn() },
}));

// The page reads the signed-in user for its profile card; the subject here is the export
// preference, so the session is a constant.
vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({
    user: { name: 'Ada Lovelace', email: 'ada@example.com', provider: 'github' },
    loading: false,
  }),
}));

describe('AccountPage — the default export format', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchSettings).mockResolvedValue({
      preferences: DEFAULT_SETTINGS,
      updated_at: '2026-01-01T00:00:00Z',
    });
    vi.mocked(saveSettings).mockResolvedValue({
      preferences: { export: { defaultFormat: 'markdown' } },
      updated_at: '2026-01-01T00:00:00Z',
    });
    useSettingsStore.setState({
      settings: DEFAULT_SETTINGS,
      apiSaving: false,
      lastSaveResult: 'idle',
    });
  });

  async function renderPage() {
    render(<AccountPage locale="en" />);
    // The page renders a spinner until it has mounted and asked for the stored preferences.
    return screen.findByLabelText('Default Format');
  }

  it('persists the change instead of only updating the store', async () => {
    const user = userEvent.setup();
    const trigger = await renderPage();

    await user.click(trigger);
    await user.click(await screen.findByRole('option', { name: 'Markdown' }));

    // The select used to call `setExportFormat` alone, so the choice looked saved and came
    // back to its previous value on the next visit.
    await waitFor(() =>
      expect(saveSettings).toHaveBeenCalledWith({ export: { defaultFormat: 'markdown' } }),
    );
  });

  it('reports the save with translated copy, from the caller', async () => {
    const user = userEvent.setup();
    const trigger = await renderPage();

    await user.click(trigger);
    await user.click(await screen.findByRole('option', { name: 'Trello' }));

    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        'Preferences saved',
        expect.objectContaining({
          description: 'Your default export format is saved to your account.',
        }),
      ),
    );
  });

  it('shows the stored value when the page loads', async () => {
    vi.mocked(fetchSettings).mockResolvedValue({
      preferences: { export: { defaultFormat: 'trello' } },
      updated_at: '2026-01-01T00:00:00Z',
    });

    const trigger = await renderPage();

    await waitFor(() => expect(trigger).toHaveTextContent('Trello'));
  });

  it('reports a failed save without pretending it worked', async () => {
    const user = userEvent.setup();
    vi.mocked(saveSettings).mockRejectedValue(new Error('the API is down'));
    const trigger = await renderPage();

    await user.click(trigger);
    await user.click(await screen.findByRole('option', { name: 'JSON' }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'Could not save preferences',
        expect.objectContaining({ description: 'the API is down' }),
      ),
    );
    expect(toast.success).not.toHaveBeenCalled();
  });
});
