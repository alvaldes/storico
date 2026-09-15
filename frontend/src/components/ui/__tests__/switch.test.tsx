import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

import { Switch } from '../switch';

describe('Switch', () => {
  it('exposes switch semantics with an accessible name', () => {
    render(<Switch checked={false} onCheckedChange={vi.fn()} aria-label="Automatic few-shot" />);

    const control = screen.getByRole('switch', { name: 'Automatic few-shot' });
    expect(control).toHaveAttribute('aria-checked', 'false');
  });

  it('reflects the checked state through aria-checked', () => {
    const { rerender } = render(<Switch checked={false} aria-label="probe" />);
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false');

    rerender(<Switch checked={true} aria-label="probe" />);
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true');
  });

  it('renders the data attributes the base-nova styles depend on', () => {
    const { rerender } = render(<Switch checked={false} aria-label="probe" />);
    // `data-unchecked:bg-input` / `data-checked:bg-primary` are the only visual
    // state hooks in the registry styles, so a silent attribute change would
    // leave an unstyled control.
    expect(screen.getByRole('switch')).toHaveAttribute('data-unchecked');
    expect(screen.getByRole('switch')).not.toHaveAttribute('data-checked');

    rerender(<Switch checked={true} aria-label="probe" />);
    expect(screen.getByRole('switch')).toHaveAttribute('data-checked');
    expect(screen.getByRole('switch')).not.toHaveAttribute('data-unchecked');
  });

  it('keeps the thumb state hooks and the group size hook the knob travel depends on', () => {
    const { container, rerender } = render(<Switch checked={false} aria-label="probe" />);
    const root = () => container.querySelector('[data-slot="switch"]');
    const thumb = () => container.querySelector('[data-slot="switch-thumb"]');

    // The thumb ships no base size and no base position: `size-4`/`size-3` and the
    // `translate-x` travel are gated on the group's `data-size` *and* the thumb's own
    // state hook, so dropping either silently freezes the knob at 0 with the suite green.
    expect(root()).toHaveAttribute('data-size', 'default');
    expect(thumb()).toHaveAttribute('data-unchecked');
    expect(thumb()).not.toHaveAttribute('data-checked');

    rerender(<Switch checked={true} aria-label="probe" />);
    expect(thumb()).toHaveAttribute('data-checked');
    expect(thumb()).not.toHaveAttribute('data-unchecked');

    rerender(<Switch checked={true} size="sm" aria-label="probe" />);
    expect(root()).toHaveAttribute('data-size', 'sm');
  });

  it('reports the next checked value when clicked', () => {
    const onCheckedChange = vi.fn();
    render(<Switch checked={false} onCheckedChange={onCheckedChange} aria-label="probe" />);

    fireEvent.click(screen.getByRole('switch'));
    expect(onCheckedChange).toHaveBeenCalledWith(true, expect.anything());
  });

  it('does not report changes while disabled', () => {
    const onCheckedChange = vi.fn();
    render(
      <Switch checked={false} onCheckedChange={onCheckedChange} disabled aria-label="probe" />,
    );

    fireEvent.click(screen.getByRole('switch'));
    expect(onCheckedChange).not.toHaveBeenCalled();
  });
});
