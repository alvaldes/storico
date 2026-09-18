import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { CustomProviderDialog } from '@/components/react/CustomProviderDialog';
import { createCustomProvider, renameCustomProvider } from '@/lib/custom-providers-api';
import type { CustomProvider } from '@/types/workspace';

vi.mock('@/lib/custom-providers-api', () => ({
  createCustomProvider: vi.fn(),
  renameCustomProvider: vi.fn(),
}));

const WORKSPACE_ID = 'ws-1';

const savedProvider: CustomProvider = {
  id: 'cp-1',
  workspaceId: WORKSPACE_ID,
  name: 'My Gateway v2',
  createdAt: '2026-09-18T00:00:00Z',
  updatedAt: '2026-09-18T00:00:00Z',
};

/**
 * The name field of the custom-provider dialog.
 *
 * These tests pin the two things the slug rule used to decide for the user: the
 * name is free-form text stored as typed, and the 50-character cap is visible in the
 * field instead of arriving as a rejection.
 */
describe('CustomProviderDialog name field', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(createCustomProvider).mockResolvedValue(savedProvider);
    vi.mocked(renameCustomProvider).mockResolvedValue(savedProvider);
  });

  function renderDialog(provider: CustomProvider | null = null) {
    const onSaved = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <CustomProviderDialog
        locale="en"
        workspaceId={WORKSPACE_ID}
        provider={provider}
        open
        onOpenChange={onOpenChange}
        onSaved={onSaved}
      />,
    );
    return { onSaved, onOpenChange, field: screen.getByLabelText('Provider name') };
  }

  it('starts the counter at the empty length', () => {
    renderDialog();

    expect(screen.getByText('0/50')).toBeDefined();
  });

  it('counts what is typed', async () => {
    const user = userEvent.setup();
    const { field } = renderDialog();

    await user.type(field, 'Ünïcode');

    expect(screen.getByText('7/50')).toBeDefined();
  });

  it('stops the field at the limit and shows it full', async () => {
    const user = userEvent.setup();
    const { field } = renderDialog();

    await user.type(field, 'a'.repeat(60));

    expect(field).toHaveAttribute('maxlength', '50');
    expect((field as HTMLInputElement).value).toHaveLength(50);
    expect(screen.getByText('50/50')).toBeDefined();
  });

  it('saves a name with an uppercase letter and a space exactly as typed', async () => {
    const user = userEvent.setup();
    const { onSaved, field } = renderDialog();

    await user.type(field, 'My Gateway v2');
    await user.click(screen.getByRole('button', { name: 'Add provider' }));

    await waitFor(() =>
      expect(createCustomProvider).toHaveBeenCalledWith(WORKSPACE_ID, { name: 'My Gateway v2' }),
    );
    expect(onSaved).toHaveBeenCalledWith(savedProvider);
  });

  it('trims the padding before it sends the name', async () => {
    const user = userEvent.setup();
    const { field } = renderDialog();

    await user.type(field, '  Groq  ');
    await user.click(screen.getByRole('button', { name: 'Add provider' }));

    await waitFor(() =>
      expect(createCustomProvider).toHaveBeenCalledWith(WORKSPACE_ID, { name: 'Groq' }),
    );
  });

  it('refuses a built-in provider in any casing', async () => {
    const user = userEvent.setup();
    const { field } = renderDialog();

    await user.type(field, 'OpenAI');
    await user.click(screen.getByRole('button', { name: 'Add provider' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'That name is a built-in provider. Choose a different name.',
    );
    expect(createCustomProvider).not.toHaveBeenCalled();
  });

  it('refuses the selector control value with its own message', async () => {
    const user = userEvent.setup();
    const { field } = renderDialog();

    await user.type(field, '__add_custom_provider__');
    await user.click(screen.getByRole('button', { name: 'Add provider' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'That name is reserved by the provider selector. Choose a different name.',
    );
    expect(createCustomProvider).not.toHaveBeenCalled();
  });

  it('counts the prefilled name when renaming and allows a casing-only change', async () => {
    const user = userEvent.setup();
    const existing: CustomProvider = { ...savedProvider, name: 'groq', id: 'cp-2' };
    const { field } = renderDialog(existing);

    expect(screen.getByText('4/50')).toBeDefined();

    await user.clear(field);
    await user.type(field, 'Groq');
    await user.click(screen.getByRole('button', { name: 'Save name' }));

    await waitFor(() =>
      expect(renameCustomProvider).toHaveBeenCalledWith(WORKSPACE_ID, 'cp-2', { name: 'Groq' }),
    );
  });
});
