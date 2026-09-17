import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { renderBoldMarkup } from '@/lib/render-bold-markup';
import { useTranslations } from '@/i18n/utils';

describe('renderBoldMarkup', () => {
  it('splits on the authored tag and renders only the authored segments as elements', () => {
    const { container } = render(<>{renderBoldMarkup('Type <b>yes</b> to confirm.', 'b')}</>);

    expect(container.querySelectorAll('b')).toHaveLength(1);
    expect(container.querySelector('b')?.textContent).toBe('yes');
    expect(container.textContent).toBe('Type yes to confirm.');
    expect(container.innerHTML).toBe('Type <b>yes</b> to confirm.');
  });

  it('renders a `<strong>` when the copy is authored with `<strong>`', () => {
    const { container } = render(
      <>{renderBoldMarkup('Use <strong>As a user</strong> in English.', 'strong')}</>,
    );

    expect(container.querySelectorAll('strong')).toHaveLength(1);
    expect(container.querySelector('strong')?.textContent).toBe('As a user');
    expect(container.textContent).toBe('Use As a user in English.');
  });

  it('does not turn a closing tag of the other flavour into an element', () => {
    // `story_format_hint` is an `<strong>` string; `<b>` in it is ordinary text.
    const { container } = render(<>{renderBoldMarkup('Keep <b>literal</b> here.', 'strong')}</>);

    expect(container.querySelector('strong')).toBeNull();
    expect(container.querySelector('b')).toBeNull();
    expect(container.textContent).toBe('Keep <b>literal</b> here.');
  });

  it('renders nested payload as visible literal text and injects no element', () => {
    const payload = '<img src=x onerror=alert(1)><script>alert(2)</script>';

    const { container } = render(<>{renderBoldMarkup(payload, 'b')}</>);

    // Nothing was parsed into the DOM: no element to append, no handler to fire.
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelectorAll('b')).toHaveLength(0);
    // The payload survives verbatim, as text.
    expect(container.textContent).toBe(payload);
    expect(container.innerHTML).toBe(
      '&lt;img src=x onerror=alert(1)&gt;&lt;script&gt;alert(2)&lt;/script&gt;',
    );
  });

  it('keeps a non-tag payload literal even when the surrounding copy uses the tag', () => {
    const { container } = render(
      <>{renderBoldMarkup('Type <b>yes</b> — not <img src=x onerror=alert(1)>', 'b')}</>,
    );

    expect(container.querySelectorAll('b')).toHaveLength(1);
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toBe('Type yes — not <img src=x onerror=alert(1)>');
  });

  it('can only ever produce the authored tag: no attributes, no handler, no other element', () => {
    // The split is parity-based, so a payload that itself contains the split tag yields that
    // element — this is the exact boundary of the guarantee and it is worth stating rather
    // than assuming. What the helper can never do is honor *other* markup: the only element
    // it creates is the authored tag, attribute-less, and every other payload stays text.
    const { container } = render(
      <>{renderBoldMarkup('<b>t</b><img src=x onerror=alert(1)>', 'b')}</>,
    );

    const bold = container.querySelectorAll('b');
    expect(bold).toHaveLength(1);
    // No way to smuggle an attribute or an event handler through the authored tag.
    expect(bold[0].attributes.length).toBe(0);
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toBe('t<img src=x onerror=alert(1)>');
  });
});

describe('renderBoldMarkup — against the real call-site strings', () => {
  // The two call sites pass the tag their own copy is authored with, so these tests double as the
  // cross-file contract: if the `{email}` label or `story_format_hint` were re-authored with a
  // different tag, the call site would silently stop emphasising it. Expectations are derived from
  // the source string rather than duplicated, so a copy edit does not fail a helper test.
  it('renders the delete-account email label with `<b>` and keeps the email inside it', () => {
    const en = useTranslations('en');
    const label = en.settings.danger_delete_dialog_email_label;
    const email = 'a@b.com';
    const withEmail = label.replace('{email}', email);

    const { container } = render(<>{renderBoldMarkup(withEmail, 'b')}</>);

    expect(container.querySelectorAll('b')).toHaveLength(1);
    // The substituted value is emphasised exactly as the authored placeholder was.
    expect(container.querySelector('b')?.textContent).toBe(email);
    // Visible text is the source string with its tags dropped, and nothing else changed.
    expect(container.textContent).toBe(withEmail.replace(/<\/?b>/g, ''));
  });

  it('renders the dialog boilerplate with `<b>`', () => {
    const en = useTranslations('en');
    const copy = en.settings.danger_delete_dialog_description_1;

    const { container } = render(<>{renderBoldMarkup(copy, 'b')}</>);

    expect(container.querySelectorAll('b')).toHaveLength(1);
    expect(container.textContent).toBe(copy.replace(/<\/?b>/g, ''));
  });

  it('renders the story format hint with `<strong>` and never as `<b>`', () => {
    const en = useTranslations('en');
    const hint = en.stories.story_format_hint;

    const { container } = render(<>{renderBoldMarkup(hint, 'strong')}</>);

    expect(container.querySelectorAll('strong')).toHaveLength(1);
    expect(container.querySelectorAll('b')).toHaveLength(0);
    expect(container.textContent).toBe(hint.replace(/<\/?strong>/g, ''));
  });
});
