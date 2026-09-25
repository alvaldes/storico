import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { MobileNav, type MobileNavLink } from '@/components/react/MobileNav';
import { useTranslations } from '@/i18n/utils';

vi.mock('auth-astro/client', () => ({
  signOut: vi.fn(),
}));

const t = useTranslations('en');

const enUser = { name: 'Ada Lovelace Byron', email: 'ada@example.com', avatarUrl: null };

// Mirrors what PublicLayout.astro builds for a signed-in visitor: Product holds
// Stories + Kanban only — never Dashboard, which is the footer CTA's job.
const signedInLinks: MobileNavLink[] = [
  { href: '/en/stories', label: t.nav.stories, category: t.footer.product },
  { href: '/en/kanban', label: t.nav.kanban, category: t.footer.product },
  { href: '/en/docs', label: t.footer.documentation, category: t.footer.resources },
  { href: '/en/api', label: t.footer.api_reference, category: t.footer.resources },
  { href: '/en/status', label: t.footer.status_page, category: t.footer.resources },
  { href: '/en/about', label: t.footer.about, category: t.footer.company },
  { href: '/en/privacy', label: t.footer.privacy, category: t.footer.company },
  { href: '/en/terms', label: t.footer.terms, category: t.footer.company },
];

// Anonymous visitors get no Product group: those routes sit behind the auth guard.
const signedOutLinks: MobileNavLink[] = signedInLinks.filter(
  (link) => link.category !== t.footer.product,
);

beforeEach(() => {
  vi.clearAllMocks();
});

async function openSheet(props: Parameters<typeof MobileNav>[0]) {
  const user = userEvent.setup();
  render(<MobileNav {...props} />);
  await user.click(screen.getByRole('button', { name: t.nav.toggleMenu }));
  // Base UI opens the sheet's portal from a requestAnimationFrame callback, so
  // the content lands one tick after the click; findBy* waits for that tick.
  return user;
}

describe('MobileNav — signed in', () => {
  it('shows the identity block, the three labelled groups, and exactly one "Dashboard" (the CTA)', async () => {
    await openSheet({
      links: signedInLinks,
      brandName: 'Storico',
      locale: 'en',
      langToggleHref: '/es/',
      cta: { href: '/en/dashboard', label: t.nav.dashboard },
      user: enUser,
    });

    await screen.findByRole('link', { name: t.nav.stories });

    expect(screen.getByText('Ada Lovelace Byron')).toBeInTheDocument();
    expect(screen.getByText('ada@example.com')).toBeInTheDocument();

    expect(screen.getByText(t.footer.product)).toBeInTheDocument();
    expect(screen.getByText(t.footer.resources)).toBeInTheDocument();
    expect(screen.getByText(t.footer.company)).toBeInTheDocument();

    expect(screen.getByRole('link', { name: t.nav.stories })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: t.nav.kanban })).toBeInTheDocument();

    // The Product group lost Dashboard (D2): the footer CTA is the only one.
    expect(screen.getAllByText(t.nav.dashboard)).toHaveLength(1);
  });

  it('renders the identity block as a link to /account, reachable by its accessible name', async () => {
    await openSheet({
      links: signedInLinks,
      brandName: 'Storico',
      locale: 'en',
      langToggleHref: '/es/',
      cta: { href: '/en/dashboard', label: t.nav.dashboard },
      user: enUser,
    });

    const accountLink = await screen.findByRole('link', { name: t.nav.account });
    expect(accountLink).toHaveAttribute('href', '/en/account');
  });

  it('renders rows as real links with locale-prefixed hrefs', async () => {
    await openSheet({
      links: signedInLinks,
      brandName: 'Storico',
      locale: 'en',
      langToggleHref: '/es/',
      cta: { href: '/en/dashboard', label: t.nav.dashboard },
      user: enUser,
    });

    await screen.findByRole('link', { name: t.nav.stories });

    expect(screen.getByRole('link', { name: t.nav.stories })).toHaveAttribute('href', '/en/stories');
    expect(screen.getByRole('link', { name: t.nav.kanban })).toHaveAttribute('href', '/en/kanban');
    expect(screen.getByRole('link', { name: t.footer.documentation })).toHaveAttribute(
      'href',
      '/en/docs',
    );
  });
});

describe('MobileNav — accessible name', () => {
  // The single-SheetTitle rule: when the identity row is shown the title is
  // sr-only, when signed out it is visible, but the panel must stay a dialog
  // named after the brand in BOTH states.
  it('exposes the panel as a dialog named after the brand in both session states', async () => {
    const user = userEvent.setup();
    const sharedProps = {
      brandName: 'Storico',
      locale: 'en',
      langToggleHref: '/es/',
    } as const;

    // Signed in: the visible title is replaced by the identity row.
    const signedIn = render(
      <MobileNav
        {...sharedProps}
        links={signedInLinks}
        cta={{ href: '/en/dashboard', label: t.nav.dashboard }}
        user={enUser}
      />,
    );
    await user.click(screen.getByRole('button', { name: t.nav.toggleMenu }));
    expect(await screen.findByRole('dialog', { name: 'Storico' })).toBeInTheDocument();
    signedIn.unmount();

    // Signed out: the title is rendered visibly again.
    render(
      <MobileNav
        {...sharedProps}
        links={signedOutLinks}
        cta={{ href: '/en/login', label: t.landing.cta.button }}
        user={null}
      />,
    );
    await user.click(screen.getByRole('button', { name: t.nav.toggleMenu }));
    expect(await screen.findByRole('dialog', { name: 'Storico' })).toBeInTheDocument();
  });
});

describe('MobileNav — signed out', () => {
  it('shows no identity block, no sign-out control, and a login CTA', async () => {
    await openSheet({
      links: signedOutLinks,
      brandName: 'Storico',
      locale: 'en',
      langToggleHref: '/es/',
      cta: { href: '/en/login', label: t.landing.cta.button },
      user: null,
    });

    await screen.findByRole('link', { name: t.footer.documentation });

    expect(screen.queryByText(enUser.name)).not.toBeInTheDocument();
    // By role, not by text: the label is translated.
    expect(screen.queryByRole('button', { name: t.nav.logout })).not.toBeInTheDocument();
    expect(screen.queryByText(t.footer.product)).not.toBeInTheDocument();

    const cta = screen.getByRole('link', { name: t.landing.cta.button });
    expect(cta).toHaveAttribute('href', '/en/login');
  });
});
