import { render, screen, fireEvent } from '@testing-library/react';
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

describe('FewShotConfigEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the enabled toggle, limit input, and threshold slider', () => {
    renderEditor();

    expect(screen.getByText('Automatic few-shot examples')).toBeInTheDocument();
    expect(screen.getByLabelText('Max examples')).toBeInTheDocument();
    expect(screen.getByText('Similarity threshold')).toBeInTheDocument();
  });

  it('reflects enabled state in the toggle label', () => {
    renderEditor({ enabled: true });
    expect(screen.getByText('On')).toBeInTheDocument();

    renderEditor({ enabled: false });
    expect(screen.getByText('Off')).toBeInTheDocument();
  });

  it('toggles enabled via onClick', () => {
    const onChange = vi.fn();
    renderEditor({ enabled: true, onChange });

    fireEvent.click(screen.getByText('On'));
    expect(onChange).toHaveBeenCalledWith({ enabled: false, limit: 3, threshold: 0.85 });
  });

  it('updates limit on change', () => {
    const onChange = vi.fn();
    renderEditor({ limit: 3, onChange });

    const input = screen.getByLabelText('Max examples');
    fireEvent.change(input, { target: { value: '5' } });
    expect(onChange).toHaveBeenCalledWith({ enabled: true, limit: 5, threshold: 0.85 });
  });

  it('shows threshold value', () => {
    renderEditor({ threshold: 0.9 });
    expect(screen.getByText('0.90')).toBeInTheDocument();
  });

  it('applies locale-specific translations', () => {
    renderEditor({ locale: 'es' });
    expect(screen.getByText('Ejemplos few-shot automáticos')).toBeInTheDocument();
    expect(screen.getByText('Máximo de ejemplos')).toBeInTheDocument();
  });
});
