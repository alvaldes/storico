import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { PublicUserMenu } from '@/components/react/PublicUserMenu';
import { signOut } from 'auth-astro/client';
import { useTranslations } from '@/i18n/utils';

vi.mock('auth-astro/client', () => ({
  signOut: vi.fn(),
}));

const t = useTranslations('en');
const tEs = useTranslations('es');

const enUser = { name: 'Ada Lovelace Byron', email: 'ada@example.com', avatarUrl: null };

beforeEach(() => {
  vi.clearAllMocks();
});

describe('PublicUserMenu — the avatar trigger', () => {
  it('derives two-word initials when there is no avatar image', () => {
    render(<PublicUserMenu locale="en" user={enUser} />);

    expect(screen.getByText('AL')).toBeInTheDocument();
  });

  it('renders ? instead of throwing on an empty name', () => {
    render(<PublicUserMenu locale="en" user={{ name: '', email: 'ada@example.com' }} />);

    expect(screen.getByText('?')).toBeInTheDocument();
  });

  it('renders an emoji-leading name as that emoji plus the next word initial, not a replacement glyph', () => {
    render(<PublicUserMenu locale="en" user={{ name: '😀 Smith', email: 'ada@example.com' }} />);

    expect(screen.getByText('😀S')).toBeInTheDocument();
  });

  it('is reachable by its accessible name', () => {
    render(<PublicUserMenu locale="en" user={enUser} />);

    expect(screen.getByRole('button', { name: t.nav.open_user_menu })).toBeInTheDocument();
  });
});

describe('PublicUserMenu — the opened menu (English)', () => {
  it('reveals the identity header and every item with locale-prefixed hrefs', async () => {
    const user = userEvent.setup();
    render(<PublicUserMenu locale="en" user={enUser} />);

    await user.click(screen.getByRole('button', { name: t.nav.open_user_menu }));

    // Base UI opens the menu from a requestAnimationFrame callback, so the
    // portal lands one tick after the click; findByRole waits for that tick.
    await screen.findByRole('menuitem', { name: t.nav.dashboard });

    expect(screen.getByText('Ada Lovelace Byron')).toBeInTheDocument();
    expect(screen.getByText('ada@example.com')).toBeInTheDocument();

    expect(screen.getByRole('menuitem', { name: t.nav.dashboard })).toHaveAttribute(
      'href',
      '/en/dashboard',
    );
    expect(screen.getByRole('menuitem', { name: t.nav.account })).toHaveAttribute(
      'href',
      '/en/account',
    );
    expect(screen.getByRole('menuitem', { name: t.nav.projects })).toHaveAttribute(
      'href',
      '/en/projects',
    );
    expect(screen.getByRole('menuitem', { name: t.nav.logout })).toBeInTheDocument();
  });
});

describe('PublicUserMenu — the opened menu (Spanish)', () => {
  it('yields Spanish labels and /es/ hrefs', async () => {
    const user = userEvent.setup();
    render(<PublicUserMenu locale="es" user={enUser} />);

    await user.click(screen.getByRole('button', { name: tEs.nav.open_user_menu }));

    await screen.findByRole('menuitem', { name: tEs.nav.dashboard });

    expect(screen.getByRole('menuitem', { name: tEs.nav.dashboard })).toHaveAttribute(
      'href',
      '/es/dashboard',
    );
    expect(screen.getByRole('menuitem', { name: tEs.nav.account })).toHaveAttribute(
      'href',
      '/es/account',
    );
    expect(screen.getByRole('menuitem', { name: tEs.nav.projects })).toHaveAttribute(
      'href',
      '/es/projects',
    );
    expect(screen.getByRole('menuitem', { name: tEs.nav.logout })).toBeInTheDocument();
  });
});

describe('PublicUserMenu — signing out', () => {
  it('calls signOut with the locale-prefixed login callback', async () => {
    const user = userEvent.setup();
    render(<PublicUserMenu locale="en" user={enUser} />);

    await user.click(screen.getByRole('button', { name: t.nav.open_user_menu }));

    const logout = await screen.findByRole('menuitem', { name: t.nav.logout });
    await user.click(logout);

    expect(signOut).toHaveBeenCalledWith({ callbackUrl: '/en/login' });
  });
});
