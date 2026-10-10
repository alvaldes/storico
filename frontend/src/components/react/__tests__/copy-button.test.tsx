import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { CopyButton, copyToClipboard } from '@/components/ui/copy-button';

function stubClipboard(): ReturnType<typeof vi.fn> {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText },
    configurable: true,
  });
  return writeText;
}

describe('copyToClipboard', () => {
  it('writes the text and reports success', async () => {
    const writeText = stubClipboard();

    await expect(copyToClipboard('the body')).resolves.toBe(true);
    expect(writeText).toHaveBeenCalledWith('the body');
  });

  it('reports failure instead of throwing when the clipboard refuses', async () => {
    // The clipboard API is not available in every context; a copy that cannot
    // happen is a quiet no, never an unhandled rejection.
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
      configurable: true,
    });

    await expect(copyToClipboard('the body')).resolves.toBe(false);
  });

  it('reports failure when there is no clipboard at all', async () => {
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });

    await expect(copyToClipboard('the body')).resolves.toBe(false);
  });
});

describe('CopyButton', () => {
  it('writes its text to the clipboard and announces the copied state', async () => {
    const user = userEvent.setup();
    const writeText = stubClipboard();

    render(<CopyButton text="the body" label="Copy" copiedLabel="Copied!" />);

    const button = screen.getByRole('button', { name: 'Copy' });
    await user.click(button);

    expect(writeText).toHaveBeenCalledWith('the body');
    expect(screen.getByRole('button', { name: 'Copied!' })).toBeInTheDocument();
  });

  it('keeps the idle name when the write did not happen', async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
      configurable: true,
    });

    render(<CopyButton text="the body" label="Copy" copiedLabel="Copied!" />);
    await user.click(screen.getByRole('button', { name: 'Copy' }));

    expect(screen.getByRole('button', { name: 'Copy' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Copied!' })).not.toBeInTheDocument();
  });

  it('reverts to the idle name after a moment', async () => {
    // A short reset window instead of fake timers: userEvent's own event loop
    // and fake timers agree badly, and the claim — the copied state is momentary
    // — is the same claim at 10 ms that it is at 2000.
    const user = userEvent.setup();
    stubClipboard();

    render(
      <CopyButton text="the body" label="Copy" copiedLabel="Copied!" copiedResetMs={10} />,
    );
    await user.click(screen.getByRole('button', { name: 'Copy' }));
    expect(screen.getByRole('button', { name: 'Copied!' })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Copy' })).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: 'Copied!' })).not.toBeInTheDocument();
  });
});
