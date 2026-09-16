import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { FewShotConfigEditor } from '../FewShotConfigEditor';

const renderEditor = (props = {}) => {
  return render(
    <FewShotConfigEditor
      locale="en"
      enabled={true}
      limit={3}
      threshold={0.85}
      onChange={vi.fn()}
      {...props}
    />,
  );
};

/**
 * The slider exposes its label on the named group wrapper; the range input that
 * actually carries the value sits in a thumb that jsdom cannot lay out, so it is
 * only reachable with `hidden: true`.
 */
const getSlider = (name: string) =>
  within(screen.getByRole('group', { name })).getByRole('slider', { hidden: true });

describe('FewShotConfigEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the enabled switch, limit slider, and threshold slider', () => {
    renderEditor();

    expect(screen.getByText('Automatic few-shot examples')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Automatic few-shot examples' })).toBeInTheDocument();
    expect(getSlider('Max examples')).toBeInTheDocument();
    expect(getSlider('Similarity threshold')).toBeInTheDocument();
  });

  it('reflects enabled state through aria-checked', () => {
    const { unmount } = renderEditor({ enabled: true });
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true');
    unmount();

    renderEditor({ enabled: false });
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false');
  });

  it('turns enabled off when the switch is clicked while on', () => {
    const onChange = vi.fn();
    renderEditor({ enabled: true, onChange });

    fireEvent.click(screen.getByRole('switch'));
    expect(onChange).toHaveBeenCalledWith({ enabled: false, limit: 3, threshold: 0.85 });
  });

  it('turns enabled on when the switch is clicked while off', () => {
    const onChange = vi.fn();
    renderEditor({ enabled: false, onChange });

    fireEvent.click(screen.getByRole('switch'));
    expect(onChange).toHaveBeenCalledWith({ enabled: true, limit: 3, threshold: 0.85 });
  });

  it('updates limit on change', () => {
    const onChange = vi.fn();
    renderEditor({ limit: 3, onChange });

    // The limit now steps like the threshold slider: one arrow press is one example.
    fireEvent.keyDown(getSlider('Max examples'), { key: 'ArrowRight' });
    expect(onChange).toHaveBeenCalledWith({ enabled: true, limit: 4, threshold: 0.85 });
  });

  it('shows the limit and threshold values', () => {
    renderEditor({ limit: 7, threshold: 0.9 });
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText('0.90')).toBeInTheDocument();
  });

  it('applies locale-specific translations', () => {
    renderEditor({ locale: 'es' });
    expect(screen.getByText('Ejemplos few-shot automáticos')).toBeInTheDocument();
    expect(screen.getByText('Máximo de ejemplos')).toBeInTheDocument();
  });

  it('disables both sliders while few-shot is off', () => {
    renderEditor({ enabled: false });

    expect(getSlider('Max examples')).toBeDisabled();
    expect(getSlider('Similarity threshold')).toBeDisabled();
  });

  it('names the switch in the active locale', () => {
    const { unmount } = renderEditor({ locale: 'en' });
    expect(screen.getByRole('switch', { name: 'Automatic few-shot examples' })).toBeInTheDocument();
    unmount();

    // The switch carries no visible On/Off text, so its accessible name is the
    // only thing that tells a screen reader which setting it controls.
    renderEditor({ locale: 'es' });
    expect(
      screen.getByRole('switch', { name: 'Ejemplos few-shot automáticos' }),
    ).toBeInTheDocument();
  });
});
