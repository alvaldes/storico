import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ErrorDisplay } from '@/components/react/ErrorDisplay';
import { useTranslations } from '@/i18n/utils';

const t = useTranslations('en');

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ErrorDisplay — the failure it reports', () => {
  it('announces itself and shows the caller’s message', () => {
    render(<ErrorDisplay friendlyMessage="Could not load the board" />);

    // `role="alert"` is what makes a banner that appears after a failure reach a screen
    // reader; it rendered `null` before, so nothing was announced and nothing was shown.
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Could not load the board')).toBeInTheDocument();
  });

  it('shows the status and the error code together when it has both', () => {
    render(
      <ErrorDisplay
        friendlyMessage="Incomplete configuration"
        status={400}
        errorCode="LLM_CONFIG_INCOMPLETE"
      />,
    );

    expect(screen.getByText('HTTP 400 • LLM_CONFIG_INCOMPLETE')).toBeInTheDocument();
  });

  it('shows the status alone when there is no code', () => {
    render(<ErrorDisplay friendlyMessage="Boom" status={500} />);

    expect(screen.getByText('HTTP 500')).toBeInTheDocument();
  });

  it('shows no status line at all when it has neither', () => {
    render(<ErrorDisplay friendlyMessage="Boom" />);

    expect(screen.queryByText(/HTTP/)).not.toBeInTheDocument();
  });
});

describe('ErrorDisplay — the actions it offers', () => {
  it('offers no retry unless the caller gives one', () => {
    render(<ErrorDisplay friendlyMessage="Boom" />);

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('retries with the caller’s label', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<ErrorDisplay friendlyMessage="Boom" onRetry={onRetry} retryLabel="Try again" />);

    await user.click(screen.getByRole('button', { name: 'Try again' }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('falls back to the shared retry label', () => {
    render(<ErrorDisplay friendlyMessage="Boom" onRetry={vi.fn()} />);

    expect(screen.getByRole('button', { name: t.common.retry })).toBeInTheDocument();
  });

  it('dismisses through a button a screen reader can name', async () => {
    const user = userEvent.setup();
    const onDismiss = vi.fn();
    render(<ErrorDisplay friendlyMessage="Boom" onDismiss={onDismiss} />);

    // The dismiss control had no accessible name before this change: an icon-only button
    // with no text, announced as "button".
    await user.click(screen.getByRole('button', { name: t.errorDisplay.dismiss }));

    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('offers no dismiss unless the caller gives one', () => {
    render(<ErrorDisplay friendlyMessage="Boom" />);

    expect(
      screen.queryByRole('button', { name: t.errorDisplay.dismiss }),
    ).not.toBeInTheDocument();
  });
});

describe('ErrorDisplay — the raw detail behind the message', () => {
  it('offers no toggle when there is no detail to show', () => {
    render(<ErrorDisplay friendlyMessage="Boom" />);

    expect(
      screen.queryByRole('button', { name: t.errorDisplay.raw_response }),
    ).not.toBeInTheDocument();
  });

  it('offers no toggle for a null detail either', () => {
    render(<ErrorDisplay friendlyMessage="Boom" rawDetail={null} />);

    expect(
      screen.queryByRole('button', { name: t.errorDisplay.raw_response }),
    ).not.toBeInTheDocument();
  });

  it('offers no toggle for an empty detail', () => {
    render(<ErrorDisplay friendlyMessage="Boom" rawDetail="" />);

    // An empty string is not a detail: the toggle would open onto an empty panel.
    expect(
      screen.queryByRole('button', { name: t.errorDisplay.raw_response }),
    ).not.toBeInTheDocument();
  });

  it('shows a detail whose text happens to be the placeholder', async () => {
    const user = userEvent.setup();
    // The gate used to compare the formatted text against the placeholder string, which
    // silently dropped a caller whose detail *is* that text.
    render(<ErrorDisplay friendlyMessage="Boom" rawDetail="(no detail provided)" />);

    await user.click(screen.getByRole('button', { name: t.errorDisplay.raw_response }));

    expect(screen.getByRole('region')).toHaveTextContent('(no detail provided)');
  });

  it('starts collapsed, discloses the detail on demand, and reports its state', async () => {
    const user = userEvent.setup();
    render(<ErrorDisplay friendlyMessage="Boom" rawDetail="gateway said no" />);

    const toggle = screen.getByRole('button', { name: t.errorDisplay.raw_response });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('region')).not.toBeInTheDocument();

    await user.click(toggle);

    expect(screen.getByRole('button', { name: t.errorDisplay.raw_response })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    const region = screen.getByRole('region', { name: t.errorDisplay.raw_response });
    expect(region).toHaveTextContent('gateway said no');
  });

  it('swaps the visible label with the state', async () => {
    const user = userEvent.setup();
    render(<ErrorDisplay friendlyMessage="Boom" rawDetail="detail" />);

    // Both labels live in the DOM and CSS hides the inactive one; the button's accessible
    // name is stable (`raw_response`) so the hidden copy cannot leak into it.
    expect(screen.getByText(t.errorDisplay.show_details)).toBeInTheDocument();
    expect(screen.getByText(t.errorDisplay.hide_details)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: t.errorDisplay.raw_response }));

    expect(screen.getByText(t.errorDisplay.show_details)).toBeInTheDocument();
  });

  it('pretty-prints an object detail', async () => {
    const user = userEvent.setup();
    render(
      <ErrorDisplay
        friendlyMessage="Boom"
        rawDetail={{ error_code: 'LLM_CONFIG_INCOMPLETE', missing: ['model'] }}
      />,
    );

    await user.click(screen.getByRole('button', { name: t.errorDisplay.raw_response }));

    expect(screen.getByRole('region')).toHaveTextContent('"error_code": "LLM_CONFIG_INCOMPLETE"');
    expect(screen.getByRole('region')).toHaveTextContent('"missing"');
  });

  it('joins an array detail', async () => {
    const user = userEvent.setup();
    render(<ErrorDisplay friendlyMessage="Boom" rawDetail={['first', 'second']} />);

    await user.click(screen.getByRole('button', { name: t.errorDisplay.raw_response }));

    expect(screen.getByRole('region')).toHaveTextContent('first');
    expect(screen.getByRole('region')).toHaveTextContent('second');
  });

  it('copies exactly what it shows', async () => {
    const user = userEvent.setup();
    render(<ErrorDisplay friendlyMessage="Boom" rawDetail={{ detail: 'boom' }} />);

    await user.click(screen.getByRole('button', { name: t.errorDisplay.raw_response }));
    await user.click(screen.getByRole('button', { name: t.errorDisplay.copy }));

    // Read it back the way a paste would. `userEvent.setup()` owns the clipboard stub, which
    // is also why this test does not install one: doing so would be replaced by it.
    await expect(navigator.clipboard.readText()).resolves.toContain('"detail": "boom"');
  });

  it('reports that the copy happened', async () => {
    const user = userEvent.setup();
    render(<ErrorDisplay friendlyMessage="Boom" rawDetail="detail" />);

    await user.click(screen.getByRole('button', { name: t.errorDisplay.raw_response }));
    await user.click(screen.getByRole('button', { name: t.errorDisplay.copy }));

    // The state change is announced, not just drawn: the prior implementation flipped an
    // icon and said nothing.
    expect(
      await screen.findByRole('button', { name: t.errorDisplay.copied }),
    ).toBeInTheDocument();
  });
});
