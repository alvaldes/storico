import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { toast } from 'sonner';

import { AccountPage } from '@/components/react/AccountPage';
import { api, ApiRequestError } from '@/lib/api';
import { useSettingsStore } from '@/stores/settingsStore';
import { DEFAULT_SETTINGS, type ExportFormat } from '@/types/settings';
import { fetchSettings, saveSettings } from '@/lib/settings-api';
import { getTranslations } from '@/i18n/utils';

const t = getTranslations('en');

vi.mock('@/lib/settings-api', () => ({
  fetchSettings: vi.fn(),
  saveSettings: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { loading: vi.fn(() => 'toast-id'), success: vi.fn(), error: vi.fn() },
}));

// The page reads the signed-in user for its profile card; the subject here is the export
// preference, so the session is a constant. The mock honors the selector: the
// delete-account dialog reads `user` and `clear` separately (D-a-4 carry case below).
vi.mock('@/stores/authStore', () => ({
  useAuthStore: (selector?: (s: unknown) => unknown) => {
    const state = {
      user: { name: 'Ada Lovelace', email: 'ada@example.com', provider: 'github' },
      loading: false,
      clear: vi.fn(),
    };
    return selector ? selector(state) : state;
  },
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
    await user.click(await screen.findByRole('option', { name: 'JSON' }));

    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        'Preferences saved',
        expect.objectContaining({
          description: 'Your default export format is saved to your account.',
        }),
      ),
    );
  });

  it('renders a retired stored value as the format it now means', async () => {
    vi.mocked(fetchSettings).mockResolvedValue({
      // The cast models a value arriving from outside this build's contract, which is what a
      // row stored before `trello` was retired is. Without the normalisation the label lookup
      // returns `undefined` and the control renders blank.
      preferences: { export: { defaultFormat: 'trello' as unknown as ExportFormat } },
      updated_at: '2026-01-01T00:00:00Z',
    });

    const trigger = await renderPage();

    await waitFor(() => expect(trigger).toHaveTextContent('JSON'));
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

/* ── The delete-account refusal (0.9.0 slice b, D-a-4 carry) ──
 *
 * The backend answers 409 `ACCOUNT_DELETE_BLOCKED` when an account still has standing
 * revocations, and its `errorCodes` copy is mirrored in both locales. The dialog must
 * render that code's localized headline through the error-code map — never the raw
 * error the HTTP layer built, whose object detail degrades to the status text.
 */
describe('AccountPage — the delete-account refusal', () => {
  it('renders the ACCOUNT_DELETE_BLOCKED refusal through the error-code map, never a raw status', async () => {
    const user = userEvent.setup();
    // Built the way the backend's 409 envelope arrives: the canonical `error_code`
    // beside an object `detail` that names the blocking marks. The API layer turns the
    // object detail into the status text — exactly what the user must not be shown.
    const deleteSpy = vi.spyOn(api, 'delete').mockRejectedValue(
      new ApiRequestError(
        409,
        'Conflict',
        { message: 'Account deletion is blocked by 2 standing revocations.', count: 2, marks: [] },
        {
          detail: { message: 'Account deletion is blocked by 2 standing revocations.', count: 2, marks: [] },
          error_code: 'ACCOUNT_DELETE_BLOCKED',
        },
      ),
    );

    render(<AccountPage locale="en" />);
    await screen.findByLabelText('Default Format');

    await user.click(screen.getByRole('button', { name: t.settings.danger_delete_account }));
    const dialog = await screen.findByRole('dialog');

    const inputs = within(dialog).getAllByRole('textbox');
    await user.type(inputs[0], 'ada@example.com');
    await user.type(inputs[1], 'delete my personal account');
    await user.click(
      within(dialog).getByRole('button', { name: t.settings.danger_delete_dialog_confirm }),
    );

    expect(deleteSpy).toHaveBeenCalledWith('/api/v1/users/me');

    // The designed refusal is the code's localized sentence...
    expect(await screen.findByText(t.errorCodes.ACCOUNT_DELETE_BLOCKED)).toBeInTheDocument();
    // ...never the status text the raw error carried, and never a bare status number.
    expect(screen.queryByText('Conflict')).not.toBeInTheDocument();
    expect(screen.queryByText(/409/)).not.toBeInTheDocument();
  });
});
